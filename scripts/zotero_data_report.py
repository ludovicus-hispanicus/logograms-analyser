#!/usr/bin/env python3
"""What has to be fixed in the Zotero items themselves before the bibliography is right.

The OBO CSL style renders what it is given. Three of the reviewers' complaints are
not style problems at all -- the data in Zotero is wrong:

  * given names stored as initials, where OBO wants them in full;
  * collection-number (the series volume) missing, so "(Yale oriental series)"
    prints without its 10;
  * BibTeX markup imported verbatim into titles (\\grqq, \\itshape, ...).

This reads the cited items straight out of zotero.sqlite, compares them with the
bibliography the author typed by hand in the .docx (which the reviewers corrected),
and writes a per-item worklist.

    py scripts/zotero_data_report.py DOC.docx [-o OUT.md]
"""
import argparse
import os
import re
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_docx import load_bib, map_article_bib                    # noqa: E402
from inject_zotero import (                                          # noqa: E402
    bibliography_entries, library_links, resolve_link, DEFAULT_BIB, DEFAULT_DB,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INITIALS = re.compile(r"^(?:[A-ZÀ-Þ]\.?\s*)+$")
LATEX = re.compile(r"\\[a-zA-Z]{2,}|ıtshape|\\grqq|\\frqq|\\flqq")
# "(Series Title 12)" / "(Series Title)" as the author typed it
SERIES = re.compile(r"\(([^()]*?)(?:\s+([IVXivx\d][\w/\-–.]*))?\)")

CREATORS = """
select cr.lastName, cr.firstName, ct.creatorType
from itemCreators ic
  join creators cr on cr.creatorID = ic.creatorID
  join creatorTypes ct on ct.creatorTypeID = ic.creatorTypeID
where ic.itemID = ? order by ic.orderIndex
"""
FIELD = """
select v.value from itemData d
  join itemDataValues v on v.valueID = d.valueID
  join fields f on f.fieldID = d.fieldID
where d.itemID = ? and f.fieldName = ?
"""


def q(tag):
    return W + tag


def para_style(para):
    pr = para.find(q("pPr"))
    if pr is None:
        return None
    st = pr.find(q("pStyle"))
    return st.get(q("val")) if st is not None else None


def para_text(para):
    return "".join(t.text or "" for t in para.iter(q("t")))


def typed_by_key(doc_root):
    """The hand-typed bibliography, keyed by first family name + year."""
    out = {}
    for para in doc_root.iter(q("p")):
        if para_style(para) != "Bibliographie1":
            continue
        text = re.sub(r"\s+", " ", para_text(para)).strip()
        m = re.match(r"^(?:von |van |de )?([^,]+),.*?\b((?:1[89]|20)\d{2})", text)
        if m:
            out.setdefault((m.group(1).strip().lower(), m.group(2)), text)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx")
    ap.add_argument("-o", "--out", default=os.path.join(
        BASE, "docs", "The-Logographic-Shift-zotero-data-fixes.md"))
    ap.add_argument("--bib", default=DEFAULT_BIB)
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args()

    doc = ET.fromstring(zipfile.ZipFile(args.docx).read("word/document.xml"))
    entries = [re.sub(r"\b((?:1[89]|20)\d{2})[–-](?:1[89]|20)\d{2}(?=\.)", r"\1", e)
               for e in bibliography_entries(doc)]
    typed = typed_by_key(doc)

    build = os.path.join(BASE, "docs", "_build")
    os.makedirs(build, exist_ok=True)
    index = load_bib(args.bib, os.path.join(build, "library-csl.json"))
    cmap, _, _ = map_article_bib(entries, index)
    links_index, groups, user_id = library_links(
        args.db, os.path.join(build, "zotero-snapshot.sqlite"))
    con = sqlite3.connect(os.path.join(build, "zotero-snapshot.sqlite"))

    rows, seen = [], set()
    for item in cmap.values():
        if str(item["id"]) in seen:
            continue
        seen.add(str(item["id"]))
        item_id, uri = resolve_link(item, links_index, groups, user_id)
        if item_id is None:
            continue
        creators = list(con.execute(CREATORS, (item_id,)))
        def field(name):
            r = con.execute(FIELD, (item_id, name)).fetchone()
            return r[0] if r else ""

        title = field("title")
        series = field("series") or field("seriesTitle") or ""
        # CSL maps seriesNumber -> collection-number, which is what the OBO style
        # prints inside the series parentheses. A number sitting in Volume is a
        # different variable and never shows up there.
        number = field("seriesNumber")
        volume = field("volume")

        year = item.get("issued", {}).get("date-parts", [[None]])
        year = str(year[0][0]) if year and year[0] and year[0][0] else ""
        primary = [c for c in creators if c[2] in ("author", "editor")]
        fam = primary[0][0].split()[-1].lower() if primary else ""
        hand = typed.get((fam, year)) or typed.get(
            (primary[0][0].strip().lower() if primary else "", year), "")

        problems = []
        short = [("%s, %s" % (ln, fn)) for ln, fn, _ in primary
                 if fn and INITIALS.match(fn.strip())]
        if short:
            problems.append(("given name is initials only", "; ".join(short)))
        for text, where in ((title, "title"), (series, "series")):
            if text and LATEX.search(text):
                problems.append(("BibTeX markup in %s" % where, text[:70]))
        if series and not number:
            want = ""
            for body, num in SERIES.findall(hand):
                if num and body.split()[:2] == series.split()[:2]:
                    want = num
                    break
            if volume:
                problems.append(("series volume is in the wrong field",
                                 "move Volume %s -> Series Number (series = %s)"
                                 % (volume, series)))
            else:
                problems.append(("Series Number empty",
                                 "series = %s; set Series Number to %s"
                                 % (series, want or "?? (author typed no number)")))
        if series and "(" in series:
            problems.append(("abbreviation inside the series name", series))
        if problems:
            rows.append((("%s %s" % (primary[0][0] if primary else "?", year)).strip(),
                         title[:64], item_id, uri, problems))

    rows.sort()
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Zotero items to fix before the bibliography is regenerated\n\n")
        f.write("%d of the cited items need editing **in Zotero**. The OBO style renders\n"
                "what the item holds, so these cannot be fixed in the .csl.\n\n" % len(rows))
        for name, title, item_id, uri, problems in rows:
            f.write("## %s\n\n" % name)
            f.write("%s  \n`%s`\n\n" % (title, uri))
            for what, detail in problems:
                f.write("- **%s** — %s\n" % (what, detail))
            f.write("\n")
    print("%d items need fixing -> %s" % (len(rows), args.out))
    for name, _, _, _, problems in rows:
        print("  %-28s %s" % (name, "; ".join(w for w, _ in problems)))


if __name__ == "__main__":
    main()
