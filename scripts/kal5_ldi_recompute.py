# -*- coding: utf-8 -*-
"""Recompute the KAL 5 LDI from the INGESTED data files (clean, glyph-remapped,
apparatus-stripped) instead of the raw PDF, and compare to the original scan.

Uses the same token definition as scripts/kal5_ldi_scan.py (app.get_token_type:
uppercase -> logogram, lowercase -> phonetic; LDI = log / (log + phon)), so the
only thing that changes is the text quality. Writes an old-vs-new comparison and,
with --write, refreshes docs/kal5-ldi-by-tradition.csv.

Run:  py -3.12 scripts/kal5_ldi_recompute.py [--write]
"""
import os, re, csv, sys, glob
from collections import defaultdict

# --- borrow get_token_type from app.py (real streamlit, no page config) ---
import streamlit as st
st.set_page_config = lambda *a, **k: None
src = open("app.py", encoding="utf-8").read().splitlines()
end = max(i for i, l in enumerate(src) if 'return "other"' in l)  # end of get_token_type
ns = {}
exec("\n".join(src[:end + 1]), ns)
get_token_type = ns['get_token_type']

SKIP = {"Vs", "Rs", "Seite", "KI.MIN", "MIN", "DIŠ.MIN"}

def score(path):
    """LDI (log/(log+phon)) and token count for one ingested transliteration file."""
    log = tot = 0
    body = open(path, encoding="utf-8").read()
    body = re.split(r'^---\s*$', body, flags=re.M)[-1]          # drop YAML frontmatter
    for line in body.splitlines():
        # Only numbered transliteration lines ("12. …", "3'. …"); skip @structure,
        # #tr.en / #note comments, $-lines and blanks.
        if not re.match(r"^\s*\d+['’]?\.\s", line):
            continue
        line = re.sub(r"^\s*\d+['’]?\.\s*", "", line)           # strip "12. " line number
        line = line.replace("{", "").replace("}", "")           # det markers -> attach to sign
        for t in re.split(r'[\s|]+', line):
            t = t.strip("[]()<>#!?:.")
            if not t or re.fullmatch(r"\d+['’]?\.?", t) or re.fullmatch(r"[x.\-–…'’]+", t):
                continue
            if t in SKIP or t.rstrip('.!') in ('Vs', 'Rs', 'Seite'):
                continue
            tt = get_token_type(t)
            if tt == 'other':
                continue
            log += (tt == 'logogram'); tot += 1
    return (log / tot if tot else 0.0), tot

def norm(s):
    return re.sub(r'[^A-Za-z0-9]', '', s).upper()

def primary_siglum(tablet):
    t = re.split(r'\s*\(|\s*\+|\s*/|\s*=|\s\(\+\)', tablet.strip())[0]
    return re.sub(r'\s+', ' ', t).strip()

# index every data file by normalized siglum
byname = {}
for p in glob.glob("data/**/*.txt", recursive=True):
    byname.setdefault(norm(os.path.basename(p)[:-4]), p)

rows = list(csv.DictReader(open("docs/kal5-ldi-by-tradition.csv", encoding="utf-8")))
out, missing = [], []
for r in rows:
    prim = primary_siglum(r["tablet"])
    path = byname.get(norm(prim))
    if not path:
        missing.append(prim); continue
    new_ldi, new_tok = score(path)
    r["_new_ldi"], r["_new_tok"], r["_path"] = new_ldi, new_tok, path
    out.append(r)

print(f"rescored {len(out)} tablets  |  not found: {len(missing)} {missing}\n")
print(f'{"Nr":>3} {"tablet":22} {"per":4} {"trad":4} {"oldLDI":>6} {"newLDI":>6} {"Δ":>6} {"oldTok":>6} {"newTok":>6}')
big = []
for r in sorted(out, key=lambda r: int(r["Nr"])):
    old = float(r["LDI"]); d = r["_new_ldi"] - old
    if abs(d) >= 0.10:
        big.append((r["tablet"][:22], old, r["_new_ldi"], d))
    print(f'{r["Nr"]:>3} {primary_siglum(r["tablet"])[:22]:22} {r["period"]:4} {r["tradition"]:4} '
          f'{old:6.3f} {r["_new_ldi"]:6.3f} {d:+6.3f} {r["tokens"]:>6} {r["_new_tok"]:>6}')

# aggregate by period x tradition, old vs new (mean of per-text LDI)
def agg(key):
    b = defaultdict(list)
    for r in out:
        cat = 'Bab(copy)' if str(r["babylon_copy"]).strip().lower() == 'true' else r["tradition"]
        b[(r["period"], cat)].append((float(r["LDI"]), r["_new_ldi"]))
    return b

print("\n=== mean LDI by period × tradition (old → new) ===")
b = agg(None)
for k in sorted(b, key=lambda k: (k[0] or 'zz', k[1] or 'zz')):
    v = b[k]
    mo = sum(x[0] for x in v) / len(v); mn = sum(x[1] for x in v) / len(v)
    print(f'  {str(k):28}  n={len(v):3}   {mo:.3f} → {mn:.3f}   (Δ {mn-mo:+.3f})')

print(f"\n=== tablets whose LDI moved ≥0.10 ({len(big)}) ===")
for name, o, n, d in sorted(big, key=lambda x: -abs(x[3])):
    print(f'  {name:24} {o:.3f} → {n:.3f}  ({d:+.3f})')

if "--write" in sys.argv:
    fields = ["Nr", "tablet", "date", "period", "tradition", "babylon_copy", "LDI", "tokens"]
    with open("docs/kal5-ldi-by-tradition.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in sorted(out, key=lambda r: int(r["Nr"])):
            w.writerow({**{k: r[k] for k in fields},
                        "LDI": f"{r['_new_ldi']:.3f}", "tokens": r["_new_tok"]})
    print("\nwrote refreshed docs/kal5-ldi-by-tradition.csv")
else:
    print("\n(dry run — pass --write to refresh docs/kal5-ldi-by-tradition.csv)")
