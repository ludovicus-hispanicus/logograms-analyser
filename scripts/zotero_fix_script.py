#!/usr/bin/env python3
"""Generate a Zotero "Run JavaScript" script that fixes the cited items in place.

Zotero's local HTTP API is read-only (a PATCH answers 501), so bulk edits go
through Tools -> Developer -> Run JavaScript, which drives Zotero's own item API
and therefore syncs and undoes like any manual edit.

Four classes of fix, all traceable to the reviewers' comments:

  * seriesNumber -- the series volume usually sits in `volume`, but CSL maps
    seriesNumber to collection-number, which is what the OBO style prints inside
    the series parentheses. Moving it is what makes "(Yale Oriental Series 10)"
    appear at all.
  * series -- strip an abbreviation the series name carries in brackets
    ("... Records (SANER)"), which otherwise prints as nested parentheses.
  * title -- strip BibTeX markup imported with the library (\\grqq, \\itshape).
  * creators -- expand a given name stored as initials.

A forename is only proposed when it is EVIDENCED: another item in the same
library, or the printed OBO article supplied as --reference, carries the full
form AND its initials agree with the initials already stored. Anything left
unresolved is listed for you rather than guessed at.

    "C:/Users/wende/AppData/Local/Programs/Python/Python312/python.exe" \
        scripts/zotero_fix_script.py DOC.docx [-o OUT.js] [--reference SOME.pdf]

Run it with that interpreter, NOT with `py`. The `#!/usr/bin/env python3` line
makes the Windows py launcher follow the shebang to msys2's python3, which has no
PyMuPDF -- the printed references then yield nothing and every forename that only
the PDFs know is silently reported as unresolved.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_docx import load_bib, map_article_bib                    # noqa: E402
from inject_zotero import (                                          # noqa: E402
    bibliography_entries, library_links, resolve_link, DEFAULT_BIB, DEFAULT_DB,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
INITIALS = re.compile(r"^(?:[A-ZÀ-Þ]\.?[\s-]*)+$")
LATEX = re.compile(r"\\(?:grqq|frqq|flqq|glqq|textquotedbl|itshape|textit|emph)\b|ıtshape")
SERIES_ABBR = re.compile(r"\s*\(([A-Z][A-Za-z]{1,9})\)\s*$")
SERIES_IN_DOC = re.compile(r"\(([^()]*?)(?:\s+([IVXivx\d][\w/\-–.]*))?\)")
# "Rochberg, Francesca. 1993." / "Freedman, Sally M. 1998." in a printed OBO
# bibliography. The middle initial carries its own full stop, so the one that
# closes the name has to be optional -- demanding it silently lost every name
# with a middle initial (Sally M., Ulla S., Heather D., Zackary M.).
PRINTED = re.compile(r"\b([A-ZÀ-Þ][\wÀ-ž'’\-]+(?:[ -][A-ZÀ-Þ][\wÀ-ž'’\-]+)?),\s+"
                     r"([A-ZÀ-Þ][\wÀ-ž'’\-]{2,}(?:\s+[A-ZÀ-Þ]\.)*)\.?\s+"
                     r"(?:1[89]|20)\d{2}")

# Forenames the author confirmed by hand (2026-09-14). Nothing on disk evidences
# these, so they are listed explicitly rather than inferred -- but they still pass
# through consistent(), so a typo here cannot quietly rewrite the wrong name.
CONFIRMED = {
    ("Abusch", "T."): "Tzvi",
    ("Borger", "R."): "Rykle",
    ("Escobar", "E. A."): "Eduardo A.",
    ("George", "A. R."): "Andrew R.",
    ("Goetze", "A."): "Albrecht",
    ("Labat", "R."): "René",
    ("Leichty", "E."): "Erle",
    ("Nötscher", "F."): "Friedrich",
    ("Rutz", "M. T."): "Matthew T.",
    ("Seminara", "S."): "Stefano",
    ("Tanaka", "T."): "Terri",
    ("Wiggermann", "F. A. M."): "Frans A. M.",
    ("Wilhelm", "G."): "Gernot",
    ("von Weiher", "E."): "Egbert",
}

CREATORS = """
select cr.lastName, cr.firstName, ct.creatorType from itemCreators ic
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
ALL_CREATORS = """
select distinct cr.lastName, cr.firstName from itemCreators ic
  join creators cr on cr.creatorID = ic.creatorID
  join items i on i.itemID = ic.itemID
where i.itemID not in (select itemID from deletedItems)
"""


def q(tag):
    return W + tag


def initials_of(name):
    """'Nils P.' -> 'NP';  'N. P.' -> 'NP';  'Ulla S.' -> 'US'."""
    return "".join(p[0] for p in re.split(r"[\s.-]+", name or "") if p).upper()


def consistent(full, stored):
    """Is `full` a safe spelling-out of the initials in `stored`?

    The candidate must account for EVERY initial already stored -- "Andrew" is
    not an expansion of "A. R.", it silently drops the R -- and its first token
    must be a real forename, not a truncation like Abusch's "Tz".
    """
    f, s = initials_of(full), initials_of(stored)
    if not (f and s) or not f.startswith(s):
        return False
    return len(re.split(r"[\s.-]+", full.strip())[0]) >= 3


def printed_forenames(paths):
    """Full forenames harvested from printed OBO bibliographies."""
    found = {}
    if not paths:
        return found
    try:
        import fitz
    except ImportError:
        print("  (PyMuPDF not installed -- skipping the printed references)")
        return found
    for path in paths:
        if not os.path.exists(path):
            print("  reference not found, skipped: %s" % path)
            continue
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
        text = re.sub(r"\s+", " ", re.sub(r"-\n", "", text))
        hits = [(last, first) for last, first in PRINTED.findall(text)
                if not INITIALS.match(first)]
        for last, first in hits:
            found.setdefault(last, set()).add(first)
        print("  %s: %d forenames" % (os.path.basename(path)[:44], len(hits)))
    return found


def para_style(para):
    pr = para.find(q("pPr"))
    if pr is None:
        return None
    st = pr.find(q("pStyle"))
    return st.get(q("val")) if st is not None else None


def typed_series_numbers(doc_root):
    """Series volume numbers as the author typed them, keyed by series name."""
    out = {}
    for para in doc_root.iter(q("p")):
        if para_style(para) != "Bibliographie1":
            continue
        text = "".join(t.text or "" for t in para.iter(q("t")))
        for body, num in SERIES_IN_DOC.findall(text):
            # a series volume is a number or a roman numeral -- not the last word
            # of "(Compte rendu de la ... Rencontre Assyriologique Internationale)"
            if not num or not re.fullmatch(r"\d[\w/\-–.]*|[IVXLC]+(?:/\d+)?", num):
                continue
            if len(body.split()) >= 2:
                out.setdefault(" ".join(body.split()[:3]).lower(), num)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx")
    ap.add_argument("-o", "--out", default=os.path.join(BASE, "docs", "zotero-fixes.js"))
    ap.add_argument("--reference", action="append",
                    help="a printed OBO article (PDF) to harvest full forenames from")
    ap.add_argument("--bib", default=DEFAULT_BIB)
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args()

    doc = ET.fromstring(zipfile.ZipFile(args.docx).read("word/document.xml"))
    entries = [re.sub(r"\b((?:1[89]|20)\d{2})[\u2013-](?:1[89]|20)\d{2}(?=\.)", r"\1", e)
               for e in bibliography_entries(doc)]
    typed_series = typed_series_numbers(doc)

    build = os.path.join(BASE, "docs", "_build")
    os.makedirs(build, exist_ok=True)
    index = load_bib(args.bib, os.path.join(build, "library-csl.json"))
    cmap, _, _ = map_article_bib(entries, index)
    links_index, groups, user_id = library_links(
        args.db, os.path.join(build, "zotero-snapshot.sqlite"))
    con = sqlite3.connect(os.path.join(build, "zotero-snapshot.sqlite"))

    from_library = {}
    for last, first in con.execute(ALL_CREATORS):
        if first and not INITIALS.match(first.strip()):
            from_library.setdefault(last.strip(), set()).add(first.strip())
    from_print = printed_forenames(args.reference)

    fixes, unresolved, seen = [], [], set()
    for item in cmap.values():
        if str(item["id"]) in seen:
            continue
        seen.add(str(item["id"]))
        item_id, uri = resolve_link(item, links_index, groups, user_id)
        if item_id is None:
            continue
        key = uri.rsplit("/", 1)[-1]

        def field(name):
            row = con.execute(FIELD, (item_id, name)).fetchone()
            return row[0] if row else ""

        entry, notes = {"key": key, "set": {}, "creators": []}, []
        title, series = field("title"), field("series")
        number, volume = field("seriesNumber"), field("volume")

        if LATEX.search(title or ""):
            clean = LATEX.sub("", title).replace("  ", " ").strip()
            entry["set"]["title"] = clean
            notes.append("title: strip BibTeX markup")
        if series and not number:
            if volume:
                entry["set"]["seriesNumber"] = volume
                entry["set"]["volume"] = ""
                notes.append("volume %s -> seriesNumber" % volume)
            else:
                want = typed_series.get(" ".join(series.split()[:3]).lower())
                if want:
                    entry["set"]["seriesNumber"] = want
                    notes.append("seriesNumber := %s (as typed in the article)" % want)
                else:
                    unresolved.append((key, title[:50], "series number unknown for %r" % series))
        if series and SERIES_ABBR.search(series):
            entry["set"]["series"] = SERIES_ABBR.sub("", series).strip()
            notes.append("series: drop %s" % SERIES_ABBR.search(series).group(1))

        done = set()
        for last, first, ctype in con.execute(CREATORS, (item_id,)):
            if not first or not INITIALS.match(first.strip()):
                continue
            if (last, first) in done:
                continue
            done.add((last, first))
            confirmed = CONFIRMED.get((last.strip(), first.strip()))
            cands = {c for c in (from_library.get(last.strip(), set())
                                 | from_print.get(last.strip(), set())
                                 | ({confirmed} if confirmed else set()))
                     if consistent(c, first)}
            if confirmed and confirmed in cands:
                best = confirmed          # the author's own call wins any tie
            else:
                best = max(cands, key=len) if len(cands) == 1 else (
                    max(cands, key=len)
                    if cands and len({initials_of(c) for c in cands}) == 1 else None)
            if best:
                entry["creators"].append({"lastName": last, "from": first, "to": best})
                notes.append("%s: %s -> %s" % (last, first, best))
            else:
                unresolved.append((key, title[:50], "forename for %s, %s" % (last, first)))
        if entry["set"] or entry["creators"]:
            entry["why"] = "; ".join(notes)
            fixes.append(entry)

    js = """// Zotero bulk fixes for the OBO bibliography -- generated, do not hand-edit.
// Paste into Zotero: Tools -> Developer -> Run JavaScript (check "Run as async function").
// Every change goes through Zotero's own item API, so it syncs and undoes normally.
const FIXES = %s;

const lib = Zotero.Libraries.userLibraryID;
let changed = 0, missing = [], log = [];
for (const fix of FIXES) {
    const item = await Zotero.Items.getByLibraryAndKeyAsync(lib, fix.key);
    if (!item) { missing.push(fix.key); continue; }
    for (const [field, value] of Object.entries(fix.set || {})) {
        item.setField(field, value);
    }
    if (fix.creators && fix.creators.length) {
        const creators = item.getCreators();
        for (const want of fix.creators) {
            for (const c of creators) {
                if (c.lastName === want.lastName && c.firstName === want.from) {
                    c.firstName = want.to;
                }
            }
        }
        item.setCreators(creators);
    }
    await item.saveTx();
    changed++;
    log.push(item.getField('title').slice(0, 48) + '  <-  ' + fix.why);
}
return `updated ${changed} of ${FIXES.length} items` +
       (missing.length ? `\\nnot found: ${missing.join(', ')}` : '') +
       '\\n\\n' + log.join('\\n');
""" % json.dumps(fixes, ensure_ascii=False, indent=2)

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(js)

    print("%d items will be changed -> %s" % (len(fixes), args.out))
    for fix in fixes:
        print("  %-10s %s" % (fix["key"], fix["why"][:96]))
    if unresolved:
        print("\n%d things I will NOT guess at:" % len(unresolved))
        for key, title, what in unresolved:
            print("  %-10s %-42s %s" % (key, title, what))


if __name__ == "__main__":
    main()
