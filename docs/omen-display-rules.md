# Displaying an omen line

How this project renders a transliterated omen on screen, and why. The rules
below are implementation-independent: they describe what the reader should see,
so another application can follow them without reading this one's code. The
reference implementation is `render_tokens_html` and its helpers in `app.py`.

Two things are kept strictly apart:

- the **token** — the cleaned form that drives classification and every LDI
  count, with damage and format markers removed;
- the **display** — the raw form as the edition wrote it, with brackets and
  markers intact.

Everything on this page concerns the display. **No rule here changes a count.**
Segmentation and counting are specified separately, in
[`../data/corpus-counting.md`](../data/corpus-counting.md).

## 1. What each colour means

A line is a sequence of words; each word is classified once and coloured
accordingly. Colour carries the writing system, weight and slope carry the
editorial status.

| class | what it is | colour | face |
|---|---|---|---|
| `logogram` | a word written logographically | `#D32F2F` red | medium (500) |
| `particle` | the omen-opening particle: `DIŠ` `BAD` `BE` `UD` `AŠ` | `#388E3C` green | bold |
| `phonetic` | a syllabically written word | `#212121` near-black | *italic* |
| `monogram` | the one-sign prepositions `ina` `ana` | `#00838F` teal | *italic*, 600 |
| `determinative` | a classifier written in `{ }` | `#1976D2` blue | superscript, lower case, 0.8em |
| `sux` | every word of a line marked `%sux` | `#8E24AA` purple | 600 |
| `broken` | breaks, illegible signs, editorial marks | inherits | inherits |

Italic for syllabic writing is the familiar Assyriological convention; the
logographic red is what the index measures, so it is the strongest signal on the
line.

**`broken` deliberately has no colour of its own.** Greying `x`, `[x]` and `...`
looked informative but was not: the tokenizer types a mark `broken` only when it
stands alone, so an identical mark inside a scored word stayed black and the page
contradicted itself. The class is kept because the markup should still say what
the token is; it simply does not paint it.

## 2. Editorial marks are not language

Anything the editor added, rather than the scribe, is set apart from the word it
sits in. This matters most inside an italic word, where an upright bracket reads
as an intervention and a leaning one reads as text.

- **Brackets** — `[` `]` `(` `)` `{` `}` `<` `>` and the half-brackets `⸢` `⸣` —
  are always upright, on the baseline, never transformed. They keep the colour of
  the word they belong to, which is what shows the reader what the bracket
  applies to.
- **Collation marks** — `?` (uncertain reading) and `!` (corrected sign) — are
  upright and raised clear of the line, at 0.72em. They comment on a sign; they
  are not part of it.
- **An illegible `x`** is upright wherever it appears, including inside an
  otherwise italic word: `ku-x-ma`. It is a note that a sign could not be read,
  not a reading. This applies only where `x` is a whole sign — the letter `x`
  inside a syllable (`ax-bu`, `MAX`) is left alone.

## 3. Damage: from per-sign markers to half-brackets

ATF marks damage one sign at a time with a trailing `#`. An edition brackets the
damaged stretch once. So the markers are dropped and half-brackets are placed at
the two ends of each **maximal run of consecutive damaged signs**:

```
a#-b#-c#      →  ⸢a-b-c⸣
a#-b-c#       →  ⸢a⸣-b-⸢c⸣
ta-lit#-ti    →  ta-⸢lit⸣-ti
```

Signs are separated by `.` or `-`. Three boundary rules follow:

**A run never crosses a word boundary.** Two damaged words each carry their own
pair. Half-brackets say how much of a *word* survives, and merging them across a
space would assert a single damaged stretch the edition does not:

```
URU]{KI#} il#-la-hu-u₂   →  URU]⸢KI⸣ ⸢il⸣-la-hu-u₂     ✓
                          →  URU]⸢KI il⸣-la-hu-u₂       ✗
```

**Editorial brackets stay outside the run.** A restoration encloses the damage
notation, not the reverse:

```
[a#-b#]  →  [⸢a-b⸣]      ✓        ⸢[a-b]⸣    ✗
```

**The round brackets of the corrected-sign notation stay inside**, because they
belong to the sign rather than to the editor's framing of it:

```
KUR!#(EŠ)  →  ⸢KUR!(EŠ)⸣   ✓      ⸢KUR!(EŠ⸣)  ✗
```

## 4. Determinatives

A determinative is a classifier, not a word. It is rendered superscript, in blue,
and **lower-cased whatever case the edition used** — `{LU₂}` and `{lu₂}` both
read `lu₂`.

Its braces are not shown. Any bracket or collation mark attached to it is emitted
**beside** the superscript span rather than inside it, so a half-bracket around a
damaged determinative stays full-size and on the baseline:

```
URU]{KI#}  →  URU]⸢ki⸣        (ki superscript; ] and ⸢ ⸣ are not)
```

## 5. Spacing: what counts as one word

A determinative binds to the word it classifies. Every piece of one
space-separated word is joined with **no space**:

```
{iti}KIN.{d}INANNA  →  itiKIN.dINANNA
URU{ki}             →  URUki
{mul}UGA{mušen}     →  mulUGAmušen
```

**Two determinatives in a row are two classifiers**, read apart, and keep a space
between them even inside a single word:

```
{mul}{d}AMAR.UTU  →  mul dAMAR.UTU
{ki}{meš}         →  ki meš
```

A compound written as one determinative (`{hi.a}`) is one classifier and is not
split.

## 6. Line structure

**The omen number** is printed once, at the head of the line, in grey and not
selectable — it is apparatus, and should not end up in a copied quotation. It
occupies a **fixed column**, wide enough for the longest number in that text, so
that a 9 and a 10 leave the omen itself starting at the same place:

```
9.   DIŠ AN.TA.LU₃ …
10.  DIŠ 30 ha-ad-ri-iš …
```

**The line is two columns, and nothing hangs outside it.** The number occupies
the first; the omen occupies the second. Within the omen's own column its first
line is pulled back by the width of the counting mark, so the mark sits at that
column's edge and every further line of the same omen — a wrap, or a run-over —
begins where the omen's *words* do. The text therefore forms one column however
often it breaks, while the pull-back stays inside the omen's box and can never
cross the block's left border into whatever sits beside it.

Both widths are measured per text: the number column from its widest label, the
pull-back from the length of its counting mark. A `counting: line` text has no
mark and so no pull-back, which is why two texts of the same series can indent
differently — the difference records how each is segmented.

**A run-over marked `($___$)`** — the editions' notation for text that stood on
its own indented line on the tablet — is not printed. It becomes a plain line
break, and the hanging indent puts it in the same column as a wrap.

**Repeated markers are one break at a deeper step, not one break each.** An
edition indents a run-over further; it does not skip lines. So `($___$)
($___$) ($___$)` breaks once and steps in twice beyond the hanging indent, while
two markers *separated by text* on the same line break twice, once at each. The
example below shows the single case:

```
5. DIŠ AN.TA.LU₃ i+na qa₂-a[b-la-ti-šu ...]
        LUGAL i-ma-[at ...]
```

**The edition's translation**, written on its own line as `#tr.en:` under the
line it renders, is printed under the omen — grey, a size down, indented to the
omen's column rather than the number's. It is there to be read beside the
transliteration, not to compete with it. A translation that runs over several
`#tr.` lines is joined into one; an omen assembled from several tablet lines
carries all of their translations, in order.

**A `%sux` marker** is not printed either. It colours the whole line purple,
marking it as Sumerian rather than Akkadian.

## 7. Escaping

Display strings are HTML-escaped. Transliteration uses `<` and `>` for scribal
omissions (`<<MA>>`), which are text and must not become markup.

## Summary for an implementer

1. Classify each word once; colour by writing system, slope by editorial status.
2. Set brackets upright; raise `?` and `!`; keep an illegible `x` upright.
3. Convert `#` to half-brackets around each damaged run, stopping at word
   boundaries, with editorial brackets outside and corrected-sign brackets inside.
4. Superscript and lower-case determinatives; keep their marks out of the
   superscript.
5. Join the pieces of one word; separate two adjacent determinatives.
6. Hang the line past number and delimiter; break at a run-over into that same
   column; print the `#tr.` translation under it in grey; print neither
   `($___$)` nor `%sux`.
7. Escape the text.

None of it touches the numbers.
