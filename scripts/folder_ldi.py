#!/usr/bin/env python
"""Pooled LDI for all .txt files in a folder, reporting both the old word-level
binary LDI and the new graded sign-level metrics (see docs/ldi-sign-level.md).

  bin   = old word-level binary LDI (raw / excl-particle / preserved-only)
  macro = graded per-word LDI (mean of per-word logogram-sign fractions)
  micro = strict per-sign LDI (logogram / (logogram + phonetic) signs)
  word composition = pure-logographic / mixed / syllabic

Akkadian and Sumerian (%sux) are pooled separately.

Usage:  python scripts/folder_ldi.py data/new/diagnostic/tablet3
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compute_ratios as c


def block(label, df, dfp, sdf):
    if sdf.empty:
        return
    r = c.ldi(df); rx = c.ldi(df, True); rp = c.ldi(dfp, True)
    rm = c.ldi(df, monogram_as_log=True)
    g = c.graded_ldi(sdf)
    gm = c.graded_ldi(sdf, monogram_as_log=True)
    omens = sdf.groupby(['filename', 'omen_id']).ngroups
    tot = g['pure'] + g['mixed'] + g['syllabic']
    print(f'  [{label}]  omens={omens}')
    print(f'    bin   LDI = {r[0]:.3f}  (excl-particle {rx[0]:.3f}, preserved-only {rp[0]:.3f})')
    print(f'    macro LDI = {g["macro"]:.3f}   micro LDI = {g["micro"]:.3f}')
    print(f'    +monogram (ina/ana as logographic): bin {rm[0]:.3f}, macro {gm["macro"]:.3f}, micro {gm["micro"]:.3f}')
    if tot:
        print(f'    words: pure-log {g["pure"]/tot:.0%} / mixed {g["mixed"]/tot:.0%} '
              f'/ syllabic {g["syllabic"]/tot:.0%}   '
              f'(signs: {g["log"]} log, {g["phon"]} phon, {g["det"]} det)')


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else 'data/new/diagnostic/tablet3'
    df = pd.DataFrame(c.load_local_data(folder))
    dfp = pd.DataFrame(c.load_local_data(folder, preserved_only=True))
    sdf = pd.DataFrame(c.load_local_signs(folder))
    if sdf.empty:
        print(f'No annotations found in {folder}')
        return

    print(f'POOLED LDI for folder: {folder}   (files={sdf.filename.nunique()})')
    block('AKKADIAN', df[df.language == 'akkadian'], dfp[dfp.language == 'akkadian'],
          sdf[sdf.language == 'akkadian'])
    if (sdf.language == 'sumerian').any():
        block('SUMERIAN (%sux)', df[df.language == 'sumerian'],
              dfp[dfp.language == 'sumerian'], sdf[sdf.language == 'sumerian'])

    akk = sdf[sdf.language == 'akkadian']
    print()
    print(f'  per-file (Akkadian only):')
    print(f'    {"file":<20}{"bin":>7}{"macro":>7}{"micro":>7}')
    wdf = df[df.language == 'akkadian']
    for fn in sorted(akk.filename.unique()):
        s = akk[akk.filename == fn]
        g = c.graded_ldi(s)
        b = c.ldi(wdf[wdf.filename == fn])[0]
        print(f'    {fn:<20}{b:>7.3f}{g["macro"]:>7.3f}{g["micro"]:>7.3f}')


if __name__ == '__main__':
    main()
