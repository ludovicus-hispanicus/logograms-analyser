#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest the KAL 5 (Heeßel 2012) Opferschau tablets as SUPPLEMENTARY extispicy texts.

Reads the transliterations straight out of the KAL 5 PDF, remaps the special
Assyriological font to Unicode, strips the apparatus/translation, and writes one
file per tablet into a separate top-level data/kal5/ folder with `exclude: true`
(so they are available in the app and Sources catalogue but NOT folded into the
main LDI, and kept out of the period/genre corpus tree).

Tablets already hand-curated in data/ (the 27 main-corpus witnesses) are skipped,
as is VAT 10535 (too damaged). Idempotent: re-running overwrites the kal5/ files.
Run from the repo root:  py scripts/ingest_kal5.py
"""
import os, re, csv, glob
from pypdf import PdfReader

PDF = r'C:\Users\wende\Downloads\Heeßel 2012 Divinatorische Texte II. Opferschau-Omina KAL 5.pdf'
CSV = "docs/kal5-ldi-by-tradition.csv"

# --- font glyph remap (verified against known Akkadian; see prototype) ---
GLYPH = {'·': 'š', '◊': 'ṣ', '¿': 'ḫ', '∞': 'Š', '®': 'ā', '∂': 'ē', '†': 'ṭ',
         'ø': 'Ḫ', '¬': 'ā', '«': '⸢', '»': '⸣'}   # «» are mis-mapped half-brackets
def remap(s): return "".join(GLYPH.get(c, c) for c in s)

# German date prefix -> (fine period label, data/ period folder)
def period_info(date):
    d = (date or "").lower()
    if d.startswith("frühneuassyris") or d.startswith("neuassyrisch"):
        return "Neo-Assyrian", "new"
    if d.startswith("mittelassyrisc"):
        return "Middle Assyrian", "middle"
    if d.startswith("frühmittelbaby"):
        return "Early Middle Babylonian", "middle"
    if d.startswith("mittelbabyloni"):
        return "Middle Babylonian", "middle"
    return None, None   # spätmittelassyrisch (VAT 10535) etc. -> caller skips

TRAD = {"Ass": "Assyrian", "Bab": "Babylonian"}

def norm(sig):
    """Normalized siglum key for de-dup / skip matching (drop punctuation/case)."""
    return re.sub(r'[^A-Za-z0-9]', '', sig).upper()

def primary_siglum(tablet):
    """First siglum of a (possibly joined) tablet string: 'VAT 9949 (+) VAT 11051' -> 'VAT 9949'."""
    t = tablet.strip()
    t = re.split(r'\s*\(|\s*\+|\s*/|\s*=|\s\(\+\)', t)[0]
    return re.sub(r'\s+', ' ', t).strip()

def filename_for(prim):
    return re.sub(r'\.+', '.', prim.replace(' ', '.')) + ".txt"

# --- 1. CSV: Nr -> metadata ---
meta = {}
with open(CSV, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        meta[int(row["Nr"])] = row

# --- 2. existing curated sigla (skip these) ---
existing = set()
for p in glob.glob("data/**/*.txt", recursive=True):
    if os.sep + "kal5" + os.sep in p or "/kal5/" in p.replace("\\", "/"):
        continue                       # our own supplementary output — regenerate, don't skip
    existing.add(norm(os.path.basename(p)[:-4]))

# --- 3. extract + segment the PDF (same logic as kal5_ldi_scan.py) ---
reader = PdfReader(PDF)
pages = []
for pg in reader.pages:
    try: pages.append(pg.extract_text(extraction_mode='layout') or "")
    except Exception: pages.append("")
lines = "\n".join(pages).splitlines()
hdr = re.compile(r'^\s*(\d{1,3})\)\s+([A-ZÄ].{2,})$')
units, cur = [], None
for ln in lines:
    m = hdr.match(ln)
    if m and re.search(r'\b(VAT|AO|A|K|Ass|BM|Sm|Rm|N|MS|Bu|Th|DT|VA)\b|[0-9]', m.group(2)[:30]):
        if cur: units.append(cur)
        cur = {"nr": int(m.group(1)), "body": []}
    elif cur is not None:
        cur["body"].append(ln)
if cur: units.append(cur)
seen = {}
for u in units:
    if u["nr"] not in seen and len(u["body"]) > 4:
        seen[u["nr"]] = u
units = [seen[k] for k in sorted(seen)]

FURNITURE = re.compile(r'Heeßel-KAL|Divinatorische Texte|Opferschau-Omina|\.qxd'
                       r'|^\s*\d{1,3}\s*$|^\s*_+\s*$'
                       r'|^\s*\((?:Rand|abgebrochen|leer|Lücke|Kolophon)\)\s*$'
                       r'|^\s*Spuren\s*$')
# German editorial notes embedded mid-line (would otherwise count as phonetic tokens)
GERMAN_EDIT = re.compile(r'\s*\((?:Rasur|abgebrochen|Lücke|Spuren|leer|Kolophon)\)\s*')

def transliteration(body):
    """Slice out the Transliteration block, strip furniture, remap glyphs, format as ATF-ish lines."""
    i0 = next((i for i, l in enumerate(body) if 'Transliteration:' in l), None)
    i1 = next((i for i, l in enumerate(body) if 'Übersetzung:' in l), None)
    if i0 is None:
        return []
    block = body[i0 + 1: (i1 if i1 else len(body))]
    out, sec = [], None
    for l in block:
        if not l.strip() or FURNITURE.search(l):
            continue
        l = GERMAN_EDIT.sub(' ', remap(re.sub(r'\s{2,}', ' ', l.strip()))).strip()
        if not l:
            continue
        m = re.match(r'^(Vs\.|Rs\.)\s+(.*)$', l)
        if m:
            newsec = "obverse" if m.group(1) == "Vs." else "reverse"
            if newsec != sec:
                out.append(f"@{newsec}"); sec = newsec
            l = m.group(2)
        elif sec is None:
            out.append("@obverse"); sec = "obverse"
        m2 = re.match(r"^(?:[IVX]+\s+)?(\d+['’]?)\s+(.*)$", l)
        out.append(f"{m2.group(1)}. {m2.group(2)}" if m2 else l)
    return out

# --- 4. write files ---
created, skipped_existing, skipped_other = [], [], []
for u in units:
    nr = u["nr"]
    if nr not in meta:
        continue                       # false-positive header / sub-part not in the edition table
    row = meta[nr]
    prim = primary_siglum(row["tablet"])
    if norm(prim) in existing:
        skipped_existing.append(prim); continue
    period, folder = period_info(row["date"])
    if not period:
        skipped_other.append(f"{prim} (period {row['date'].strip()})"); continue
    atf = transliteration(u["body"])
    if not any(re.search(r'[A-Za-zš]', l) for l in atf):
        skipped_other.append(f"{prim} (no transliteration)"); continue
    trad = TRAD.get(row["tradition"], "")
    full = re.sub(r'\s*\(Kopie.*$|\s*\(Photo.*$|\s*\(KAR.*$|\s+S\..*$', '', row["tablet"]).strip()
    fm = ["---", "genre: extispicy omens", f"period: {period}", "provenance: Assur"]
    if trad: fm.append(f"tradition: {trad}")
    fm += ["counting: line",
           f"publication: Heeßel 2012, KAL 5 no. {nr} ({full})",
           "exclude: true   # KAL 5 supplementary witness (Heeßel 2012); held out of the "
           "main extispicy corpus, available in the app",
           "source_note: Transliteration auto-extracted from the KAL 5 PDF (Heeßel 2012) and "
           "glyph-remapped (·→š ◊→ṣ ¿→ḫ "
           "∞→Š ®→ā ∂→ē †→ṭ); "
           f"apparatus/translation removed; not hand-collated. Reference LDI {row['LDI']} "
           f"on {row['tokens']} tokens.",
           "---", ""]
    dest = os.path.join("data", "kal5", filename_for(prim))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(fm) + "\n".join(atf) + "\n")
    created.append((dest, period))

print(f"created: {len(created)}")
from collections import Counter
for per, n in Counter(p for _, p in created).most_common():
    print(f"   {per}: {n}")
print(f"skipped (already curated): {len(skipped_existing)}")
print(f"skipped (other): {len(skipped_other)} -> {skipped_other}")
