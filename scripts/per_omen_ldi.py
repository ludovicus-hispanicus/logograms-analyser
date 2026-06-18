#!/usr/bin/env python
"""Compute the LDI for EACH omen in a folder (or single corpus path).

Reports, per omen, both indices (see docs/ldi-sign-level.md):
  bin   = old WORD-level binary LDI (a space-token is logographic if it holds
          any uppercase sign; phonetic complements absorbed; determinatives
          dilute the denominator).
  macro = graded per-WORD LDI: mean of each word's logogram-sign fraction, so a
          logogram+complement word lands between 0 and 1 (e.g. ŠIR-MEŠ-šu₂ = 2/3).
  micro = strict per-SIGN LDI: logogram / (logogram + phonetic) signs pooled.
And the three-state word composition: pure-logographic / mixed / syllabic.

Akkadian and Sumerian (%sux) omens are reported in separate, flagged blocks.

Usage:
    python scripts/per_omen_ldi.py data/new/astrology/EAE55
    python scripts/per_omen_ldi.py data/new/astrology/EAE57 --csv out.csv
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compute_ratios as c


def omen_language(sub):
    return "sumerian" if (sub["language"] == "sumerian").mean() > 0.5 else "akkadian"


def build_rows(df, sdf):
    """One row per omen, in first-seen order, with binary + graded metrics."""
    order = sdf.groupby(["filename", "omen_id"])["index"].min().sort_values()
    rows = []
    for (fn, oid) in order.index:
        wsub = df[(df.filename == fn) & (df.omen_id == oid)]
        ssub = sdf[(sdf.filename == fn) & (sdf.omen_id == oid)]
        g = c.graded_ldi(ssub)
        rows.append({
            "file": fn, "omen": oid, "language": omen_language(ssub),
            "bin": round(c.ldi(wsub)[0], 3),
            "macro": round(g["macro"], 3), "micro": round(g["micro"], 3),
            "pure": g["pure"], "mixed": g["mixed"], "syll": g["syllabic"],
        })
    return rows


def print_block(title, rows, sdf_sub, multi_file):
    if not rows:
        return
    print(f"  [{title}]  {len(rows)} omens")
    print(f"  {'omen':<10}{'bin':>7}{'macro':>7}{'micro':>7}{'pure':>6}{'mix':>5}{'syl':>5}")
    for r in rows:
        label = r["omen"] if not multi_file else f"{r['file']}:{r['omen']}"
        print(f"  {str(label):<10}{r['bin']:>7.3f}{r['macro']:>7.3f}{r['micro']:>7.3f}"
              f"{r['pure']:>6}{r['mixed']:>5}{r['syll']:>5}")
    g = c.graded_ldi(sdf_sub)
    out = pd.DataFrame(rows)
    print(f"  {'-'*45}")
    print(f"  {'pooled':<10}{'':>7}{g['macro']:>7.3f}{g['micro']:>7.3f}"
          f"{g['pure']:>6}{g['mixed']:>5}{g['syllabic']:>5}")
    print(f"  per-omen macro: mean={out.macro.mean():.3f} median={out.macro.median():.3f} "
          f"min={out.macro.min():.3f} max={out.macro.max():.3f}")
    tot = g['pure'] + g['mixed'] + g['syllabic']
    if tot:
        print(f"  word composition: pure-log {g['pure']/tot:.0%} / mixed {g['mixed']/tot:.0%} "
              f"/ syllabic {g['syllabic']/tot:.0%}  ({g['log']} log, {g['phon']} phon, {g['det']} det signs)\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = args[0] if args else "data/new/astrology/EAE55"
    csv_path = sys.argv[sys.argv.index("--csv") + 1] if "--csv" in sys.argv else None

    df = pd.DataFrame(c.load_local_data(folder))
    sdf = pd.DataFrame(c.load_local_signs(folder))
    if sdf.empty:
        print(f"No annotations found in {folder}")
        return

    rows = build_rows(df, sdf)
    multi_file = sdf.filename.nunique() > 1
    akk = [r for r in rows if r["language"] == "akkadian"]
    sux = [r for r in rows if r["language"] == "sumerian"]

    print(f"PER-OMEN LDI for: {folder}  (bin=old word-level | macro=per-word | micro=per-sign)\n")
    print_block("AKKADIAN", akk, sdf[sdf.language == "akkadian"], multi_file)
    print_block("SUMERIAN (%sux)", sux, sdf[sdf.language == "sumerian"], multi_file)

    if csv_path:
        pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8")
        print(f"  wrote {csv_path}")


if __name__ == "__main__":
    main()
