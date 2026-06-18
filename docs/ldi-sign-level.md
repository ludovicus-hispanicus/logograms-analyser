# The sign-level (graded) LDI — what changed and why

This documents a change to how the Logogram Density Index is computed. The
original index is **kept unchanged** (for continuity with earlier results and the
dissertation); two new, complementary indices are **added** alongside it.

## The problem with the original (binary, word-level) LDI

The original LDI tokenizes on whitespace and scores a whole token as a *logogram*
if it contains **any** uppercase sign (`compute_ratios.get_token_type`). So a word
written logographically but carrying a syllabic **phonetic complement** —
`ŠIR-MEŠ-šu₂`, `LUGAL-šu₂` — counts as **fully** logographic, and the complement
disappears. Under that rule an omen like EAE 57:94 scores **LDI = 1.00** even
though two of its words carry the complements *-šu₂* and *-ma*. "100 % logographic"
therefore did **not** mean "only logograms, no syllabic signs."

## The fix: count each sign, and grade each word

The new tokenizer (`compute_ratios.annotate_signs`) splits every word into its
individual **signs**, on both `.` and `-`, and classifies each sign on its own:

- **logogram** — an uppercase sign (`ŠIR`, `MEŠ`, `KI`, `SA₂`; the opening particle
  `DIŠ`; a divine name written as a number, `{d}30`);
- **phonetic** — a lowercase sign (syllabic Akkadian *or* a phonetic complement —
  the metric does not distinguish the two; both are "not a logogram");
- **determinative** — a classifier in braces (`{mul}`, `{d}`, `{ki}`);
- *not counted* — bare numerals (`2`, `3`) and stray punctuation.

So `ŠIR-MEŠ-šu₂` → `ŠIR` (log) + `MEŠ` (log) + `šu₂` (phonetic): the complement is
now visible.

### Three word states (the underlying breakdown)

Every written word falls into exactly one state, by its content signs:

| state | meaning | example |
|---|---|---|
| **pure-logographic** | logogram sign(s), no phonetic sign | `KI.A`, `MUL₅.MUL₅` |
| **mixed** | logogram(s) **and** phonetic complement | `ŠIR-MEŠ-šu₂`, `SIG₇-MEŠ-ma` |
| **syllabic** | phonetic sign(s) only | `i-bal-luṭ`, `šum-ma` |

Reporting the proportions of these three (a composition summing to 100 %) is the
most transparent representation; the indices below are summaries of it.

### Two aggregate indices

Each word gets a **graded degree** = (logogram signs) / (logogram + phonetic signs)
*within that word* — parameter-free. A pure logogram = 1.0, `ŠIR-MEŠ-šu₂` = 2/3,
a syllabic word = 0.0. The two indices differ only in how they aggregate, which is
the standard **macro- vs micro-average** distinction:

- **macro LDI** — mean of the per-word degrees; **each word counts once**. This is
  the "respect the word as a unit" reading: a logogram+complement word lands
  *between* 0 and 1 rather than being divided away. **Use this as the headline.**
- **micro LDI** — logogram / (logogram + phonetic) signs, pooled over all signs;
  **weights by sign**. This is the strict reading: a complement is just one more
  phonetic sign and counts fully against the score.

The two bracket the truth. For a single omen, EAE 57:94:

```
DIŠ MUL₅.MUL₅ ŠIR-MEŠ-šu₂ SIG₇-MEŠ-ma KI.A SI.SA₂
```
| index | value | note |
|---|---|---|
| old binary (word-level) | **1.00** | complements absorbed |
| **macro (per-word)** | **0.889** | degrees 1, 1, ⅔, ⅔, 1, 1 |
| micro (per-sign) | 0.846 | 11 log / 13 content signs |

word composition: **4 pure-log, 2 mixed, 0 syllabic.**

## Two deliberate decisions

1. **Determinatives are excluded** from both indices (numerator *and* denominator).
   They are unpronounced classifiers, not part of the word's logogram-vs-syllable
   choice; counting them as logograms would also wrongly lift Sumerian words
   (`{mul}uga` → uga is Sumerian, not a logogram). They are still tracked and
   reported as a separate sign count.
   - **Consequence, important when comparing to the old index:** the old LDI put
     determinatives in its denominator as *non*-logograms, so they quietly diluted
     it. The new indices do not. This means the new **micro can sit slightly above
     the old binary** at the chapter level even though it peels complements — the
     two indices differ on *two* axes (− complements, + classifiers). The old index
     understated logographic density by treating classifiers as non-logographic;
     the new ones correct that.
2. **Numerals are not counted** (a bare `2`, `3`), as before. A divine name written
   as a number after `{d}` (e.g. `{d}30` = Sîn) is still a logogram.

A one-line change in `annotate_signs`/`graded_ldi` flips determinatives to count as
logograms instead, if a different convention is preferred later.

## Effect on the diachronic curve

The rise survives on every index; what the new metrics add is the **mechanism**.
The genre-controlled diagnostic arc (*Sakikkû* and its forerunners), Akkadian only:

| Period | old binary | macro | micro | pure-log | mixed | syllabic |
|---|---:|---:|---:|---:|---:|---:|
| **Old** | 0.125 | 0.124 | 0.062 | 12 % | 0 % | 87 % |
| **Middle** | 0.461 | 0.406 | 0.278 | 32 % | 16 % | 52 % |
| **Neo / canonical** | 0.721 | 0.605 | 0.533 | 44 % | 30 % | 27 % |

Two things are now visible that the binary index hid:

- **The curve still climbs monotonically** (macro 0.12 → 0.41 → 0.61; micro
  0.06 → 0.28 → 0.53), but the first-millennium ceiling is **lower and more
  honest**: the canonical omens are not "100 % logographic," they are ~60 %
  logographic by word, the residue being grammatical complement.
- **The shift is largely the rise of the *mixed* category.** Pure-syllabic writing
  collapses (87 % → 52 % → 27 %) while *mixed* logogram+complement words grow from
  **0 % → 16 % → 30 %**. Much of what the binary LDI counted as a jump to "full
  logography" is in fact a jump into *logogram-plus-complement* writing.

The astrological chapters behave differently and the new index shows why: EAE 55/57
are **purer** logographic (≈ 65–68 % pure-log words, only ~8–10 % mixed), where the
Neo diagnostic canon is **complement-heavy** (30 % mixed). The binary LDI put both
near ≈ 0.72 and could not tell them apart.

## Where it lives in the code

- `compute_ratios.annotate_signs(text, omen_id, metadata, preserved_only=False)`
  — sign-level tokenizer (one row per sign, with `word_index`).
- `compute_ratios.load_local_signs(base_path, preserved_only=False)` — sign-level
  corpus load (same omen segmentation as `load_local_data`).
- `compute_ratios.graded_ldi(signs_df, exclude_particles=False)` — returns
  `{micro, macro, pure, mixed, syllabic, words, log, phon, det}`.
- The original `annotate_omen` / `ldi` are untouched; `load_local_data` now takes an
  optional `annotate=` tokenizer (defaults to the old one).
- Reporting: `scripts/per_omen_ldi.py` and `scripts/folder_ldi.py` print `bin`,
  `macro`, `micro` and the three-state composition side by side.

Note: `app.py` (the Streamlit viewer) still uses the original binary LDI only; the
graded metrics live in the analysis pipeline.

## Monographic function words (the `ina`/`ana` nuance)

The prepositions **`ina`** and **`ana`** are normally written with a *single
sign* — `ina` = the sign AŠ, `ana` = the *ana* sign — not with the phonetic
spellings `i-na` / `a-na` (cf. the Middle-Assyrian `i+na`). Because they are
transliterated in lowercase, the default LDI files them as **phonetic/syllabic**,
which understates their graphic character: a one-sign, non-decomposed writing of a
whole lexeme behaves like a **monogram** — a quasi-logographic abbreviation — not
like a syllabically spelled-out word. (At the sign level they are already counted
as a single sign; the issue is only their *class*, syllabic vs logographic.)

To make this visible without redefining the primary metric, `ldi()` and
`graded_ldi()` take **`monogram_as_log=True`**, which reclassifies the tokens in
`MONOGRAM_PARTICLES = {ina, ana}` as logograms. `scripts/folder_ldi.py` prints this
as a `+monogram` line next to the default figures.

The set is deliberately limited to `ina`/`ana`: they are independent prepositions
written as one sign and, in the Neo terrestrial cell, the two largest components of
the "syllabic" residue (`ina` 652 + `ana` 401 = 15.9 % of all syllabic signs).
Bound morphemes (`-ma`, `-šu₂`, `-ut`, `-su`) are *not* included — they are genuine
phonetic complements/grammar, not monographic lexemes. (Conjunctions `u`/`lu` are
candidate extensions but are left out by default.)

Effect on the **Neo terrestrial cell** (1000 omens): bin 0.749 → **0.843**,
macro 0.693 → **0.789**, micro 0.613 → **0.675**; fully-logographic omens
(micro = 1.00) rise from 48 to 87 — i.e. 39 omens whose *only* non-logographic
signs were `ina`/`ana` (e.g. the gecko omen Tablet 33:34, `DIŠ MUŠ.GIM.GURUN.NA
SIG₇ ina E₂ LU₂ MIN EN E₂ BI SUḪUŠ.BI NU GI.NA`). Report the default figure as the
headline and the `+monogram` figure as the upper bound of "graphic logography."
