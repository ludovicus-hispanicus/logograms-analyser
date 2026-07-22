#!/usr/bin/env python3
"""Regenerate docs/catalogue-of-sources.md from the corpus frontmatter.

Groups every manuscript by discipline -> period into a "Sources analysed" list
and an "Excluded sources" list. Run from the repo root:  python scripts/build_catalogue.py
"""
import os, re, collections

ROOT = "data"
OUT = "docs/catalogue-of-sources.md"

def fm(t):
    m = re.match(r'^---\s*\n(.*?)\n---', t, re.S)
    return m.group(1) if m else ""

def get(F, k):
    m = re.search(r'^' + re.escape(k) + r':\s*(.*)$', F, re.M)
    return m.group(1).strip() if m else ""

def excl_reason(F):
    m = re.search(r'^exclude:\s*true\s*#\s*(.*)$', F, re.M)
    return m.group(1).strip() if m else ""

def cell(s):
    return (s or "").replace("|", "/").replace("\n", " ").strip() or "—"

def sigfmt(s):
    m = re.match(r'^([A-Za-z]{1,6})\.(\d.*)$', s)   # standard sigla LETTERS.NUMBER -> "LETTERS NUMBER"
    return f"{m.group(1)} {m.group(2)}" if m else s

DISC = {"astrological omens": "Celestial / Astrological (Enūma Anu Enlil)",
        "terrestrial omens": "Terrestrial (Šumma Ālu)",
        "izbu omens": "Teratological (Šumma Izbu)",
        "extispicy omens": "Extispicy (bārûtu)",
        "diagnostic omens": "Diagnostic / Medical (Sakikkû)",
        "extispicy model": "Extispicy models & orientation texts",
        "prayer": "Other genres (comparanda)", "incantation": "Other genres (comparanda)",
        "Unspecified": "Unspecified"}
DORD = ["Celestial / Astrological (Enūma Anu Enlil)", "Terrestrial (Šumma Ālu)",
        "Teratological (Šumma Izbu)", "Extispicy (bārûtu)", "Diagnostic / Medical (Sakikkû)",
        "Extispicy models & orientation texts", "Other genres (comparanda)", "Unspecified"]
PORD = {"Old Babylonian": 1, "Late Old Babylonian": 2, "Early Middle Babylonian": 3,
        "Middle Babylonian": 4, "Middle Assyrian": 5, "Neo-Assyrian": 6,
        "Neo-Assyrian / Late Babylonian": 7, "Neo-Babylonian": 8, "Neo Babylonian": 8,
        "Late Babylonian": 9}
pnorm = lambda p: "Neo-Babylonian" if p == "Neo Babylonian" else p

rows = []
for dp, _, fs in os.walk(ROOT):
    for f in sorted(fs):
        if not f.endswith(".txt"):
            continue
        F = fm(open(os.path.join(dp, f), encoding="utf-8").read())
        rows.append(dict(sig=sigfmt(f[:-4]), disc=DISC.get(get(F, "genre"), get(F, "genre")),
                         period=pnorm(get(F, "period")),
                         pub=get(F, "publication") or get(F, "source") or get(F, "edition"),
                         prov=get(F, "provenance"),
                         excl=get(F, "exclude").startswith("true"), reason=excl_reason(F)))
used = [r for r in rows if not r["excl"]]
supp = [r for r in rows if r["excl"] and "supplementary" in r["reason"].lower()]
excluded = [r for r in rows if r["excl"] and "supplementary" not in r["reason"].lower()]
pkey = lambda r: (PORD.get(r["period"], 99), r["sig"].lower())
dkey = lambda d: DORD.index(d) if d in DORD else 99

L = ["# Catalogue of Sources\n",
     f"*Auto-generated from the corpus frontmatter ({len(rows)} manuscripts: {len(used)} analysed, "
     f"{len(supp)} supplementary, {len(excluded)} excluded), grouped by discipline and period. "
     "The Publication / edition column "
     "reproduces the recorded publication and excavation numbers verbatim; “—” marks an entry whose "
     "publication reference is not yet recorded in the source file.*\n",
     "\n---\n\n## Part 1 — Sources analysed\n"]
byd = collections.defaultdict(list)
for r in used:
    byd[r["disc"]].append(r)
for d in sorted(byd, key=dkey):
    L.append(f"\n### {d}\n")
    byp = collections.defaultdict(list)
    for r in byd[d]:
        byp[r["period"]].append(r)
    for per in sorted(byp, key=lambda x: PORD.get(x, 99)):
        L += [f"\n**{per}**  ({len(byp[per])})\n",
              "| Museum no. / siglum | Publication / edition | Provenance |", "|---|---|---|"]
        for r in sorted(byp[per], key=pkey):
            L.append(f"| {cell(r['sig'])} | {cell(r['pub'])} | {cell(r['prov'])} |")
        L.append("")

L.append("\n---\n\n## Part 2 — Excluded sources\n")
byd = collections.defaultdict(list)
for r in excluded:
    byd[r["disc"]].append(r)
for d in sorted(byd, key=dkey):
    L += [f"\n### {d}\n",
          "| Museum no. / siglum | Period | Publication / edition | Reason for exclusion |",
          "|---|---|---|---|"]
    for r in sorted(byd[d], key=pkey):
        L.append(f"| {cell(r['sig'])} | {cell(r['period'])} | {cell(r['pub'])} | {cell(r['reason'])} |")
    L.append("")

L.append("\n---\n\n## Part 3 — Supplementary sources\n")
L.append("*Held out of the main LDI counts, but digitized and available in the accompanying "
         "app (e.g. the further KAL 5 extispicy witnesses of Heeßel 2012).*\n")
byd = collections.defaultdict(list)
for r in supp:
    byd[r["disc"]].append(r)
for d in sorted(byd, key=dkey):
    L.append(f"\n### {d}\n")
    byp = collections.defaultdict(list)
    for r in byd[d]:
        byp[r["period"]].append(r)
    for per in sorted(byp, key=lambda x: PORD.get(x, 99)):
        L += [f"\n**{per}**  ({len(byp[per])})\n",
              "| Museum no. / siglum | Publication / edition | Provenance |", "|---|---|---|"]
        for r in sorted(byp[per], key=pkey):
            L.append(f"| {cell(r['sig'])} | {cell(r['pub'])} | {cell(r['prov'])} |")
        L.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(L))
print(f"wrote {OUT}: {len(used)} analysed, {len(supp)} supplementary, {len(excluded)} excluded")
