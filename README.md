# Logograms Analyser

A tool and corpus for tracking the **Logogram Density Index (LDI)** across a
diachronic corpus of Mesopotamian omen texts — measuring the "logographic
shift," the increasing use of Sumerian logograms in cuneiform divination from
the Old Babylonian period into the first millennium BCE.

<!-- TODO: add once the Zenodo DOI is minted:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
-->

This repository accompanies the article *The Logographic Shift: Tracking the
'Sumerianizing' Process in Cuneiform Divination* (Luis Sáenz, forthcoming).

## What it does

The **Logogram Density Index (LDI)** is the share of logographic writings among
the meaningful tokens of a text:

```
LDI = logograms / (logograms + phonetic spellings)
```

ranging from 0 (fully syllabic/phonetic) to 1 (fully logographic). The app
classifies each token as logogram, phonetic, or other, then aggregates LDI by
period, genre, and text, with options to exclude grammatical particles or count
monograms as logograms.

- Interactive [Streamlit](https://streamlit.io) app (`app.py`) with annotation
  editor, per-text and per-omen views, and Plotly charts.
- Standalone, Streamlit-free analysis library (`compute_ratios.py`) plus
  genre-specific scripts (`analyze_astrology.py`, `analyze_restoration.py`,
  `scripts/`).

## Corpus

The `data/` directory holds the transliteration corpus, organized by period and
divination genre:

```
data/
  old/        Old Babylonian
  middle/     Middle Babylonian / Middle Assyrian
  new/        First-millennium (Neo-Assyrian / Neo-Babylonian)
  _comparanda/  cross-cultural comparison texts (Hittite, Hurrian, models)
        astrology/ diagnostic/ extispicy/ izbu/ terrestrial/
```

Primary text editions underlying the transliterations are documented in
[`references.bib`](references.bib).

## Running it locally

Requires Python 3.11+.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

> On Windows where `python` may resolve to an msys2 build without pip, use the
> launcher: `py -m streamlit run app.py`.

## Licensing

- **Software** (`app.py`, `compute_ratios.py`, `analyze_*.py`, `scripts/`, …):
  [MIT License](LICENSE).
- **Data** (the `data/` corpus and derived tables): [CC BY 4.0](data/LICENSE.txt).

Individual omen transliterations are based on published cuneiform text editions;
users remain responsible for citing the underlying primary editions
(see `references.bib`).

## Citation

See [`CITATION.cff`](CITATION.cff), or use GitHub's *Cite this repository*
button. Once archived on Zenodo, please cite the concept DOI.
