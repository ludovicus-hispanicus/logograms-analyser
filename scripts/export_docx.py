# -*- coding: utf-8 -*-
"""Export the article to a Word file on the OBO template with live Zotero fields.

    py -3 scripts/export_docx.py [--bib "path/to/My Library.bib"]
                                 [--template "path/to/OBO Template_Collective volumes.docx"]
                                 [--out docs/The-Logographic-Shift-zotero.docx]

What it does
------------
1. Converts the Zotero .bib export to CSL JSON (via pandoc) and indexes it by
   (author family names, year).
2. Finds every "Author Year(, pages)" citation in the article's footnotes and
   replaces it with a live ZOTERO_ITEM CSL_CITATION field. The item's full CSL
   data is embedded in the field, the mechanism Zotero itself uses for shared
   documents: the Zotero Word plugin can refresh, re-style (e.g. to the OBO
   house style) and edit these citations; on first edit of a citation Zotero
   offers to re-link it to the local library.
3. Replaces the typed bibliography with a live ZOTERO_BIBL field whose cached
   text is the current typed bibliography, so the document looks right before
   the first refresh and regenerates from the cited items afterwards.
4. Renders through pandoc with the OBO template as reference-doc; a Lua filter
   maps body text to "Standard Abstand vor 6 Pt.", omen quotations to "Quote"
   (= Zitat), and Table/Figure captions to "Bildlegende".

Citations the matcher cannot resolve unambiguously are left as plain text and
listed at the end of the run.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import unicodedata

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "docs", "The-Logographic-Shift.md")
PANDOC = os.environ.get("PANDOC", r"C:\Users\wende\AppData\Local\Pandoc\pandoc.exe")

# --------------------------------------------------------------- bib indexing

def norm(s):
    """Lowercase, strip accents, ß->ss, for name matching."""
    s = s.replace("ß", "ss")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


PARTICLES = {"von", "van", "de", "der", "al", "el", "di"}


def fam_key(name):
    """Reduce a family name to its accent-free last token: 'von Soden' -> 'soden',
    'Sáenz Santos' -> 'santos', 'Al-Rawi' -> 'al-rawi' (hyphens kept)."""
    toks = [t for t in norm(name).split() if t not in PARTICLES]
    return toks[-1] if toks else norm(name)


def title_tokens(s):
    """Significant words plus numbers (chapter and tablet numbers discriminate,
    e.g. EAE 'Chapter 55' vs 'Chapter 57')."""
    return {t for t in re.findall(r"[a-zšṣṭḫā-ž]+|\d+", norm(s))
            if len(t) > 3 or t.isdigit()}


def item_year(it):
    issued = it.get("issued", {}).get("date-parts", [[None]])
    return str(issued[0][0]) if issued and issued[0] and issued[0][0] else None


def item_fams(it):
    people = it.get("author") or it.get("editor") or []
    return tuple(fam_key(str(p.get("family", p.get("literal", "")))) for p in people)


def load_bib(bib_path, cache):
    if not os.path.exists(cache) or os.path.getmtime(cache) < os.path.getmtime(bib_path):
        subprocess.run([PANDOC, bib_path, "-t", "csljson", "-o", cache], check=True)
    with open(cache, encoding="utf-8") as f:
        items = json.load(f)
    index = {}   # (last-token fams, year) -> [item, ...]
    for it in items:
        fams, year = item_fams(it), item_year(it)
        if not fams or not year:
            continue
        index.setdefault((fams, year), []).append(it)
        if len(fams) > 1:   # first-author fallback ("Al-Rawi & George" style lookups)
            index.setdefault(((fams[0],), year), []).append(it)
    return index


BIBENTRY_RE = re.compile(
    r"^(?P<authors>.+?)\s+(?P<year>1[89]\d{2}|20[0-3]\d)(?P<suffix>[a-z])?\.\s+(?P<rest>.+)$")


def map_article_bib(entries, index):
    """Match the article's typed bibliography to library items by author+year,
    disambiguating by title overlap. Returns {(fams, year+suffix): item}."""
    cmap, misses = {}, []
    for e in entries:
        m = BIBENTRY_RE.match(e)
        if not m:
            misses.append(("unparsed", e[:70]))
            continue
        authors = [a.strip() for a in re.split(r"\s*/\s*|\s+&\s+", m.group("authors"))]
        fams = tuple(fam_key(a.split(",")[0]) for a in authors if a)
        cands = index.get((m.group("year") and (fams, m.group("year"))) or ()) or \
            index.get((fams, m.group("year")), [])
        cands = list({c["id"]: c for c in cands}.values())
        if not cands:
            misses.append(("no library item", e[:70]))
            continue
        if len(cands) == 1:
            best = cands[0]
        else:
            # A quoted segment names the item itself (an article or chapter);
            # otherwise score on the whole tail. Container title breaks ties.
            q = re.match(r'^[\"„"«]([^\""»]+)', m.group("rest"))
            want = title_tokens(q.group(1) if q else m.group("rest"))
            rest = title_tokens(m.group("rest"))

            def score(c):
                t = title_tokens(str(c.get("title", "")))
                ct = title_tokens(str(c.get("container-title", "")))
                return (len(want & t), len(rest & (t | ct)))
            best = max(cands, key=score)
        cmap[(fams, m.group("year") + (m.group("suffix") or ""))] = best
    return cmap, misses


# --------------------------------------------------------- citation detection

# One personal name: "Heeßel", "Sáenz Santos", "von Soden", "Al-Rawi",
# "Huber Vulliet", "de Zorzi" ...
NAME = r"(?:(?:[Vv]on|[Vv]an|[Dd]e|Al|al)[- ])?[A-ZĀ-ŽÀ-Ö][\w''\-]+(?:\s+(?:Santos|Vulliet|Sepe))?"
CITE_RE = re.compile(
    r"(?<![\w/])"
    r"(?P<names>" + NAME + r"(?:\s*(?:/|&|and)\s*" + NAME + r")*)"
    r"\s+(?P<year>1[89]\d{2}|20[0-3]\d)(?P<suffix>[a-z])?"
    r"(?P<locator>,\s*(?:pp?\.\s*)?(?:§\s*)?\d+[\d\.,:–\-]*(?:\s*(?:ff?\.?|and\s+\d+))?"
    r"|,\s*no\.\s*[\w\.\d]+"
    r"|,\s*passim)?")


def split_names(names):
    return [n.strip() for n in re.split(r"\s*(?:/|&|\band\b)\s*", names) if n.strip()]


def find_citations(text):
    """Yield (start, end, names, year+suffix, locator_text) in one footnote."""
    for m in CITE_RE.finditer(text):
        end = m.end()
        # never swallow sentence-final punctuation into the field: on refresh
        # Zotero replaces the cached text and the period would vanish
        while end > m.start() and text[end - 1] in ".,;" \
                and not text[:end].endswith(("f.", "ff.")):
            end -= 1
        loc = text[m.start("locator"):end].lstrip(", ").strip() \
            if m.group("locator") else ""
        yield m.start(), end, split_names(m.group("names")), \
            m.group("year"), m.group("suffix") or "", loc


# --------------------------------------------------------- field XML builders

def esc(s):
    return html.escape(s, quote=False).replace('"', "&quot;")


_cid = [0]


def zotero_item_field(items, cited_text, locators):
    """A live ADDIN ZOTERO_ITEM CSL_CITATION field as raw OpenXML runs."""
    _cid[0] += 1
    citation_items = []
    for it, loc in zip(items, locators):
        ci = {"id": abs(hash(it["id"])) % 100000,
              "uris": [f"http://zotero.org/users/local/obo/items/{it['id']}"],
              "itemData": it}
        if loc:
            m = re.match(r"(?:pp?\.\s*)?([\d\.,:–\-]+[\d])(\s*ff?\.?)?$", loc)
            if loc.startswith("§"):
                ci["label"] = "section"; ci["locator"] = loc.lstrip("§ ").strip()
            elif loc.startswith("no."):
                ci["label"] = "number"; ci["locator"] = loc[3:].strip()
            elif m:
                ci["label"] = "page"
                ci["locator"] = m.group(1) + (m.group(2).strip() if m.group(2) else "")
        citation_items.append(ci)
    payload = {
        "citationID": f"obo{_cid[0]:05d}",
        "properties": {"formattedCitation": cited_text,
                       "plainCitation": cited_text, "noteIndex": 0},
        "citationItems": citation_items,
        "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json",
    }
    instr = " ADDIN ZOTERO_ITEM CSL_CITATION " + json.dumps(payload, ensure_ascii=False)
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{esc(instr)}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t xml:space="preserve">{esc(cited_text)}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def md_runs(text):
    """Markdown inline emphasis to Word runs: *...* becomes italic."""
    runs = []
    for part in re.split(r"(\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("*") and part.endswith("*") and len(part) > 2:
            runs.append('<w:r><w:rPr><w:i/></w:rPr>'
                        f'<w:t xml:space="preserve">{esc(part[1:-1])}</w:t></w:r>')
        else:
            runs.append(f'<w:r><w:t xml:space="preserve">{esc(part)}</w:t></w:r>')
    return "".join(runs)


def zotero_bibl_field(entries):
    """A live ADDIN ZOTERO_BIBL field caching the typed bibliography."""
    instr = (' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} '
             'CSL_BIBLIOGRAPHY ')
    paras = "".join(
        '<w:p><w:pPr><w:pStyle w:val="Bibliographie1"/></w:pPr>'
        f'{md_runs(e)}</w:p>'
        for e in entries)
    return ('<w:p><w:pPr><w:pStyle w:val="Bibliographie1"/></w:pPr>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{esc(instr)}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r></w:p>'
            + paras +
            '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')


# ---------------------------------------------------------------- md pipeline

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bib", default=r"C:\Users\wende\Downloads\My Library.bib")
    ap.add_argument("--template",
                    default=r"C:\Users\wende\Downloads\OBO Template_Collective volumes.docx")
    ap.add_argument("--out", default=os.path.join(BASE, "docs", "The-Logographic-Shift-zotero.docx"))
    ap.add_argument("--split", action="store_true",
                    help="separate deliverables: -text.docx with [Table/Figure N near here] "
                         "callouts, -tables.docx, -figures.docx, and numbered figure files "
                         "in docs/_delivery/")
    args = ap.parse_args()

    build = os.path.join(BASE, "docs", "_build")
    os.makedirs(build, exist_ok=True)
    index = load_bib(args.bib, os.path.join(build, "library-csl.json"))
    print(f"bib: {sum(len(v) for v in index.values())} indexed entries")

    md = open(SRC, encoding="utf-8").read()

    # ---- split off the bibliography section (replaced by a live field)
    bib_m = re.search(r"^## Bibliography\s*$", md, re.M)
    fn_m = re.search(r"^\[\^\d+\]:", md, re.M)
    body = md[:bib_m.start()]
    tail = md[bib_m.end():fn_m.start()] if fn_m else md[bib_m.end():]
    notes = md[fn_m.start():] if fn_m else ""
    bib_entries = [l.strip() for l in tail.splitlines() if l.strip()]

    # ---- the typed bibliography names WHICH Author-Year each citation means
    cmap, bib_misses = map_article_bib(bib_entries, index)
    print(f"article bibliography: {len(cmap)} of {len(bib_entries)} entries mapped to library items")
    for (fams, year), it in sorted(cmap.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        print(f"    {'/'.join(fams)} {year:6} -> [{it.get('type','?'):17}] {str(it.get('title',''))[:58]}")

    # ---- replace citations in the FOOTNOTES with placeholders
    matched, unmatched, ambiguous = 0, [], []
    fields = {}

    def zoterify(text):
        nonlocal matched
        out, pos = [], 0
        for start, end, names, year, suffix, loc in find_citations(text):
            fams = tuple(fam_key(n) for n in names)
            cited = text[start:end]
            item = cmap.get((fams, year + suffix))
            if item is None and len(fams) == 1:
                # first-author-only citation of a multi-author entry
                hits = [v for (k, y), v in cmap.items() if y == year + suffix and k[:1] == fams]
                if len({h["id"] for h in hits}) == 1:
                    item = hits[0]
            if item is None:
                cands = list({c["id"]: c for c in index.get((fams, year), [])}.values())
                if len(cands) == 1 and not suffix:
                    item = cands[0]
                elif len(cands) > 1:
                    ambiguous.append(cited)
                    continue
            if item is None:
                unmatched.append(cited)
                continue
            key = f"ZOTFLD{len(fields):04d}"
            fields[key] = zotero_item_field([item], cited, [loc])
            out.append(text[pos:start]); out.append(key)
            pos = end
            matched += 1
        out.append(text[pos:])
        return "".join(out)

    notes = zoterify(notes)

    def style_pass(text):
        """Captions to Bildlegende, title and author to their styles."""
        text = re.sub(r"^(\*\*(?:Table|Figure) \d+\.\*\*.*)$",
                      r'::: {custom-style="Bildlegende"}\n\1\n:::', text, flags=re.M)
        text = re.sub(r"^# (.+)$",
                      r'::: {custom-style="Title"}\n\1\n:::', text, count=1, flags=re.M)
        text = re.sub(r"^\*\*Luis Sáenz\*\*$",
                      r'::: {custom-style="Autor"}\nLuis Sáenz\n:::', text, count=1, flags=re.M)
        return text

    # ---- live bibliography field
    bibl = "## Bibliography\n\n```{=openxml}\n" + zotero_bibl_field(bib_entries) + "\n```\n\n"

    # ---- Lua filter: body/quote styles + image width
    lua = os.path.join(build, "obo-styles.lua")
    open(lua, "w", encoding="utf-8", newline="\n").write("""
function Pandoc(doc)
  local out = {}
  for _, b in ipairs(doc.blocks) do
    if b.t == 'Para' and not (#b.content == 1 and b.content[1].t == 'Image') then
      table.insert(out, pandoc.Div({b}, {['custom-style'] = 'Standard Abstand vor 6 Pt.'}))
    elseif b.t == 'BlockQuote' then
      table.insert(out, pandoc.Div(b.content, {['custom-style'] = 'Quote'}))
    else
      table.insert(out, b)
    end
  end
  doc.blocks = out
  return doc
end
function Image(img)
  img.attributes.width = '15.5cm'
  return img
end
""")

    import shutil
    import zipfile

    def build_docx(md_text, out_docx, tag):
        src_md = os.path.join(build, f"article-{tag}.md")
        open(src_md, "w", encoding="utf-8", newline="\n").write(md_text)
        subprocess.run(
            [PANDOC, src_md, "-f", "markdown", "-o", out_docx,
             "--reference-doc", args.template,
             "--lua-filter", lua,
             "--resource-path", os.path.join(BASE, "docs")],
            check=True, cwd=BASE)
        # swap placeholders for live fields inside the produced docx
        tmp = out_docx + ".tmp"
        shutil.copy(out_docx, tmp)
        with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename in ("word/document.xml", "word/footnotes.xml"):
                    xml = data.decode("utf-8")
                    for key, fld in fields.items():
                        # the placeholder sits inside a <w:t>; split its run around the field
                        xml = re.sub(
                            r'(<w:r>(?:(?!<w:r>).)*?<w:t[^>]*>)([^<]*?)'
                            + key +
                            r'([^<]*?)(</w:t></w:r>)',
                            lambda m, f=fld: (
                                (m.group(1) + m.group(2) + m.group(4) if m.group(2) else "")
                                + f
                                + (m.group(1) + m.group(3) + m.group(4) if m.group(3) else "")),
                            xml, count=1, flags=re.S)
                    data = xml.encode("utf-8")
                zout.writestr(info, data)
        os.remove(tmp)
        inserted = 0
        with zipfile.ZipFile(out_docx) as z:
            for f in ("word/document.xml", "word/footnotes.xml"):
                x = z.read(f).decode("utf-8")
                inserted += x.count("ZOTERO_ITEM")
                if "ZOTFLD" in x:
                    print(f"  !! unreplaced placeholders remain in {out_docx}:{f}")
        print(f"wrote {out_docx}  ({inserted} live citation fields)")

    if not args.split:
        build_docx(style_pass(body) + "\n" + bibl + notes, args.out, "zotero")
    else:
        # ---- pull every table (pipe block + caption) and figure (image + caption)
        TBL_RE = re.compile(
            r"^(?P<tbl>(?:\|[^\n]*\n)+)\s*\n(?P<cap>\*\*Table (?P<num>\d+)\.\*\*[^\n]*)$", re.M)
        FIG_RE = re.compile(
            r"^!\[[^\]]*\]\((?P<path>[^)]+)\)\s*\n\s*\n(?P<cap>\*\*Figure (?P<num>\d+)\.\*\*[^\n]*)$", re.M)

        tables, figures = [], []

        def take_table(m):
            tables.append((int(m.group("num")), m.group("tbl"), m.group("cap")))
            return f"\\[Table {m.group('num')} near here\\]"

        def take_figure(m):
            figures.append((int(m.group("num")), m.group("path"), m.group("cap")))
            return f"\\[Figure {m.group('num')} near here\\]"

        text_body = TBL_RE.sub(take_table, body)
        text_body = FIG_RE.sub(take_figure, text_body)
        print(f"split: {len(tables)} tables and {len(figures)} figures pulled out")

        stem = re.sub(r"\.docx$", "", args.out)
        build_docx(style_pass(text_body) + "\n" + bibl + notes,
                   stem + "-text.docx", "text")

        tables_md = "# The Logographic Shift: Tables\n\n" + "\n".join(
            f"{tbl}\n{cap}\n" for _n, tbl, cap in sorted(tables)) + "\n" + notes
        build_docx(style_pass(tables_md), stem + "-tables.docx", "tables")

        figures_md = "# The Logographic Shift: Figures\n\n" + "\n".join(
            f"![]({path})\n\n{cap}\n" for _n, path, cap in sorted(figures)) + "\n" + notes
        build_docx(style_pass(figures_md), stem + "-figures.docx", "figures")

        # numbered copies of the image files for submission
        delivery = os.path.join(BASE, "docs", "_delivery")
        os.makedirs(delivery, exist_ok=True)
        for n, path, _cap in sorted(figures):
            src_img = os.path.normpath(os.path.join(BASE, "docs", path))
            ext = os.path.splitext(src_img)[1]
            shutil.copy(src_img, os.path.join(delivery, f"Figure-{n:02d}{ext}"))
        print(f"figure files copied to {delivery} (Figure-01..{len(figures):02d})")

    print(f"citations matched: {matched}")
    if bib_misses:
        print(f"\nBIBLIOGRAPHY ENTRIES WITHOUT LIBRARY MATCH ({len(bib_misses)}):")
        for why, e in bib_misses:
            print(f"  - [{why}] {e}")
    if unmatched:
        print(f"\nUNMATCHED ({len(set(unmatched))}):")
        for c in sorted(set(unmatched)):
            print("  -", c)
    if ambiguous:
        print(f"\nAMBIGUOUS ({len(set(ambiguous))}):")
        for c in sorted(set(ambiguous)):
            print("  -", c)


if __name__ == "__main__":
    main()
