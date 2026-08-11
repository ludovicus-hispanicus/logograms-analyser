#!/usr/bin/env python3
"""Corpus-wide restoration sensitivity of the LDI.

analyze_restoration.py inspects five hand-picked astrological witnesses. This
sweeps the whole corpus and asks the question that matters for any claim built
on the index:

  1. How much of each text's countable material is editorial restoration?
  2. How far does a text's LDI move when restored spans are dropped?
  3. Does the headline diachronic arc (Old -> Middle -> Neo) survive counting
     only what is physically preserved on the tablets?

(3) is the real test. Per-text noise is tolerable if the aggregate signal the
argument rests on is unchanged; it is not tolerable if the arc is partly an
artifact of how much editors reconstructed in each period -- and later tablets
are, in general, better preserved and more heavily parallel-restored, so the
bias plausibly runs with the trend rather than against it.

Run from the repo root:  py -3 scripts/restoration_sweep.py
Writes docs/restoration-sweep.csv (one row per text).
"""
import os
import sys
import warnings

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from compute_ratios import load_local_data, ldi, PERIOD_ORDER  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frame(preserved):
    return pd.DataFrame(load_local_data(os.path.join(ROOT, "data"),
                                        preserved_only=preserved))


print("loading corpus (full and preserved-only)...")
full = frame(False)
pres = frame(True)

# --- per text -------------------------------------------------------------
rows = []
for fn in sorted(full["filename"].unique()):
    f_sub = full[full["filename"] == fn]
    p_sub = pres[pres["filename"] == fn]
    f_ldi, _, f_tok = ldi(f_sub)
    p_ldi, _, p_tok = ldi(p_sub)
    if f_tok == 0:
        continue
    rows.append({
        "filename": fn,
        "period": f_sub["period"].iloc[0],
        "genre": f_sub["genre"].iloc[0],
        "tokens_full": f_tok,
        "tokens_preserved": p_tok,
        "restored_share": 1 - (p_tok / f_tok) if f_tok else 0.0,
        "ldi_full": f_ldi,
        "ldi_preserved": p_ldi,
        "delta": p_ldi - f_ldi,
    })
df = pd.DataFrame(rows)
df["abs_delta"] = df["delta"].abs()

out = os.path.join(ROOT, "docs", "restoration-sweep.csv")
df.to_csv(out, index=False)

# --- summary --------------------------------------------------------------
print("\n" + "=" * 72)
print("PER-TEXT RESTORATION SENSITIVITY  (%d texts)" % len(df))
print("=" * 72)
print("restored share of countable tokens:")
print("   median %.1f%%   mean %.1f%%   max %.1f%%  (%s)" % (
    100 * df.restored_share.median(), 100 * df.restored_share.mean(),
    100 * df.restored_share.max(), df.loc[df.restored_share.idxmax(), "filename"]))
print("\n|LDI shift| when restored material is dropped:")
print("   median %.3f   mean %.3f   max %.3f  (%s)" % (
    df.abs_delta.median(), df.abs_delta.mean(),
    df.abs_delta.max(), df.loc[df.abs_delta.idxmax(), "filename"]))
for t in (0.02, 0.05, 0.10, 0.20):
    n = (df.abs_delta > t).sum()
    print("   texts shifting more than %.2f : %3d  (%4.1f%%)" % (t, n, 100 * n / len(df)))

print("\ncorrelation(restored share, |LDI shift|) = %.3f" %
      df.restored_share.corr(df.abs_delta))

print("\n--- 10 most restoration-sensitive texts ---")
top = df.nlargest(10, "abs_delta")[
    ["filename", "period", "restored_share", "ldi_full", "ldi_preserved", "delta"]]
for _, r in top.iterrows():
    print("  %-26s %-14s restored %4.1f%%  %.3f -> %.3f  (%+.3f)" % (
        r.filename[:26], r.period[:14], 100 * r.restored_share,
        r.ldi_full, r.ldi_preserved, r.delta))

# --- does the diachronic arc survive? ------------------------------------
print("\n" + "=" * 72)
print("THE HEADLINE ARC, POOLED PER PERIOD")
print("=" * 72)
print("  %-16s %8s %8s %9s %10s" % ("period", "full", "preserved", "delta", "restored%"))
for p in PERIOD_ORDER:
    f_sub = full[full["period"] == p]
    p_sub = pres[pres["period"] == p]
    if f_sub.empty:
        continue
    f_ldi, _, f_tok = ldi(f_sub)
    p_ldi, _, p_tok = ldi(p_sub)
    print("  %-16s %8.3f %8.3f %+9.3f %9.1f%%" % (
        p, f_ldi, p_ldi, p_ldi - f_ldi,
        100 * (1 - p_tok / f_tok) if f_tok else 0))

print("\nwrote %s" % os.path.relpath(out, ROOT))
