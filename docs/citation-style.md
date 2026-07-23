# Citation style

How published texts are cited in this project. The model is adapted from the
LAD dictionary's TEI citation rules (`lad-website/resources/xsl/entry/utils/bibliography.xsl`,
`references.xsl`, `sections/examples-citations.xsl`).

## Principle

**Never write a full reference inline.** A citation is a *pointer*: a standard
**abbreviation (siglum)** plus a **typed locus**. The full author / year / title /
publisher lives once in the **registry** — for us, [`references.bib`](../references.bib) —
keyed by a BibTeX key. The in-text `publication:` / `edition:` strings in each
source's frontmatter are the pointers that resolve to it.

This matches Assyriological convention: cite `TCS 4, 101`, `CUSAS 18 no. 14`,
`KAR 444`, `Iraq 68, 23–57` — **siglum-first, not author-year** — and let the
abbreviation carry the reference.

Author-year (`Heeßel 2012`, `De Zorzi 2014`) is a valid secondary form and is
also resolved by the app's Bibliography tab, but the **preferred** form for a
published text edition is the siglum.

## Anatomy of a citation

A citation has three optional layers:

1. **Siglum + locus** — the printed reference. `Iraq 68, 23–57`.
2. **Registry key** — which `references.bib` entry it resolves to. `alrawigeorge2006`.
3. **Online deep-link** — an eBL / DCCLT / Archibab pointer to the digital text.

In the frontmatter these collapse into one string, e.g.:

```yaml
publication: VAT 17259 (TCS 4, 101); De Zorzi 2014 ms D of canonical Tablet 7
edition: Al-Rawi & George, Iraq 68 (2006) 23–57 (MS "IM")
```

## Locus — controlled vocabulary

A locus is built from typed parts, **never a free string**. The only units:

| unit | meaning | renders as |
| --- | --- | --- |
| `volume` | series/journal volume | `TCS 4` |
| `page` | page(s) | `, 23–57` or `: 131` |
| `number` | text/exemplar number | `no. 14` |
| `tablet` | tablet number | `Tablet 7` |
| `museumNumber` | excavation/museum siglum | `VAT 9580` |
| `line` | line / column | `: 15` or `i 12` |
| `footnote` | footnote | `fn. 3` |

Plus `author` / `editor` / `date` / `publisher` / `pubPlace` for full-form
rendering, and a genre gloss.

## Ordering & punctuation

Parts are emitted in this fixed order, with context-dependent separators:

| Part | Separator before it |
| --- | --- |
| **title / siglum** | — |
| **volume** | space → `TCS 4` |
| **page** | `, ` if a *volume* **or** *line* is present; otherwise `: ` |
| **number** | ` no. ` if a *page* precedes; otherwise `, ` |
| **tablet** | space |
| **museumNumber** | space |
| **line** | space if a *tablet* or *museumNumber* precedes, **or** the line starts with a column (`i`–`vi`), `rev.`/`obv.`, or an edge (`l.e.`, `r.e.`, `u.e.`, `lo.e.`); otherwise `: ` |
| **footnote** | ` fn. ` |
| genre gloss | ` (gloss)` |
| equivalent siglum | ` (= …)` |

### Worked examples

| Parts | Result |
| --- | --- |
| `Iraq` + vol `68` + page `23–57` | `Iraq 68, 23–57` |
| `CUSAS` + vol `18` + no. `14` | `CUSAS 18 no. 14` |
| `KAL` + vol `5` + no. `78` | `KAL 5 no. 78` |
| `TDP` + page `2` + line `15` | `TDP 2: 15` |
| `TCS` + vol `4` + page `101` | `TCS 4, 101` |
| `JNES` + vol `42` + page `131–132` | `JNES 42, 131–132` |
| siglum `KAR 444` `(= VAT 9580)` | `KAR 444 (= VAT 9580)` |

The `X (= Y)` form links two sigla for the same object (publication number =
museum number).

## Online deep-links

The digital-source link is a **separate** part, paired with the printed
reference. `@source` → URL:

| source | URL pattern |
| --- | --- |
| `eBL` | `https://www.ebl.lmu.de/library/{id}` |
| `eBL_corpus` | `https://www.ebl.lmu.de/corpus/{id}` |
| `DCCLT` | `http://oracc.museum.upenn.edu/dcclt/{id}` |
| `ARCHIBAB` | `https://archibab.fr/texte/{id}` |
| `BDTNS` | `https://bdtns.cesga.es/{id}` |
| `SEAL` | `https://seal.huji.ac.il/node/{id}` |
| `SAAo` | `https://oracc.museum.upenn.edu/saao/{id}` |
| `RINAP` | `https://oracc.museum.upenn.edu/rinap/{id}` |
| `EPSD2` | `https://oracc.museum.upenn.edu/epsd2/{id}` |
| `CCP` | `https://ccp.yale.edu/{id}` |
| `RIBo` / `RIAo` | `https://oracc.museum.upenn.edu/ribo|riao/{id}` |
| `TCMA` | `https://oracc.museum.upenn.edu/tcma/{id}` |
| `GKAB` | `https://oracc.museum.upenn.edu/cams/gkab/{id}` |

(The full list — 25+ corpora — is in `references.xsl`, template
`generate-reference-url`.)

## How this maps to the app

- [`references.bib`](../references.bib) is the **registry**: one entry per work,
  with the standard series abbreviation in its `series` field
  (`Texts from Cuneiform Sources (TCS) 4`, `... (CUSAS) 18`, `... (KAL) 5`).
- The `publication:` / `edition:` frontmatter strings are the **pointers**.
- The **Bibliography** tab resolves both forms — a siglum (`CUSAS 18`, `TCS 4`,
  `KAL 5`) and an author-year (`Heeßel 2012`, `De Zorzi 2014`) — to the entry.

### Conventions to keep pointers resolvable

1. **Siglum first**, then the typed locus, in the order above:
   `CUSAS 18 no. 14`, not `no. 14 of CUSAS 18`.
2. Keep the **series abbreviation** exactly as registered in `references.bib`
   (`TCS 4`, `KAL 5`, `HANE/M 15`, `AfO Beih. 22`) so it links.
3. When a work has no siglum, use **author-year** (`Starr 1983`, `Fadhil 2023`);
   the surname must match the registry entry's author.
4. Give the museum/excavation number as its own part; it is *not* a citation and
   should not be styled as one (`VAT 17259 (TCS 4, 101)` — VAT number is the
   object, TCS 4 is the citation).
