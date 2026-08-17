# -*- coding: utf-8 -*-
"""Regenerate every table of figures reported in the paper, from the corpus.

    python reproduce_tables.py

Prints each table with the label it carries in the paper, so every number in
the article can be checked against the data.  Requires only compute_ratios.py
and data/ (see requirements.txt).
"""
import sys

import pandas as pd

import compute_ratios as C

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ORDER = C.PERIOD_ORDER
DISCIPLINE = {
    'astrological omens': 'astrological (Enuma Anu Enlil)',
    'diagnostic omens':   'diagnostic (Sakikku)',
    'extispicy omens':    'extispicy (liver and lung)',
    'izbu omens':         'birth (Summa izbu)',
    'terrestrial omens':  'terrestrial (Summa Alu)',
}


def fold(period):
    """Map any edition label onto the three periods used in the paper."""
    if period in ORDER:
        return period
    if period in C.PERIOD_MAPPING:
        return C.PERIOD_MAPPING[period]
    for name in ORDER:                       # e.g. 'Neo-Assyrian / Late Babylonian'
        if name.split()[0] in period:
            return name
    return period


def load():
    note('reading the corpus')
    words = pd.DataFrame(C.load_local_data())
    signs = pd.DataFrame(C.load_local_signs())
    preserved = pd.DataFrame(C.load_local_data(preserved_only=True))
    for frame in (words, signs, preserved):
        frame['era'] = frame['period'].map(fold)
    return words, signs, preserved


def scored(frame, exclude_particles=False, monogram_as_log=False):
    """The rows compute_ratios.ldi() would score, with a 0/1 column per sign.

    Grouping this frame reproduces ldi() exactly but in one pass, which matters
    when scoring all 6,990 omens individually.
    """
    sub = frame[frame['type'].isin(['logogram', 'phonetic'])]
    sub = C._drop_contentless(sub)
    if exclude_particles:
        mask = sub['token'].isin(C.LOGOGRAM_PARTICLES) & (sub['type'] == 'logogram')
        sub = sub[~mask]
    kind = sub['type']
    if monogram_as_log:
        kind = kind.where(~sub['token'].isin(C.MONOGRAM_PARTICLES), 'logogram')
    return sub.assign(is_log=(kind == 'logogram').astype(int))


_GRADED = {}


def graded(signs, era=None, exclude_particles=False):
    """graded_ldi(), computed once per (subset, convention) and reused.

    The three measures, the composition table and the by-convention table all
    need the same subsets; recomputing them is the bulk of the runtime.
    """
    key = (era, exclude_particles)
    if key not in _GRADED:
        subset = signs if era is None else signs[signs.era == era]
        note(f'scoring {era or "whole corpus"}'
             f'{" (particles excluded)" if exclude_particles else ""}')
        _GRADED[key] = C.graded_ldi(subset, exclude_particles=exclude_particles)
    return _GRADED[key]


def note(message):
    print(f'  ... {message}', file=sys.stderr, flush=True)


def head(title, label):
    print(f'\n{title}   [{label}]\n' + '-' * (len(title) + len(label) + 6), flush=True)


def main():
    words, signs, preserved = load()
    n_omens = words.groupby(['filename', 'omen_id']).ngroups
    print(f'corpus: {n_omens} omens in {words.filename.nunique()} texts')

    # ---- Table: omens (texts) by discipline and period -------------------
    head('Omens (texts) by discipline and period', 'tbl:corpus')
    print(f'{"discipline":<32}' + ''.join(f'{p.split()[0]:>14}' for p in ORDER) + f'{"total":>14}')
    for genre, label in DISCIPLINE.items():
        sub = words[words.genre == genre]
        cells = []
        for era in ORDER:
            e = sub[sub.era == era]
            cells.append(f'{e.groupby(["filename", "omen_id"]).ngroups} ({e.filename.nunique()})')
        cells.append(f'{sub.groupby(["filename", "omen_id"]).ngroups} ({sub.filename.nunique()})')
        print(f'{label:<32}' + ''.join(f'{c:>14}' for c in cells))
    cells = []
    for era in ORDER:
        e = words[words.era == era]
        cells.append(f'{e.groupby(["filename", "omen_id"]).ngroups} ({e.filename.nunique()})')
    cells.append(f'{n_omens} ({words.filename.nunique()})')
    print(f'{"TOTAL":<32}' + ''.join(f'{c:>14}' for c in cells))

    # ---- Table: the index by period --------------------------------------
    head('The index by period', 'tbl:periods')
    print(f'{"period":<10}{"bin":>8}{"macro":>8}{"micro":>8}')
    for era in ORDER:
        g = graded(signs, era)
        b = C.ldi(words[words.era == era])[0]
        print(f'{era.split()[0]:<10}{b:>8.2f}{g["macro"]:>8.2f}{g["micro"]:>8.2f}')

    # ---- Table: word composition by period -------------------------------
    head('Word composition by period', 'tbl:composition')
    print(f'{"period":<10}{"pure-log":>10}{"mixed":>10}{"syllabic":>10}')
    for era in ORDER:
        g = graded(signs, era)
        n = g['words']
        print(f'{era.split()[0]:<10}{100*g["pure"]/n:>9.1f}%{100*g["mixed"]/n:>9.1f}%'
              f'{100*g["syllabic"]/n:>9.1f}%')

    # ---- Table: effect of excluding the opening particle ------------------
    head('Effect of excluding the opening particle, by discipline', 'tbl:particles')
    print(f'{"discipline":<14}{"baseline":>10}{"excluded":>10}{"effect":>9}{"omen len":>10}')
    rows = []
    for genre in DISCIPLINE:
        sub = words[words.genre == genre]
        base = C.ldi(sub)[0]
        excl = C.ldi(sub, exclude_particles=True)[0]
        countable = scored(sub)
        length = len(countable) / countable.groupby(['filename', 'omen_id']).ngroups
        rows.append((genre.split()[0], base, excl, excl - base, length))
    for name, base, excl, eff, length in sorted(rows, key=lambda r: -r[4]):
        print(f'{name:<14}{base:>10.3f}{excl:>10.3f}{eff:>+9.3f}{length:>10.1f}')

    # ---- Sensitivity baselines and the seven conventions ------------------
    head('The same corpus under seven defensible conventions', 'tbl:spread')
    g_all = graded(signs)
    conventions = [
        ('ina/ana counted as logographic', C.ldi(words, monogram_as_log=True)[0]),
        ('bin, as published (baseline)',   C.ldi(words)[0]),
        ('restorations dropped',           C.ldi(preserved)[0]),
        ('opening particles excluded',     C.ldi(words, exclude_particles=True)[0]),
        ('unit = word, graded (macro)',    g_all['macro']),
        ('unit = sign (micro)',            g_all['micro']),
        ('micro, particles excluded',      graded(signs, exclude_particles=True)['micro']),
    ]
    for name, value in conventions:
        print(f'  {name:<34}{value:>8.3f}')
    values = [v for _, v in conventions]
    print(f'  {"range":<34}{max(values) - min(values):>8.3f}'
          f'   ({min(values):.3f} to {max(values):.3f})')

    marked = scored(words)
    by_text = marked.groupby('filename').is_log.mean()
    by_omen = marked.groupby(['filename', 'omen_id']).is_log.mean()
    print(f'\n  aggregation: pooled {C.ldi(words)[0]:.3f} | '
          f'mean of texts {by_text.mean():.3f} | mean of omens {by_omen.mean():.3f}')

    # ---- Table: the periods under each convention -------------------------
    head('The periods recomputed under each convention', 'tbl:periods-by-convention')
    print(f'{"convention":<28}' + ''.join(f'{p.split()[0]:>9}' for p in ORDER) + f'{"Old->Mid":>10}')

    def by_era(fn):
        return [fn(era) for era in ORDER]

    variants = [
        ('bin (baseline)',            lambda e: C.ldi(words[words.era == e])[0]),
        ('ina/ana logographic',       lambda e: C.ldi(words[words.era == e], monogram_as_log=True)[0]),
        ('opening particles excluded', lambda e: C.ldi(words[words.era == e], exclude_particles=True)[0]),
        ('restorations dropped',      lambda e: C.ldi(preserved[preserved.era == e])[0]),
        ('macro',                     lambda e: graded(signs, e)['macro']),
        ('micro',                     lambda e: graded(signs, e)['micro']),
        ('micro, particles excluded', lambda e: graded(signs, e, exclude_particles=True)['micro']),
    ]
    for name, fn in variants:
        vals = by_era(fn)
        print(f'{name:<28}' + ''.join(f'{v:>9.3f}' for v in vals) + f'{vals[1]-vals[0]:>+10.3f}')

    # ---- Table: restoration ----------------------------------------------
    head('Scored with and without the editor\'s restorations', 'tbl:restoration')
    both = by_text.to_frame('with_restoration')
    both['preserved_only'] = scored(preserved).groupby('filename').is_log.mean()
    both['delta'] = both.preserved_only - both.with_restoration
    print(f'  whole corpus: with restoration {C.ldi(words)[0]:.3f} | '
          f'preserved only {C.ldi(preserved)[0]:.3f}')
    print(f'  falls in {(both.delta < 0).sum()} of {len(both)} texts, rises in {(both.delta > 0).sum()}')
    print(f'  shifts by more than 0.05 in {100*(both.delta.abs() > 0.05).mean():.0f} % of texts; '
          f'largest {both.delta.abs().max():.2f}')
    for era in ORDER:                     # pooled, as reported in the paper
        correction = C.ldi(preserved[preserved.era == era])[0] - C.ldi(words[words.era == era])[0]
        print(f'    {era:<16}{correction:>+8.3f}')

    # ---- Table: a specimen report ----------------------------------------
    head('A specimen report, one witness beside the corpus', 'tbl:reporting')
    for name, wsub, ssub, psub in [
        ('BM 121034', words[words.filename == 'BM.121034.txt'],
         signs[signs.filename == 'BM.121034.txt'],
         preserved[preserved.filename == 'BM.121034.txt']),
        ('whole corpus', words, signs, preserved),
    ]:
        g = graded(signs) if name == 'whole corpus' else C.graded_ldi(ssub)
        n = g['words']
        print(f'  {name}')
        print(f'    bin {C.ldi(wsub)[0]:.3f} | macro {g["macro"]:.3f} | micro {g["micro"]:.3f}')
        print(f'    pure {100*g["pure"]/n:.1f} % | mixed {100*g["mixed"]/n:.1f} % | '
              f'syllabic {100*g["syllabic"]/n:.1f} %')
        print(f'    restorations dropped {C.ldi(psub)[0]:.3f} | '
              f'ina/ana logographic {C.ldi(wsub, monogram_as_log=True)[0]:.3f} | '
              f'particle excluded {C.ldi(wsub, exclude_particles=True)[0]:.3f}')

    # ---- ina / ana in the Neo terrestrial material ------------------------
    head('ina and ana in the Neo terrestrial material', 'sec. ina and ana')
    sub = words[(words.genre == 'terrestrial omens') & (words.era == 'Neo Period')]
    sig = signs[(signs.genre == 'terrestrial omens') & (signs.era == 'Neo Period')]
    print(f'  {sub.groupby(["filename", "omen_id"]).ngroups} omens')
    print(f'    bin   {C.ldi(sub)[0]:.3f} -> {C.ldi(sub, monogram_as_log=True)[0]:.3f}')
    for key in ('macro', 'micro'):
        print(f'    {key} {C.graded_ldi(sig)[key]:.3f} -> '
              f'{C.graded_ldi(sig, monogram_as_log=True)[key]:.3f}')
    for flag in (False, True):
        per_omen = scored(sub, monogram_as_log=flag).groupby(['filename', 'omen_id']).is_log.mean()
        full = int((per_omen == 1.0).sum())
        print(f'    fully logographic omens, ina/ana as {"logographic" if flag else "syllabic"}: {full}')


if __name__ == '__main__':
    main()
