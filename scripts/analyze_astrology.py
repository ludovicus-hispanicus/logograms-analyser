"""Astrology-focused LDI analysis (uses the loader from compute_ratios).

Run from the repo root: py -3 scripts/analyze_astrology.py
"""
import os
import sys

import pandas as pd

# compute_ratios lives at the repo root, one level up from scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from compute_ratios import load_local_data, ldi, LOGOGRAM_PARTICLES, PERIOD_ORDER  # noqa: E402

ASTRO_GENRES = {"astrological omens", "astrology omens", "celestial"}

anns = load_local_data("data")
df = pd.DataFrame(anns)
df['genre_norm'] = df['genre'].str.strip().str.lower()
astro = df[df['genre_norm'].isin(ASTRO_GENRES)].copy()
rest = df[~df['genre_norm'].isin(ASTRO_GENRES)].copy()

# Preserved-only variant: editor's reconstructions ('[ ... ]') dropped, so the
# LDI reflects only what survives on the tablet.
anns_p = load_local_data("data", preserved_only=True)
dfp = pd.DataFrame(anns_p)
dfp['genre_norm'] = dfp['genre'].str.strip().str.lower()
astro_p = dfp[dfp['genre_norm'].isin(ASTRO_GENRES)].copy()

print("=" * 78)
print("ASTROLOGICAL OMENS — LDI BY PERIOD (incl. / excl. opening particle)")
print("=" * 78)
print(f"{'Period':<16} {'LDI':>7} {'LDI-part':>9} {'Logs':>7} {'Tokens':>8} {'Omens':>7} {'Files':>6}")
for period in PERIOD_ORDER:
    p = astro[astro['period'] == period]
    if p.empty:
        print(f"{period:<16} {'—':>7}  (no astrological data in corpus)")
        continue
    r, lg, tot = ldi(p)
    rx, _, _ = ldi(p, exclude_particles=True)
    omens = p.groupby(['filename', 'omen_id']).ngroups
    print(f"{period:<16} {r:>7.3f} {rx:>9.3f} {lg:>7} {tot:>8} {omens:>7} {p['filename'].nunique():>6}")

print()
print("=" * 78)
print("ASTROLOGY vs OTHER DISCIPLINES, BY PERIOD")
print("=" * 78)
print(f"{'Period':<16} {'Astrology':>10} {'Extispicy':>10} {'Terrestrial':>12} {'Diagnostic':>11}")
for period in PERIOD_ORDER:
    row = [period]
    for genres in (ASTRO_GENRES, {'extispicy omens'}, {'terrestrial omens'}, {'diagnostic omens'}):
        sub = df[(df['period'] == period) & (df['genre_norm'].isin({g.lower() for g in genres}))]
        row.append(f"{ldi(sub)[0]:.3f}" if not sub.empty else "—")
    print(f"{row[0]:<16} {row[1]:>10} {row[2]:>10} {row[3]:>12} {row[4]:>11}")

print()
print("=" * 78)
print("ASTROLOGICAL TABLETS — PER FILE")
print("=" * 78)
print(f"{'Period':<16} {'File':<18} {'LDI':>7} {'LDI-part':>9} {'Tokens':>8} {'Omens':>7}")
for period in PERIOD_ORDER:
    p = astro[astro['period'] == period]
    for fn in sorted(p['filename'].unique()):
        sub = p[p['filename'] == fn]
        r, _, tot = ldi(sub)
        rx, _, _ = ldi(sub, exclude_particles=True)
        omens = sub['omen_id'].nunique()
        print(f"{period:<16} {fn:<18} {r:>7.3f} {rx:>9.3f} {tot:>8} {omens:>7}")

print()
print("=" * 78)
print("WITH vs WITHOUT RECONSTRUCTION (astrology, per file)")
print("=" * 78)
print("'full' counts editorial restorations [ ... ]; 'pres.' drops them, keeping")
print("only signs physically on the tablet (damaged-but-legible '#' kept).")
print()
print(f"{'Period':<14} {'File':<18} {'full':>6} {'pres.':>6} {'Δ':>7} {'restored%':>10}")
for period in PERIOD_ORDER:
    p = astro[astro['period'] == period]
    for fn in sorted(p['filename'].unique()):
        rf, _, tf = ldi(astro[astro['filename'] == fn])
        rp, _, tp = ldi(astro_p[astro_p['filename'] == fn])
        share = (tf - tp) / tf if tf else 0.0
        print(f"{period:<14} {fn:<18} {rf:>6.3f} {rp:>6.3f} {rp-rf:>+7.3f} {share:>9.0%}")
print()
print(f"{'Period total':<33} {'full':>6} {'pres.':>6} {'Δ':>7} {'restored%':>10}")
for period in PERIOD_ORDER:
    p = astro[astro['period'] == period]
    if p.empty: continue
    rf, _, tf = ldi(p)
    rp, _, tp = ldi(astro_p[astro_p['period'] == period])
    share = (tf - tp) / tf if tf else 0.0
    print(f"{period:<33} {rf:>6.3f} {rp:>6.3f} {rp-rf:>+7.3f} {share:>9.0%}")

print()
print("=" * 78)
print("PER-OMEN LDI DISTRIBUTION (astrology, omens with >= 3 countable tokens)")
print("=" * 78)
per_omen = []
for (fn, oid), sub in astro.groupby(['filename', 'omen_id']):
    r, lg, tot = ldi(sub)
    if tot >= 3:
        per_omen.append({'period': sub['period'].iloc[0], 'file': fn, 'omen': oid, 'ldi': r, 'tokens': tot})
po = pd.DataFrame(per_omen)
for period in PERIOD_ORDER:
    p = po[po['period'] == period]
    if p.empty: continue
    print(f"{period:<16} n={len(p):<4} mean={p['ldi'].mean():.3f}  median={p['ldi'].median():.3f}  "
          f"min={p['ldi'].min():.3f}  max={p['ldi'].max():.3f}  share>=0.5: {(p['ldi'] >= 0.5).mean():.0%}")

print()
print("=" * 78)
print("MOST FREQUENT LOGOGRAMS IN ASTROLOGICAL OMENS (top 20, per period)")
print("=" * 78)
for period in PERIOD_ORDER:
    p = astro[(astro['period'] == period) & (astro['type'] == 'logogram')]
    if p.empty: continue
    top = p['token'].value_counts().head(20)
    print(f"\n{period}:")
    print("  " + ", ".join(f"{t} ({c})" for t, c in top.items()))
