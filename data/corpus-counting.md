# Counting conventions: omens, lines, and the corpus totals

This note explains **how texts in `data/` are segmented into omens** — the unit on
which the Logogram Density Index (LDI) is computed — and gives the resulting
corpus totals. The counts here are generated, not typed: run

```
py -3 scripts/corpus_manifest.py
```

which writes [`corpus-manifest.md`](corpus-manifest.md) (every text with its omen
count) and `data/corpus_manifest.csv`. Both use the same segmentation as the app
(`compute_ratios.load_local_data`), so the article tables can always be checked
against them.

## The unit of counting

The LDI is computed **per omen** and then aggregated (by tablet, genre, period).
"What counts as an omen" is whatever the edition marks as one — so segmentation is
driven per text by a `counting:` field in the file's YAML front-matter. Four
structural line types are never counted as content, in every mode:

| Line begins with | Meaning | Treatment |
| --- | --- | --- |
| `@` | section header (`@obverse`, `@reverse`) | sets the current section, not counted |
| `$` | structural marker (rulings, blank spans `($___$)`) | skipped |
| `#` | translation / note (`#tr.en:`) | skipped |
| *(blank)* | — | skipped |

Two further eBL-ATF constructs are treated as **paratext** and dropped before
segmentation (`strip_paratext` in `compute_ratios.py`, mirrored in `app.py`):

- **Discourse sections** — the *content* of `@colophon`, `@catchline`, `@date`,
  `@signature(s)`, `@summary` and `@witnesses` is tablet furniture, not omen
  text, and never enters a count. A colophon's Sumerian year-name
  (`%sux mu …`, e.g. CUSAS 18 no. 28) therefore no longer surfaces as a
  phantom "Sumerian omen", and a catchline (the incipit of the *next* tablet,
  e.g. Rm 267) is not folded into the last omen. All other `@` sections
  (`@obverse`, `@introduction`, `@section …`) are ordinary text.
- **Commentary protocols** — following the eBL-ATF specification, `!cm`
  (commentary), `!qt` (quotation) and `!zz` (uncertain) at the start of a
  line's text open a span that is skipped until `!bs` (base text) resumes; the
  protocol persists across lines until replaced. Used for ṣâtu-style glosses
  inside an omen sequence (e.g. K 778 obv. 3, `!cm … %sux ba-ra : %akk la-a`).

Everything else is transliteration and is assigned to an omen according to the
mode below.

## The four counting modes

### 1. Protasis-particle delimiter — `counting: DIŠ` (or `BE`, `BAD`, `UD`, `AŠ`, `šum-ma`, `šum₄-ma`)

The most common mode. A **new omen begins at every line whose text starts with the
named particle** — the sign that writes the conjunction *šumma* "if" and so opens a
protasis. Lines that do **not** start with the particle (the apodosis, or extra
protasis lines) are folded into the omen in progress. The reader is robust to:

- leading line numbers, plain or eBL-relative — `12.`, `1'.`, `a+41.` are stripped before the test;
- a language shift: a line opening `%sux …` always starts a new omen, so a Sumerian
  line is never glued onto the preceding Akkadian omen.

So one omen = one protasis-particle plus everything up to the next one, however many
physical lines that spans. Which particle a text uses just reflects its edition's
orthography (`DIŠ`, `BE`, `BAD`, `UD`, `AŠ` are logographic openings; `šum-ma` /
`šum₄-ma` are the syllabic writing).

### 2. One omen per line — `counting: line`

Each non-empty content line is its own entry. Used where there is no protasis to
delimit:

- **label / orientation texts** (lung models, "right/left" orientation tablets) — these
  are nomenclature lists with no apodosis, so the natural unit *is* the line;
- **broken or peripheral texts** where no particle can be relied on to open each omen.

For these texts "omen count" is literally the **line count**, which is also the unit
recorded in the source editions.

### 3. Section markers — `counting: §`

Omens are delimited by explicit `§<id>` markers in the file (e.g. `§1`, `§2a`); all
lines under a marker form one omen. Used for editions numbered by paragraph.

### 4. Numbered-line fallback — *(no `counting:` field)*

With no `counting:` field, the omen id is taken from the leading line number
(`^\d+\.`); lines sharing a number belong to one omen. A last-resort default for
plainly numbered texts.

## How the counted corpus breaks down by mode

Distribution across the **196 counted texts** (excludes comparanda, KAL 5, and
individually held-out texts):

| `counting:` | texts | omens | notes |
| --- | ---: | ---: | --- |
| `line` | 67 | 2439 | one omen per line (models + broken/peripheral texts) |
| `DIŠ` | 61 | 2726 | logographic *šumma* |
| `BE` | 40 | 1280 | logographic *šumma* |
| `BAD` | 3 | 102 | logographic *šumma* |
| `AŠ` | 2 | 50 | logographic *šumma* |
| `UD` | 8 | 18 | logographic *šumma* |
| `šum-ma` | 11 | 79 | syllabic *šumma* |
| `šum₄-ma` | 1 | 27 | syllabic *šumma* |
| `§` | 1 | 9 | paragraph markers |
| *(numbered lines)* | 2 | 76 | fallback |
| **Total** | **196** | **6806** | |

The particle delimiters (`DIŠ`/`BE`/`BAD`/`AŠ`/`UD` + `šum-ma`/`šum₄-ma`) together
cover 126 texts / 4282 omens; they are all the *same* rule, differing only in which
sign the edition uses to open the protasis.

## Corpus totals

Counted corpus — **6806 omens in 196 texts**:

| Genre | Old | Middle | Neo | Total |
| --- | ---: | ---: | ---: | ---: |
| astrological (EAE) | 286 (6) | 159 (7) | 453 (8) | **898 (21)** |
| diagnostic (Sakikku) | 33 (2) | 225 (13) | 1173 (32) | **1431 (47)** |
| extispicy (liver + lung) | 188 (13) | 1156 (37) | 534 (16) | **1878 (66)** |
| birth (Šumma izbu) | 134 (5) | 191 (14) | 696 (11) | **1021 (30)** |
| terrestrial (Šumma Ālu) | 120 (3) | 418 (17) | 1040 (12) | **1578 (32)** |
| **Total** | **761 (29)** | **2149 (88)** | **3896 (79)** | **6806 (196)** |

Not included in the total, and listed separately in the manifest:

| Group | texts | omens | in counts? |
| --- | ---: | ---: | --- |
| Held out (in period folders, `exclude: true`) | 7 | 58 | no — duplicates / bilingual / preservation artifacts |
| Comparanda (`data/_comparanda/`) | 9 | 562 | no — used only for comparison |
| KAL 5 supplement (`data/kal5/`) | 78 | 2909 | no — analysed separately (§ Assyria vs Babylonia) |

## Notes

- A text is kept out of the counts by `exclude: true` in its front-matter (whatever
  folder it sits in); comparanda live in `data/_comparanda/`.
- Broken/illegible signs (`x`, `[...]`) contribute nothing to the *LDI* but do not
  change the *omen* count — segmentation is by protasis, not by preservation.
- Determinatives are dropped from the LDI (as unpronounced classifiers) but, again,
  play no role in counting omens.
- Period labels follow each edition; the combined label `Neo-Assyrian / Late
  Babylonian` (EAE 55/57) folds into **Neo**. The standalone `compute_ratios.py`
  historically missed this fold — `scripts/corpus_manifest.py` applies it, which is
  why the manifest is the reference for totals.
