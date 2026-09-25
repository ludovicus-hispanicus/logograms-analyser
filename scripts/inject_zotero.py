#!/usr/bin/env python3
"""Turn the typed citations in an existing .docx into live Zotero fields.

Why this exists: `export_docx.py --zotero` builds the live-field document by
re-exporting the article from Markdown through pandoc. That path is closed now
-- the .docx carries hand layout (anchored images, explicit run sizes, manual
page breaks, the reviewers' tracked changes and comments) that a re-export would
flatten. So this script patches the file that already exists: it wraps each
"Author Year, pages" in the footnotes in an ADDIN ZOTERO_ITEM CSL_CITATION field
with the item's full CSL data embedded, and adds the ZOTERO_PREF document data
that presets the OBO style. Everything else in the package is copied verbatim.

The typed bibliography is deliberately left alone: it is still with the
reviewers, and a ZOTERO_BIBL field would let a Zotero refresh overwrite their
work. Re-run with --bibliography once the bibliography is settled.

    py scripts/inject_zotero.py IN.docx OUT.docx [--bib "…/My Library.bib"]

Zotero re-links the embedded items on the first edit, so this works without
library keys. See also docs/The-Logographic-Shift-review-SK-AH.md.
"""
import argparse
import copy
import html
import json
import os
import re
import sqlite3
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_docx import (                                   # noqa: E402
    load_bib, map_article_bib, find_citations, fam_key, norm, esc,
    zotero_prefs_custom_xml,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS_DECL = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BIB = r"C:\Users\wende\Downloads\My Library.bib"
DEFAULT_DB = os.path.join(os.path.expanduser("~"), "Zotero", "zotero.sqlite")
CUSTOM_CT = ('<Override PartName="/docProps/custom.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.custom-properties+xml"/>')
CUSTOM_REL = ('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/'
              'officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>')


def next_rel_id(rels):
    used = {int(n) for n in re.findall(r'Id="rId(\d+)"', rels)}
    return "rId%d" % (max(used, default=0) + 1)


def q(tag):
    return W + tag


def visible_text_nodes(para):
    """The <w:t> nodes a reader sees, in order: insertions kept, deletions dropped."""
    out = []

    def walk(el, state):
        state = "ins" if el.tag == q("ins") else ("del" if el.tag == q("del") else state)
        if el.tag == q("t"):
            if state != "del":
                out.append(el)
            return
        if el.tag == q("delText"):
            return
        for child in el:
            walk(child, state)

    walk(para, None)
    return out


def para_text(para):
    return "".join(t.text or "" for t in visible_text_nodes(para))


def set_text(node, text):
    """Set a <w:t>, keeping the leading or trailing space Word would otherwise eat."""
    node.text = text
    if text != text.strip():
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def bibliography_entries(doc_root):
    """The typed bibliography, one string per entry, read from the document body."""
    paras, started, entries = list(doc_root.iter(q("p"))), False, []
    for para in paras:
        text = para_text(para).strip()
        if not started:
            started = text.lower() == "bibliography"
            continue
        if text:
            entries.append(text)
    return entries


def title_key(s):
    """Punctuation- and accent-free title, for matching a CSL entry to a real item."""
    return re.sub(r"[^a-z0-9]+", "", norm(s or ""))[:80]


ITEM_QUERY = """
select i.itemID, i.key, i.libraryID,
  (select v.value from itemData d join itemDataValues v on v.valueID=d.valueID
     join fields f on f.fieldID=d.fieldID where d.itemID=i.itemID and f.fieldName='title'),
  (select v.value from itemData d join itemDataValues v on v.valueID=d.valueID
     join fields f on f.fieldID=d.fieldID where d.itemID=i.itemID and f.fieldName='date')
from items i join itemTypes it on it.itemTypeID=i.itemTypeID
where i.itemID not in (select itemID from deletedItems)
  and it.typeName not in ('attachment', 'note', 'annotation')
"""


def library_links(db_path, scratch):
    """Map a CSL title+year onto the real Zotero item it came from.

    A citation whose id and URI point at an actual library item is *linked*: Zotero
    can refresh it, Edit Citation opens the item, and the embedded itemData is only
    a fallback. Invented ids and URIs make every citation an unlinked orphan, which
    is what makes Zotero report citations it cannot resolve.
    Returns (index, uri_prefix_for_library, userID) or (None, None, None).
    """
    if not os.path.exists(db_path):
        return None, None, None
    import shutil
    shutil.copy(db_path, scratch)                 # Zotero holds a lock on the live DB
    con = sqlite3.connect(scratch)
    user_id = dict(con.execute(
        "select setting || '.' || key, value from settings")).get("account.userID")
    groups = {lib: gid for gid, lib in con.execute("select groupID, libraryID from groups")}
    index = {}
    for item_id, key, lib, title, date in con.execute(ITEM_QUERY):
        if not title:
            continue
        year = re.search(r"\b(1[89]\d{2}|20[0-3]\d)\b", date or "")
        entry = (item_id, key, lib)
        index.setdefault((title_key(title), year.group(1) if year else None), []).append(entry)
        index.setdefault((title_key(title), None), []).append(entry)
    con.close()
    return index, groups, user_id


def resolve_link(csl_item, index, groups, user_id):
    """(itemID, uri) for a CSL entry, preferring the personal library on a tie."""
    if not index:
        return None, None
    year = csl_item.get("issued", {}).get("date-parts", [[None]])
    year = str(year[0][0]) if year and year[0] and year[0][0] else None
    key = title_key(str(csl_item.get("title", "")))
    cands = index.get((key, year)) or index.get((key, None)) or []
    if not cands:
        return None, None
    cands.sort(key=lambda c: (c[2] != 1, c[0]))          # personal library first
    item_id, item_key, lib = cands[0]
    if lib == 1:
        uri = "http://zotero.org/users/%s/items/%s" % (user_id, item_key)
    else:
        uri = "http://zotero.org/groups/%s/items/%s" % (groups.get(lib, lib), item_key)
    return item_id, uri


_cid = [0]


def citation_field(items, cited_text, locators, note_index, links):
    """One ADDIN ZOTERO_ITEM CSL_CITATION field, as raw OpenXML runs.

    Differs from export_docx.zotero_item_field in three ways that matter to Zotero:
    citationItems[].id and itemData.id are the SAME value (Zotero keys the embedded
    data off the id), that value is the real library itemID where we found one, and
    noteIndex is the actual footnote number instead of 0 -- in a note style Zotero
    uses noteIndex to order citations and to tell which note each one sits in.
    """
    _cid[0] += 1
    citation_items = []
    for it, loc in zip(items, locators):
        item_id, uri = links.get(str(it["id"]), (None, None))
        ident = item_id if item_id is not None else str(it["id"])
        data = dict(it, id=ident)
        entry = {"id": ident,
                 "uris": [uri] if uri else [],
                 "itemData": data}
        if loc:
            m = re.match(r"(?:pp?\.\s*)?([\d\.,:–\-]+[\d])(\s*ff?\.?)?$", loc)
            if loc.startswith("§"):
                entry["label"], entry["locator"] = "section", loc.lstrip("§ ").strip()
            elif loc.startswith("no."):
                entry["label"], entry["locator"] = "number", loc[3:].strip()
            elif m:
                entry["label"] = "page"
                entry["locator"] = m.group(1) + (m.group(2).strip() if m.group(2) else "")
        citation_items.append(entry)
    payload = {
        "citationID": "obo%05d" % _cid[0],
        "properties": {"formattedCitation": cited_text,
                       "plainCitation": cited_text,
                       "noteIndex": note_index},
        "citationItems": citation_items,
        "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json",
    }
    instr = " ADDIN ZOTERO_ITEM CSL_CITATION " + json.dumps(payload, ensure_ascii=False)
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve">%s</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t xml:space="preserve">%s</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>' % (esc(instr), esc(cited_text)))


def field_runs(items, cited_text, locators, note_index, links, template_rpr):
    """The field as elements, each run wearing the cited run's own formatting."""
    xml = "<w:wrap %s>%s</w:wrap>" % (
        NS_DECL, citation_field(items, cited_text, locators, note_index, links))
    runs = list(ET.fromstring(xml))
    if template_rpr is not None:
        for run in runs:
            run.insert(0, copy.deepcopy(template_rpr))
    return runs


def note_indices(doc_root):
    """Footnote id -> its position in the document, which is Zotero's noteIndex."""
    order, seen = {}, 0
    for ref in doc_root.iter(q("footnoteReference")):
        seen += 1
        order.setdefault(ref.get(q("id")), seen)
    return order


def inject_into_paragraph(para, resolve, note_index, links, stats):
    """Wrap every resolvable citation in this paragraph in a live field."""
    nodes = visible_text_nodes(para)
    if not nodes:
        return
    text = "".join(t.text or "" for t in nodes)
    parent_of = {child: parent for parent in para.iter() for child in parent}

    # right to left, so earlier offsets stay valid
    for start, end, names, year, suffix, locator in reversed(list(find_citations(text))):
        cited = text[start:end]
        items = resolve(names, year + suffix)
        if not items:
            stats["unresolved"].append(cited)
            continue

        pos, touched = 0, []
        for node in nodes:
            length = len(node.text or "")
            if pos + length > start and pos < end:
                touched.append((node, pos))
            pos += length
        runs = [parent_of[node] for node, _ in touched]
        holders = [parent_of[run] for run in runs]
        if len(set(id(h) for h in holders)) != 1:
            stats["split"].append(cited)      # spans runs with different parents
            continue
        holder = holders[0]

        first_node, first_at = touched[0]
        last_node, last_at = touched[-1]
        head = (first_node.text or "")[:start - first_at]
        tail = (last_node.text or "")[end - last_at:]
        first_run, last_run = runs[0], runs[-1]
        template_rpr = first_run.find(q("rPr"))
        was_at = list(holder).index(first_run)

        # keep the text on either side of the citation, drop the rest of the span
        head_run = tail_run = fresh_tail = None
        if head:
            head_run = first_run
            set_text(first_node, head)
        if tail:
            if last_run is first_run:
                fresh_tail = copy.deepcopy(first_run)
                for node in fresh_tail.iter(q("t")):
                    set_text(node, tail)
            else:
                tail_run = last_run
                set_text(last_node, tail)
        for run in runs:
            if run is head_run or run is tail_run or parent_of[run] is not holder:
                continue
            if run in list(holder):
                holder.remove(run)

        if head_run is not None:
            at = list(holder).index(head_run) + 1
        elif tail_run is not None:
            at = list(holder).index(tail_run)
        else:
            at = was_at
        new_runs = field_runs(items, cited, [locator], note_index, links, template_rpr)
        if fresh_tail is not None:
            new_runs.append(fresh_tail)
        for offset, run in enumerate(new_runs):
            holder.insert(at + offset, run)
        stats["fields"] += 1


def serialize(root, original):
    """Serialize, keeping every namespace the original root declared.

    ElementTree emits xmlns declarations only for namespaces it sees used, which
    drops the ones mc:Ignorable still names; Word then rejects the whole part as
    schema-invalid. Merge, rather than replace, or the DrawingML prefixes that
    ElementTree hoists out of the image subtrees are lost instead.
    """
    out = ET.tostring(root, encoding="unicode")
    orig_root = re.match(r"\s*(?:<\?xml[^>]*\?>\s*)?(<[A-Za-z0-9:]+\b[^>]*>)", original).group(1)
    new_root = re.match(r"<[A-Za-z0-9:]+\b[^>]*>", out).group(0)
    have = dict(re.findall(r'xmlns:([A-Za-z0-9]+)="([^"]*)"', orig_root))
    extra = "".join(' xmlns:%s="%s"' % (p, u)
                    for p, u in re.findall(r'xmlns:([A-Za-z0-9]+)="([^"]*)"', new_root)
                    if p not in have)
    merged = orig_root[:-1].rstrip() + extra + ">"
    out = merged + out[len(new_root):]

    declared = set(re.findall(r"xmlns:([A-Za-z0-9]+)=", merged))
    assert not re.findall(r'[<"/](ns\d+):', out), "unregistered namespace prefixes"
    for ignorable in re.findall(r'mc:Ignorable="([^"]*)"', merged):
        assert not set(ignorable.split()) - declared, "mc:Ignorable names undeclared prefixes"
    used = set(re.findall(r"</([A-Za-z0-9]+):", out))
    assert used <= declared, "element prefixes not declared: %s" % (used - declared)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + out.encode("utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--bib", default=DEFAULT_BIB)
    ap.add_argument("--db", default=DEFAULT_DB,
                    help="zotero.sqlite, read to link citations to real library items")
    args = ap.parse_args()

    zin = zipfile.ZipFile(args.src)
    raw = {name: zin.read(name).decode("utf-8")
           for name in ("word/document.xml", "word/footnotes.xml")}
    for part in raw.values():
        for m in re.finditer(r'xmlns:([A-Za-z0-9]+)="([^"]+)"', part):
            ET.register_namespace(m.group(1), m.group(2))

    build = os.path.join(BASE, "docs", "_build")
    os.makedirs(build, exist_ok=True)
    index = load_bib(args.bib, os.path.join(build, "library-csl.json"))
    print("library: %d indexed entries" % sum(len(v) for v in index.values()))

    doc = ET.fromstring(raw["word/document.xml"])
    entries = bibliography_entries(doc)
    # export_docx's BIBENTRY_RE wants a single year, so an entry dated as a range
    # ("Nötscher, F. 1928-1930.") never parses and its citations stay dead text.
    # Key such an entry on the first year, which is what the footnotes cite.
    entries = [re.sub(r"\b((?:1[89]|20)\d{2})[–-](?:1[89]|20)\d{2}(?=\.)", r"\1", e)
               for e in entries]
    cmap, misses, _ = map_article_bib(entries, index)
    print("bibliography: %d entries typed, %d matched to the library" % (len(entries), len(cmap)))
    for why, text in misses:
        print("  unmatched (%s): %s" % (why, text))

    def resolve(names, year):
        fams = tuple(fam_key(n) for n in names)
        item = cmap.get((fams, year)) or cmap.get(((fams[0],), year))
        return [item] if item else []

    scratch = os.path.join(build, "zotero-snapshot.sqlite")
    index, groups, user_id = library_links(args.db, scratch)
    links = {}
    if index:
        for item in cmap.values():
            item_id, uri = resolve_link(item, index, groups, user_id)
            if item_id is not None:
                links[str(item["id"])] = (item_id, uri)
        print("library link-up: %d of %d cited works resolved to real Zotero items "
              "(userID %s)" % (len(links), len({str(i["id"]) for i in cmap.values()}), user_id))
    else:
        print("no zotero.sqlite at %s -- citations would be unlinked" % args.db)

    order = note_indices(doc)
    notes = ET.fromstring(raw["word/footnotes.xml"])
    stats = {"fields": 0, "unresolved": [], "split": []}
    for footnote in notes.iter(q("footnote")):
        note_index = order.get(footnote.get(q("id")), 0)
        for para in footnote.iter(q("p")):
            inject_into_paragraph(para, resolve, note_index, links, stats)

    print("inserted %d live citation fields" % stats["fields"])
    for cited in stats["unresolved"]:
        print("  left as text (no library item): %s" % cited)
    for cited in stats["split"]:
        print("  left as text (runs have different parents): %s" % cited)

    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename == "word/footnotes.xml":
                zout.writestr(info, serialize(notes, raw["word/footnotes.xml"]))
            elif info.filename == "[Content_Types].xml":
                ct = zin.read(info.filename).decode("utf-8")
                if "custom-properties+xml" not in ct:
                    ct = ct.replace("</Types>", CUSTOM_CT + "</Types>")
                zout.writestr(info, ct.encode("utf-8"))
            elif info.filename == "_rels/.rels":
                rels = zin.read(info.filename).decode("utf-8")
                if "custom-properties" not in rels:
                    rels = rels.replace(
                        "</Relationships>",
                        CUSTOM_REL % next_rel_id(rels) + "</Relationships>")
                zout.writestr(info, rels.encode("utf-8"))
            elif info.filename == "docProps/custom.xml":
                continue                                  # replaced below
            else:
                zout.writestr(info, zin.read(info.filename))
        zout.writestr("docProps/custom.xml", zotero_prefs_custom_xml().encode("utf-8"))

    with zipfile.ZipFile(args.out) as check:
        for info in check.infolist():
            if info.filename.endswith((".xml", ".rels")):
                ET.fromstring(check.read(info.filename))
        body = check.read("word/footnotes.xml").decode("utf-8")
        prefs = check.read("docProps/custom.xml").decode("utf-8")
    print("verified: %d ZOTERO_ITEM fields, %d ZOTERO_PREF chunks, every part parses"
          % (body.count("ZOTERO_ITEM"), prefs.count("ZOTERO_PREF_")))


if __name__ == "__main__":
    main()
