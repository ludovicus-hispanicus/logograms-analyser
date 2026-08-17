import os
import io
import sys
import base64
import shutil
import unicodedata
import tempfile
import zipfile
import urllib.request
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components

# True under stlite/Pyodide (the offline desktop / WASM build), where live
# network calls to the eBL API are unavailable. Used to hide online-only UI.
_OFFLINE = sys.platform == "emscripten"
try:
    from streamlit_ace import st_ace
    _HAS_ACE = True
except Exception:
    _HAS_ACE = False
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import re
import yaml

# --- Configuration ---
# The logo: a grid of words, solid where the writing is logographic, split where
# mixed, outlined where spelt out — the corpus composition, cell for cell. The
# tab icon and the header use the reduced nine-cell mark, because the twenty-five
# of the full grid merge into texture below about 48 px.
_LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo")

def _logo_data_uri(name):
    """The mark as a data URI, so it travels with the page (stlite included)."""
    try:
        with open(os.path.join(_LOGO_DIR, name), "rb") as fh:
            return "data:image/svg+xml;base64," + base64.b64encode(fh.read()).decode()
    except OSError:
        return ""

# Three sizes of one mark: 25 cells large (README, print), 16 in the header where
# the split cells still read, 9 in the tab icon where they would not.
_MARK_URI = _logo_data_uri("ldi-grid-ui.svg")
_FAVICON = os.path.join(_LOGO_DIR, "ldi-grid-favicon.png")

st.set_page_config(
    page_title="The Logogram Density Index (LDI)",
    page_icon=_FAVICON if os.path.exists(_FAVICON) else "🏺",
    layout="wide",
)

# --- CSS Loading ---
def load_css():
    st.markdown("""
        <style>
        .omen-line {
            font-family: 'Source Sans 3', sans-serif;
            font-size: 1.2rem;
            margin-bottom: 0.8rem;
            line-height: 1.6;
        }
        .logogram {
            color: #D32F2F; /* Red */
            font-weight: 500;
        }
        .phonetic {
            color: #212121; /* Black/Dark Grey */
            font-style: italic;
        }
        .determinative {
            color: #1976D2; /* Blue */
            font-size: 0.8em;
            vertical-align: super;
        }
        .particle {
            color: #388E3C; /* Green */
            font-weight: bold;
        }
        .monogram {
            color: #00838F; /* Teal — ina/ana monograms (kept clear of the red logogram) */
            font-style: italic;
            font-weight: 600;
        }
        .sux {
            color: #8E24AA; /* Purple — Sumerian language marker (%sux) */
            font-weight: 600;
        }
        .broken {
            color: #9E9E9E; /* Grey — breaks, illegible signs, editorial marks (not scored) */
        }
        .ldi-val {
            font-family: 'Source Sans 3', sans-serif;
            font-size: 1.1rem;
            color: #424242;
            text-align: right;
            margin-bottom: 0.8rem;
        }
        .omen-id {
            color: #757575;
            font-weight: bold;
            margin-right: 10px;
            user-select: none;
        }
        /* Force pointer (hand) cursor on Plotly charts */
        .js-plotly-plot .plotly, .js-plotly-plot .plotly .draglayer {
            cursor: pointer !important;
        }

        /* A chart's title, printed above its measure switch (the switch then sits
           between the title and the chart, and the figure carries no title of
           its own). */
        .charttitle {
            font-size: 1.02rem;
            font-weight: 600;
            color: #262626;
            margin: 0.2rem 0 0.1rem 0.1rem;
        }

        /* Copy control beside its table: content-width children, and the frame
           nudged down so the dropdown lines up with the table's first row. */
        [class*="st-key-cprow_"] {
            gap: 0.9rem !important;
            align-items: flex-start !important;
            flex-wrap: nowrap !important;
        }
        [class*="st-key-cprow_"] > div > [data-testid="stElementContainer"] {
            flex: 0 0 auto !important;
            width: auto !important;
        }
        [class*="st-key-cprow_"] iframe {
            width: 230px !important;
            margin-top: 0.15rem;
        }

        /* The accent lives in the separators: every rule on the page is red
           taken down to a grey tone, so the colour runs through without
           competing with the logogram red in the texts. */
        .stMain hr {
            border: none !important;
            border-top: 2px solid #C79A97 !important;
            opacity: 1 !important;
            margin: 1.5rem 0 1.2rem !important;
        }

        /* --- App header: title + nav tabs on one line, with a shared bottom border --- */
        .st-key-appheader {
            margin-bottom: 1.4rem;
        }
        /* The mark, sharing the title's baseline. It is pinned to the row rather
           than laid out in it: in flow the mark was the tallest child and set the
           row height itself, so every change to the button box moved the title
           under a mark that stayed put, and the two drifted apart by a few pixels
           between renders. Pinned, the row's height comes from the button alone
           and `bottom` measures from the button's box to its text baseline. */
        .st-key-brandrow {
            position: relative;
            padding-left: 67px !important;      /* 54px mark + 13px gap */
            flex-wrap: nowrap !important;
        }
        .st-key-brandrow [data-testid="stElementContainer"]:has(.brandmark) {
            position: absolute !important;
            left: 0;
            bottom: 2.05rem;                    /* measured: row box bottom -> baseline */
            width: 54px !important;
            flex: 0 0 auto !important;
        }
        .brandmark {
            display: block;
            width: 54px; height: 54px;
        }
        /* Title rendered as a flat heading-button (left) */
        .st-key-home_btn button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 0 0.4rem 0 !important;
            color: #1a1a1a !important;
            text-align: left !important;
        }
        /* The label sits in an inner <p> with its own size — set it there. */
        .st-key-home_btn button p {
            font-size: 2.75rem !important;
            font-weight: 700 !important;
            line-height: 1.15 !important;
            margin: 0 !important;
        }
        .st-key-home_btn button:hover,
        .st-key-home_btn button:hover p { color: #D32F2F !important; }
        /* Nav tab buttons (right): flat, flush on the header border */
        [class*="st-key-nav_"] button {
            border: none !important;
            border-bottom: 3px solid transparent !important;
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
            color: #666 !important;
            font-weight: 600 !important;
            padding: 0.3rem 0.1rem !important;
            margin-bottom: -2px !important;       /* sit on the 2px border */
        }
        /* The label sits in an inner <p> with its own size — set it there, or the
           button's font-size is ignored. Only this strip grows; the LDI view tabs
           below keep their smaller size. */
        [class*="st-key-nav_"] button p {
            font-size: 1.3rem !important;
            line-height: 1.25 !important;
            margin: 0 !important;
        }
        [class*="st-key-nav_"] button:hover { color: #111 !important; }
        /* Active tab (rendered as type="primary") */
        [class*="st-key-nav_"] button[kind="primary"],
        [class*="st-key-nav_"] button[data-testid="stBaseButton-primary"] {
            color: #D32F2F !important;
            border-bottom: 3px solid #D32F2F !important;
        }
        /* LDI sub-view selector (segmented control) — read it as a tab strip:
           flat segments, active one carries the app's red accent underline. */
        /* Header row: tab strip at the left, title after it, one seam under
           both. The title is pushed to the far end so the strip keeps its
           place whatever the view is called. */
        .st-key-ldihead {
            align-items: flex-end !important;
            gap: 0.9rem !important;
            border-bottom: 2px solid #d9d9d9;   /* structural, not an accent */
            margin-bottom: 0.9rem;
        }
        .st-key-ldihead .st-key-ldi_sub {
            width: auto !important;
            flex: 0 0 auto !important;
        }
        .st-key-ldihead [data-testid="stElementContainer"]:has(.setlabel) {
            margin-left: auto !important;
        }
        /* The set picker is a switch, not a third row of tabs: one pill track with
           the chosen set lifted out of it. Deliberately a different idiom from the
           view tabs above, so the two rows do not read as the same control. */
        /* The element container is content-sized by default, which squeezed the
           three equal segments; stretch it to the tree column. */
        .st-key-text_set_pick { margin-bottom: 0.6rem; width: 100% !important; }
        /* The track spans the tree column, so equal thirds are wide enough for
           "Comparanda" without clipping. */
        .st-key-text_set_pick [data-testid="stButtonGroup"] { width: 100% !important; }
        .st-key-text_set_pick [data-baseweb="button-group"] {
            display: flex !important;
            position: relative;
            /* Three 80px segments, not the full column width. */
            width: 244px !important;
            max-width: none !important;   /* Streamlit caps it at fit-content */
            gap: 0 !important;
            background: #EDEBE7;
            border: 1px solid #E0DBD2;
            border-radius: 999px;
            padding: 2px;
        }
        /* The thumb: one white pill that slides under the labels. The three
           segments are equal thirds, so its travel is a plain percentage —
           no measuring, and it animates because Streamlit reuses the group
           element across reruns and only the active attribute changes. */
        .st-key-text_set_pick [data-baseweb="button-group"]::before {
            content: "";
            position: absolute;
            top: 2px; left: 2px;
            height: calc(100% - 4px);
            width: calc((100% - 4px) / 3);
            border-radius: 999px;
            background: #fff;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.16);
            transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
            pointer-events: none;
        }
        .st-key-text_set_pick [data-baseweb="button-group"]:has(
            button:nth-of-type(2)[kind="segmented_controlActive"])::before {
            transform: translateX(100%);
        }
        .st-key-text_set_pick [data-baseweb="button-group"]:has(
            button:nth-of-type(3)[kind="segmented_controlActive"])::before {
            transform: translateX(200%);
        }
        @media (prefers-reduced-motion: reduce) {
            .st-key-text_set_pick [data-baseweb="button-group"]::before { transition: none; }
        }
        .st-key-text_set_pick button {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            position: relative;            /* label rides above the thumb */
            z-index: 1;
            background: transparent !important;
            border: none !important;
            border-radius: 999px !important;
            box-shadow: none !important;
            padding: 0.12rem 0.18rem !important;
            font-size: 0.7rem !important;      /* fits "Comparanda" in an 80px segment */
            font-weight: 600 !important;
            color: #6B655D !important;
            white-space: nowrap;
            transition: color 180ms ease;
        }
        /* The label sits in an inner <p> with its own 14px size — set it there, or
           the segment ellipsises however small the button's font-size is. */
        .st-key-text_set_pick button p {
            font-size: 0.7rem !important;
            font-weight: 600 !important;
            line-height: 1.5 !important;
            margin: 0 !important;
        }
        .st-key-text_set_pick button:hover { color: #111 !important; }
        .st-key-text_set_pick button[data-testid="stBaseButton-segmented_controlActive"],
        .st-key-text_set_pick button[kind="segmented_controlActive"] {
            background: transparent !important;   /* the thumb paints it */
            color: #C0271F !important;
            box-shadow: none !important;
        }
        .st-key-ldi_sub { margin-bottom: 0; }
        .st-key-ldi_sub [data-baseweb="button-group"] {
            gap: 0.2rem;
            justify-content: flex-start;
        }
        /* Folder tabs: white, sitting on the seam; the open one greys and
           lifts clear of it. */
        .st-key-ldi_sub button {
            background: #fff !important;
            border: 1px solid #e2e2e2 !important;
            border-bottom: none !important;
            border-radius: 8px 8px 0 0 !important;
            box-shadow: none !important;
            padding: 0.3rem 0.9rem !important;
            margin-bottom: -2px !important;
            color: #5a5a5a !important;
            font-weight: 600 !important;
        }
        .st-key-ldi_sub button:hover {
            background: #f6f6f6 !important; color: #111 !important;
        }
        .st-key-ldi_sub button[data-testid="stBaseButton-segmented_controlActive"],
        .st-key-ldi_sub button[kind="segmented_controlActive"],
        .st-key-ldi_sub button[aria-checked="true"] {
            background: #e0e0e0 !important;
            border-color: #c4c4c4 !important;
            color: #1a1a1a !important;
            padding-bottom: 0.42rem !important;
            font-weight: 700 !important;
            /* inset, so the red edge costs no height and nothing shifts */
            box-shadow: inset 0 3px 0 0 #D32F2F !important;
        }
        .st-key-ldi_sub button[data-testid="stBaseButton-segmented_controlActive"]:hover,
        .st-key-ldi_sub button[kind="segmented_controlActive"]:hover {
            background: #d8d8d8 !important;
        }
        /* "Text set" heads its options; it is not a widget label. */
        .setlabel {
            font-size: 1.75rem; font-weight: 600; color: #1f1f1f;
            line-height: 1.2; margin: 0 0.15rem 0.75rem 0.1rem; white-space: nowrap;
        }
        /* Tablet explorer (LDI ▸ Text): rows, not buttons. Strip the chrome so
           the tree reads like a file list — flat, left-aligned, hover-highlighted. */
        /* Sticky tree. The rule must sit on the COLUMN, not on the container
           inside it: the column is the flex child, and while it stretches to the
           row's full height `position: sticky` has no distance to travel and
           looks like it does nothing. align-self stops that stretch. */
        [data-testid="stColumn"]:has([class*="st-key-tabtree"]) {
            position: sticky !important;
            top: 0.5rem;
            align-self: flex-start !important;
            max-height: calc(100vh - 2.5rem);
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 6px;
        }
        [data-testid="stColumn"]:has([class*="st-key-tabtree"])::-webkit-scrollbar { width: 7px; }
        [data-testid="stColumn"]:has([class*="st-key-tabtree"])::-webkit-scrollbar-thumb {
            background: #d6dbe1; border-radius: 4px;
        }
        [data-testid="stColumn"]:has([class*="st-key-tabtree"])::-webkit-scrollbar-thumb:hover {
            background: #b9c1ca;
        }
        /* no ancestor may clip it, or sticky is ignored outright */
        [data-testid="stHorizontalBlock"]:has([class*="st-key-tabtree"]) { overflow: visible !important; }
        [class*="st-key-tabtree"] [data-testid="stButton"] { margin: 0 !important; }
        [class*="st-key-tabtree"] button {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            border-radius: 3px !important;
            padding: 1px 6px !important;
            min-height: 0 !important;
            width: 100% !important;
            text-align: left !important;
            justify-content: flex-start !important;
            font-size: 0.86rem !important;
            line-height: 1.5 !important;
            color: #222 !important;
        }
        [class*="st-key-tabtree"] button > div,
        [class*="st-key-tabtree"] button [data-testid="stMarkdownContainer"] {
            width: 100% !important;
            text-align: left !important;
            display: block !important;
        }
        [class*="st-key-tabtree"] button p {
            text-align: left !important;
            margin: 0 !important;
            font-weight: 400 !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        /* the columns used for indenting must not add their own gap */
        [class*="st-key-tabtree"] [data-testid="stHorizontalBlock"] { gap: 0 !important; }

        [class*="st-key-tabtree"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
        [class*="st-key-tabtree"] button:hover { background: #eef2f7 !important; }
        /* the open tablet: marked by weight and a rule, not a filled button */
        [class*="st-key-tabtree"] button[kind="primary"],
        [class*="st-key-tabtree"] button[data-testid="stBaseButton-primary"] {
            background: #e8eef6 !important;
            color: #0d47a1 !important;
        }
        [class*="st-key-tabtree"] button[kind="primary"] p,
        [class*="st-key-tabtree"] button[data-testid="stBaseButton-primary"] p {
            font-weight: 600 !important;
        }
        /* discipline rows sit slightly heavier than the tablets under them */
        [class*="st-key-tabtree"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]
            > [data-testid="stButton"] > button p { font-weight: 500 !important; }
        [class*="st-key-tabtree"] [data-testid="stCaptionContainer"] {
            margin: 2px 0 0 10px !important;
            font-size: 0.72rem !important;
            letter-spacing: .04em;
            text-transform: uppercase;
            color: #8a8a8a !important;
        }
        /* Hand cursor on the open dropdown menu (selectbox option list).
           BaseWeb renders the menu in a portal, so target it broadly. */
        ul[role="listbox"], ul[role="listbox"] *,
        [role="option"], [role="option"] *,
        [data-baseweb="menu"], [data-baseweb="menu"] *,
        [data-baseweb="popover"] li {
            cursor: pointer !important;
        }
        </style>
    """, unsafe_allow_html=True)

load_css()

# --- Core Logic: Annotation ---

LOGOGRAM_PARTICLES = {'DIŠ', 'BAD', 'BE', 'UD', 'AŠ'}
IGNORE_TOKENS = {'x', '($___$)', '.', '..', '...'}

# Number-logograms: bare numerals that are logographic writings of a word —
# 15 = ZAG "right", 150 = GUB₃ "left", 30 = Sîn (moon-god). Counted as logograms
# (both word-level and sign-level); otherwise they fall through to "other".
NUMBER_LOGOGRAMS = {'15', '150', '30'}

# Function words written with a SINGLE sign (monograms): the prepositions ina (=AŠ)
# and ana. Lowercase, so they count as syllabic throughout; the ina/ana column
# of every report table shows what counting them as logographic would give.
# See docs/ldi-sign-level.md.
MONOGRAM_PARTICLES = {'ina', 'ana'}
SIGN_BOUNDARY = re.compile(r'[.\-]')   # signs within a word are joined by '.' or '-'

# Fully-restored span "[ … ]" (non-nesting). Used for the preserved-only view,
# which drops the editor's reconstructions while keeping damaged-but-legible '#'
# signs. Mirrors compute_ratios.strip_restored so the app and the batch script
# agree token-for-token.
RESTORED_SPAN = re.compile(r'\[[^\[\]]*\]')

def strip_restored(text):
    """Replace fully-restored '[ … ]' spans with '...' (an ignored token).
    Half-broken words keep their preserved part: 'KU[Š₅-túm]' -> 'KU ...'."""
    prev = None
    out = text
    while prev != out:                       # collapse nested/adjacent spans
        prev = out
        out = RESTORED_SPAN.sub(' ... ', out)
    return out.replace('[', ' ... ').replace(']', '')  # drop dangling brackets

def _omen_has_signal(sub):
    """Per-row boolean: True if the row's omen carries real linguistic signal.

    A 'content-less' omen is one whose only surviving scorable token is the omen
    particle (DIŠ/AŠ/BE/…) with everything else broken or lost — e.g. '[DIŠ ...] x#'
    or a bare '[...]'. A lone DIŠ is not evidence of logographic writing, so such
    omens are dropped from every LDI (they still count as omens and still display).
    Signal = any phonetic token, or any logogram that is NOT an omen particle."""
    is_signal = sub['type'].isin(['logogram', 'phonetic']) & (
        (sub['type'] == 'phonetic') | ~sub['token'].isin(LOGOGRAM_PARTICLES))
    keys = [sub['filename'], sub['omen_id']] if 'filename' in sub.columns else [sub['omen_id']]
    return is_signal.groupby(keys).transform('any')

def _drop_contentless(sub):
    """Drop content-less omens (see _omen_has_signal) before pooling an LDI.

    Uses the precomputed `_signal` column when the frame carries one (see
    enrich_signs) — that turns a groupby per call into a mask lookup."""
    if 'omen_id' not in sub.columns or sub.empty:
        return sub
    if '_signal' in sub.columns:
        return sub[sub['_signal']]
    return sub[_omen_has_signal(sub)]

def _drop_particles(sub):
    """Drop the omen-opening particle (DIŠ/BE/BAD/AŠ/UD) from a scored slice.

    The particle is a logographic writing of *šumma* and is counted by default, but
    it is also boilerplate — one guaranteed logogram per omen — so an analysis may
    prefer to treat it as structural markup rather than as text. Apply after
    _drop_contentless, so an omen that is nothing but its particle is already gone."""
    if sub.empty or 'token' not in sub.columns:
        return sub
    return sub[~((sub['type'] == 'logogram') & sub['token'].isin(LOGOGRAM_PARTICLES))]

def word_composition(nl, nph):
    """Split scored words into pure-logographic / mixed / syllabic shares.

    `nl`/`nph` are per-word logographic and phonetic SIGN counts. The three LDI
    measures are summaries of these three proportions, so reporting the shares
    alongside the index shows what the number is made of: two texts can agree in
    bin and still differ several-fold in how much of their logography carries a
    phonetic complement. Returns (pure %, mixed %, syllabic %, scored words)."""
    nl, nph = pd.Series(nl).reset_index(drop=True), pd.Series(nph).reset_index(drop=True)
    scored = (nl + nph) > 0
    nl, nph = nl[scored], nph[scored]
    n = int(len(nl))
    if not n:
        return float('nan'), float('nan'), float('nan'), 0
    pure = int(((nl > 0) & (nph == 0)).sum())
    mixed = int(((nl > 0) & (nph > 0)).sum())
    syll = int(((nl == 0) & (nph > 0)).sum())
    return 100 * pure / n, 100 * mixed / n, 100 * syll / n, n

def _sign_counts(token):
    """Per-sign (logogram, phonetic) counts for one word token, splitting on '.'/'-'.
    Uppercase sign -> logogram, lowercase -> phonetic; matches compute_ratios."""
    nl = nph = 0
    for s in SIGN_BOUNDARY.split(str(token)):
        if not s:
            continue
        # NB an illegible 'x' *inside* a word (ku-x) is counted as a phonetic sign
        # here, because compute_ratios.annotate_signs does the same: it drops a
        # token only when the whole token is an IGNORE_TOKEN. Matching that is
        # deliberate — the corpus figures in the article come from that path, so
        # the app must reproduce it rather than silently improve on it.
        if s.rstrip('?!') in NUMBER_LOGOGRAMS:
            nl += 1
        elif any(c.isupper() for c in s):
            nl += 1
        elif any(c.islower() for c in s):
            nph += 1
    return nl, nph

# Broad Period Mapping
# Sub-phases (Early/Late) fold into their main period so the diachronic
# comparison uses the three broad buckets: Old / Middle / Neo.
PERIOD_MAPPING = {
    "Old Babylonian": "Old Babylonian",
    "Early Old Babylonian": "Old Babylonian",
    "Late Old Babylonian": "Old Babylonian",
    "Old Assyrian": "Old Babylonian",
    "Middle Babylonian": "Middle Babylonian/Assyrian",
    "Early Middle Babylonian": "Middle Babylonian/Assyrian",
    "Late Middle Babylonian": "Middle Babylonian/Assyrian",
    "Middle Assyrian": "Middle Babylonian/Assyrian",
    "Neo-Assyrian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Neo Babylonian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Neo-Babylonian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Late Babylonian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Late-Babylonian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Neo-Assyrian / Late Babylonian": "Neo-Babylonian/Assyrian + Late Babylonian",
}

# Display names for the (normalized) genre keys, shown in the UI/charts.
REPORT_COLS = ["texts", "omens", "bin", "macro", "micro",
               "ina/ana", "restor.", "no particle",
               "pure %", "mixed %", "syll %"]
REPORT_LDI_COLS = ["bin", "macro", "micro", "ina/ana", "restor.", "no particle"]

STANDARD_CAPTION = (
    "Baseline: particle counted, ina/ana syllabic, restorations counted. "
    "**ina/ana**, **restor.** and **no particle** give bin under each of those "
    "conventions instead; the last three columns are the word composition the "
    "three measures summarise.")

def report_style(df_):
    """Shade the LDI columns; keep the counts plain."""
    cols = [c for c in REPORT_LDI_COLS if c in df_.columns]
    return (df_.style
            .set_properties(subset=cols, **{'background-color': '#f2f2f2'})
            .set_table_styles([
                {'selector': '', 'props': [('border-collapse', 'collapse')]},
                {'selector': 'th.col_heading',
                 'props': [('text-align', 'center'), ('padding', '4px 10px')]},
                {'selector': 'th.row_heading',
                 'props': [('text-align', 'left'), ('padding', '4px 10px')]},
                {'selector': 'td', 'props': [('text-align', 'center'),
                                             ('padding', '4px 10px'),
                                             ('border-bottom', '1px solid #f0f0f0')]},
            ]))

GENRE_DISPLAY = {
    "astrology": "Astrological Omens",
    "diagnostic": "Diagnostic Omens",
    "extispicy": "Extispicy",
    "izbu": "Teratological Omens",
    "terrestrial": "Terrestrial Omens",
}

LEGEND_HTML = (
    '<div style="font-size:0.85rem; text-align:right">'
    '<span class="determinative">det</span> <span class="logogram">LOGOGRAM</span> · '
    '<span class="phonetic">phonetic</span> · '
    '<span class="particle">particle</span> · '
    '<span class="monogram">monogram (ina/ana)</span> · '
    '<span class="sux">Sumerian</span></div>'
)

@st.fragment
def metric_block(key, build):
    """Run a measure switch and the chart it drives as one fragment.

    Without this, changing bin/macro/micro reruns the whole script: every chart on
    the page is recomputed and every element greys out. Inside a fragment only
    this block reruns, so only this chart is rebuilt and only this chart fades.
    `build` takes the chosen measure and draws the figure."""
    build(metric_control(key))

def metric_control(key):
    """Which measure the chart below plots: bin, macro or micro (label hidden).

    Called immediately before the chart it drives, so the switch and the line it
    moves are read together. The three convention checkboxes that used to stand
    beside it — count ina/ana as logographic, drop restorations, drop the opening
    particle — are gone: every standard report table now carries those variants
    as columns, so a reader sees what each decision is worth instead of switching
    it on and reading the figure twice. The charts hold the canonical convention
    throughout. Returns the metric name."""
    # Wide enough that the three options never wrap onto a second line.
    c1, c3, _spacer = st.columns([2.7, 0.35, 6.95], vertical_alignment="center")
    metric = c1.radio(
        "metric", ["bin", "macro", "micro"], horizontal=True,
        key=f"{key}_metric", label_visibility="collapsed")
    # Always-visible link to the full explanation (no underline).
    c3.markdown(
        '<a href="?nav=Introduction" title="Full explanation on the Introduction tab" '
        'style="text-decoration:none; font-size:1.2rem; color:#1976D2;">ⓘ</a>',
        unsafe_allow_html=True)
    return metric

def _table_to_markdown(df):
    """GitHub-flavoured Markdown for a (possibly MultiIndex-column) DataFrame.
    The index becomes the leading column; multi-level column headers are flattened."""
    def _col(c):
        if isinstance(c, tuple):
            return " ".join(str(x) for x in c if str(x) != "").strip()
        return str(c)
    def _esc(s):
        return str(s).replace("|", "\\|")
    headers = [_esc(df.index.name or "")] + [_esc(_col(c)) for c in df.columns]
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for idx, row in df.iterrows():
        cells = [_esc(idx)] + [_esc(v) for v in row.tolist()]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)

def render_table_with_copy(styler, source_df, key, label="📋 Copy table…"):
    """Render a Styler HTML table with a dropdown beside it that copies it to the
    clipboard in the chosen format: rich HTML (pastes as a real table into Excel /
    Word / Sheets), Markdown, or tab-separated text. Falls back to plain text if
    the rich-clipboard API is unavailable (e.g. a non-secure context).

    The control sits to the right of the table rather than under it: the tables are
    narrower than the page, so the space is there, and a caption or the next
    heading then follows the table directly."""
    table_html = styler.to_html()
    _row = st.container(horizontal=True, vertical_alignment="top",
                        key=f"cprow_{key}")
    with _row:
        st.markdown(table_html, unsafe_allow_html=True)

    payload_html = json.dumps(table_html)
    payload_tsv = json.dumps(source_df.to_csv(sep='\t'))
    payload_md = json.dumps(_table_to_markdown(source_df))
    label_js = json.dumps(label)
    with _row:
        components.html(
            f"""
            <select id="cp_{key}" style="font:13px/1.4 'Source Sans 3',sans-serif;
                cursor:pointer;border:1px solid #ccc;border-radius:6px;background:#fff;
                padding:3px 10px;color:#1976D2;">
                <option value="">{label}</option>
                <option value="rich">Rich table (Excel / Word)</option>
                <option value="md">Markdown</option>
                <option value="tsv">Tab-separated (TSV)</option>
            </select>
            <script>
            (function() {{
                const sel = document.getElementById("cp_{key}");
                const html = {payload_html}, tsv = {payload_tsv}, md = {payload_md};
                const placeholder = {label_js};
                function flash(msg) {{
                    sel.options[0].text = msg;
                    sel.selectedIndex = 0;
                    setTimeout(function() {{ sel.options[0].text = placeholder; }}, 1600);
                }}
                sel.addEventListener("change", async function() {{
                    const v = sel.value;
                    if (!v) return;
                    const txt = (v === "md") ? md : tsv;
                    try {{
                        if (v === "rich") {{
                            await navigator.clipboard.write([new ClipboardItem({{
                                "text/html": new Blob([html], {{type: "text/html"}}),
                                "text/plain": new Blob([tsv], {{type: "text/plain"}})
                            }})]);
                        }} else {{
                            await navigator.clipboard.writeText(txt);
                        }}
                        flash("✅ Copied");
                    }} catch (e) {{
                        try {{
                            await navigator.clipboard.writeText(txt);
                            flash("✅ Copied (text)");
                        }} catch (e2) {{ flash("⚠️ Copy failed"); }}
                    }}
                }});
            }})();
            </script>
            """,
            height=40,
        )

EBL_BASE = "https://www.ebl.lmu.de"

def ebl_url_for(row):
    """(url, label, inferred) for a text's eBL edition, or (None, None, False).

    The link type is inferred: a real eBL URL written in the frontmatter wins; then a
    corpus chapter (its `/api/texts/.../chapters/...` path appears in the frontmatter,
    e.g. EAE 55/57) → a Corpus URL; otherwise the text is a fragment → a Library URL
    from the museum number, preferring one named in the bibliography ("eBL IM.64183")
    over the filename stem. `inferred` marks a URL we built rather than read: it follows
    eBL's standard pattern but may not resolve.

    One source of truth, because two views need different renderings of it — the Text
    view wants a marked-up line, the Sources sheet wants the bare URL."""
    blob = " ".join(str(row.get(k, "")) for k in
                    ("edition", "note", "source_note", "recension", "series", "publication"))
    m_url = re.search(r"https?://(?:www\.)?ebl\.lmu\.de/\S+", blob)
    # A corpus chapter: /api/texts/<genre/cat/idx>/chapters/<stage/name>
    m_corpus = re.search(r"/api/texts/([A-Za-z0-9/]+?)/chapters/([A-Za-z0-9/]+)", blob)
    # An explicit eBL museum number named in the bibliography, e.g. "eBL IM.64183",
    # "eBL fragment BM.33793" — more reliable than the filename, so use it next.
    m_num = re.search(r"\beBL\s+(?:fragment\s+)?([A-Za-z]+\.[0-9][\w.\-]*)", blob)
    stem = str(row.get("filename", "")).rsplit(".txt", 1)[0]

    if m_url:
        return m_url.group(0).rstrip('.,;)'), "View on eBL", False
    if m_corpus:
        return f"{EBL_BASE}/corpus/{m_corpus.group(1)}/{m_corpus.group(2)}", "Corpus", True
    if m_num:
        return f"{EBL_BASE}/library/{m_num.group(1)}", "Library", False
    if stem:
        return f"{EBL_BASE}/library/{stem}", "Library", True
    return None, None, False

EBL_WARN = ('<span title="Auto-generated from the text/museum number using eBL&#39;s standard '
            'URL pattern — it may not resolve if the text is not in eBL." '
            'style="cursor:help; color:#888;">(?)</span>')

def biblio_and_ebl_lines(row):
    """Markdown lines for the bibliography (publication / edition) and an eBL link.
    Built links carry a (?) warning (see ebl_url_for).
    Returned as a list of lines so the caller can render the whole block at once."""
    lines = []
    bib = [str(row[k]).strip() for k in ("publication", "edition")
           if isinstance(row.get(k), str) and str(row[k]).strip()]
    if bib:
        lines.append("**Bibliography:** " + " · ".join(bib))

    url, label, inferred = ebl_url_for(row)
    if url:
        lines.append(f"**eBL:** [{label}]({url})" + (f" {EBL_WARN}" if inferred else ""))
    return lines

# --- Bibliography (references.bib) ------------------------------------------
# The "Bibliography" tab renders references.bib as a formatted, searchable list.
# Citations of the form "Author YEAR" in the Sources catalogue are turned into
# in-app links (?nav=Bibliography&ref=<bibkey>) to the matching entry, and each
# entry reports which corpus sources cite it ("Cited by").
REFERENCES_BIB = "references.bib"

# LaTeX accents -> Unicode. Two syntaxes appear in the file: symbol accents
# (\'e, \"u, \={a}, \`a, \^o) and letter-named accents (\v{s}, \d{h}, \u{g}).
_TEX_SYMBOL_ACCENTS = {
    "'": {"a":"á","e":"é","i":"í","o":"ó","u":"ú","y":"ý","c":"ć","n":"ń","s":"ś",
          "z":"ź","A":"Á","E":"É","I":"Í","O":"Ó","U":"Ú"},
    '"': {"a":"ä","e":"ë","i":"ï","o":"ö","u":"ü","y":"ÿ","A":"Ä","E":"Ë","O":"Ö","U":"Ü"},
    "`": {"a":"à","e":"è","i":"ì","o":"ò","u":"ù","A":"À","E":"È"},
    "^": {"a":"â","e":"ê","i":"î","o":"ô","u":"û","A":"Â","E":"Ê","O":"Ô"},
    "=": {"a":"ā","e":"ē","i":"ī","o":"ō","u":"ū","A":"Ā","E":"Ē","I":"Ī","O":"Ō","U":"Ū"},
    "~": {"n":"ñ","a":"ã","o":"õ","N":"Ñ"},
    ".": {"z":"ż","Z":"Ż","e":"ė","c":"ċ"},
}
_TEX_LETTER_ACCENTS = {
    "v": {"s":"š","c":"č","z":"ž","r":"ř","n":"ň","e":"ě","S":"Š","C":"Č","Z":"Ž"},
    "d": {"h":"ḥ","s":"ṣ","t":"ṭ","d":"ḍ","n":"ṇ","r":"ṛ","H":"Ḥ","S":"Ṣ","T":"Ṭ"},
    "u": {"g":"ğ","a":"ă","G":"Ğ","A":"Ă"},
    "c": {"c":"ç","s":"ş","C":"Ç","S":"Ş"},
    "H": {"o":"ő","u":"ű"},
    "r": {"a":"å","A":"Å"},
}
_TEX_STANDALONE = {
    r"\ss":"ß", r"\o":"ø", r"\O":"Ø", r"\l":"ł", r"\L":"Ł",
    r"\aa":"å", r"\AA":"Å", r"\ae":"æ", r"\AE":"Æ",
}
_TEX_SUBSCRIPT = {str(d): "₀₁₂₃₄₅₆₇₈₉"[d] for d in range(10)}

def _delatex(s):
    """Render a BibTeX field value as plain Unicode text (best-effort)."""
    if not s:
        return ""
    s = re.sub(r"\\textsubscript\{([0-9]+)\}",
               lambda m: "".join(_TEX_SUBSCRIPT.get(c, c) for c in m.group(1)), s)
    s = re.sub(r"\{\\(?:itshape|it|em|emph|bfseries|bf)\s+([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:itshape|it|em|bfseries|bf)\b", "", s)
    s = re.sub(r"\\url\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\([a-zA-Z])\{([A-Za-z])\}",
               lambda m: _TEX_LETTER_ACCENTS.get(m.group(1), {}).get(m.group(2), m.group(2)), s)
    s = re.sub(r"\\(['\"`^=~.])\{?([A-Za-z])\}?",
               lambda m: _TEX_SYMBOL_ACCENTS.get(m.group(1), {}).get(m.group(2), m.group(2)), s)
    for tex, uni in _TEX_STANDALONE.items():
        s = s.replace(tex + "{}", uni).replace(tex + " ", uni + " ").replace(tex, uni)
    s = s.replace("---", "—").replace("--", "–")
    s = s.replace("\\ ", " ").replace("~", " ").replace("\\&", "&")
    s = re.sub(r"\\([.,%#_&])", r"\1", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()

def _parse_bib_fields(s):
    """Parse the `name = {value}` (or "value"/bareword) pairs of one BibTeX entry."""
    fields = {}
    i, n = 0, len(s)
    name_re = re.compile(r"\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*")
    while i < n:
        m = name_re.match(s, i)
        if not m:
            break
        name, i = m.group(1).lower(), m.end()
        if i >= n:
            break
        if s[i] == "{":
            depth, j = 0, i
            while j < n:
                if s[j] == "{": depth += 1
                elif s[j] == "}":
                    depth -= 1
                    if depth == 0: break
                j += 1
            fields[name], i = s[i+1:j], j + 1
        elif s[i] == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 1
            fields[name], i = s[i+1:j], j + 1
        else:
            j = i
            while j < n and s[j] != ",":
                j += 1
            fields[name], i = s[i:j].strip(), j
        while i < n and s[i] != ",":
            i += 1
        i += 1
    return fields

@st.cache_data
def parse_bibtex(path=REFERENCES_BIB):
    """Parse references.bib into a list of {key, type, fields} dicts."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    entries, i, n = [], 0, len(text)
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        b = text.find("{", at)
        if b < 0:
            break
        etype = text[at+1:b].strip().lower()
        depth, j = 0, b
        while j < n:
            if text[j] == "{": depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        body, i = text[b+1:j], j + 1
        if etype in ("comment", "preamble", "string"):
            continue
        comma = body.find(",")
        if comma < 0:
            continue
        key = body[:comma].strip()
        if key:
            entries.append({"key": key, "type": etype,
                            "fields": _parse_bib_fields(body[comma+1:])})
    return entries

def _bib_year(fields):
    m = re.search(r"(1[5-9]\d\d|20\d\d)", fields.get("year", ""))
    return m.group(1) if m else ""

def _bib_surnames(fields):
    """First-word/last-word surnames of each author (or editor), de-LaTeX'd."""
    raw = fields.get("author") or fields.get("editor") or ""
    out = []
    for a in re.split(r"\s+and\s+", raw):
        a = a.strip()
        if not a:
            continue
        surname = a.split(",")[0].strip() if "," in a else a.split()[-1]
        out.append(_delatex(surname))
    return out

def _fold(s):
    """Fold a name to a bare ascii key: strip accents, ß->ss, keep [a-z0-9]."""
    s = unicodedata.normalize("NFKD", _delatex(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ß", "ss").replace("ẞ", "ss").replace("ø", "o").replace("Ø", "o")
    return re.sub(r"[^a-z0-9]", "", s.lower())

@st.cache_data
def _citation_index():
    """(folded-surname, year) -> bibkey, for linking free-text 'Author YEAR' cites.
    Every author's surname is indexed individually, so a second/third author or a
    particle name still links ('Edzard 1974', 'de Zorzi 2009', 'Nikolaev 2024');
    the concatenation of all authors and of the first two disambiguate shared
    surname+year (e.g. 'Goldwasser & Soler 2024' vs 'Harel … 2024')."""
    idx = {}
    for e in parse_bibtex():
        yr = _bib_year(e["fields"])
        if not yr:
            continue
        raw_sns = _bib_surnames(e["fields"])
        forms, folded = set(), []
        for rs in raw_sns:
            f = _fold(rs)
            if f:
                folded.append(f)
                forms.add(f)
            words = rs.split()
            if len(words) > 1:                     # particle name: also index last word
                lw = _fold(words[-1])
                if lw:
                    forms.add(lw)
            for part in re.split(r"[-–]", rs):     # hyphenated: index each component
                p = _fold(part)
                if p:
                    forms.add(p)
        if folded:
            forms.add("".join(folded))
            if len(folded) >= 2:
                forms.add(folded[0] + folded[1])
        for fm in forms:
            idx.setdefault((fm, yr), e["key"])
    return idx

@st.cache_data
def _series_index():
    """(SERIES-ABBREV, number) -> bibkey, so a bare series citation ('CUSAS 18',
    'KAL 5', 'HANE/M 15') links even when no author-year is written. Built from the
    `(ABBR) N` markers in each entry's series/title, plus a few manual aliases for
    series whose entry has no parenthetical abbreviation."""
    idx = {}
    for e in parse_bibtex():
        blob = _delatex(" ".join((e["fields"].get("series", ""),
                                  e["fields"].get("title", ""))))
        for pat in (r"\(([A-Za-z][A-Za-z/]*)\)\s*([0-9][0-9/]*)",    # "(CUSAS) 18"
                    r"\(([A-Za-z][A-Za-z/]*)\s+([0-9][0-9/]*)\)"):   # "(YOS 10)"
            for m in re.finditer(pat, blob):
                idx.setdefault((m.group(1).upper(), m.group(2)), e["key"])
    idx.setdefault(("AFOBEIH", "22"), "rochberg1988")
    idx.setdefault(("WAW", "37"), "abusch2015")
    idx.setdefault(("CT", "40"), "gadd1927")
    return idx

# A year, optionally parenthesised and with a range/letter suffix: "2012", "(1988)",
# "1957-58", "1983a". Restricted to 15xx–20xx so BCE dates like "1186-1172" are skipped.
_YEAR_RE = re.compile(r"\(?((?:1[5-9]|20)\d\d)[a-z]?(?:[-–/]\d{2,4})?\)?")
# A capitalised name token (>=2 chars, ending in a letter, so initials "F." are skipped).
_NAME_TOK = re.compile(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ.'’-]*[A-Za-zÀ-ÿ]")
# Bare series citations we can resolve to an entry.
_SERIES_RE = re.compile(
    r"\b(CUSAS|KAL|HANE/M|CNI|PBS|CTN|AOAT|GMTR|StBoT|MDP|BAM|YOS|WAW|CT|TCS|AfO\s+Beih\.?)"
    r"\s+([0-9][0-9/]*)", re.I)

def _find_cite_span(window, year, idx):
    """Earliest (start-offset, bibkey) in `window` for a 1–3 token surname run that,
    together with `year`, resolves to an entry. Longer runs are tried first so a
    multi-author citation beats a bare shared surname. Returns (None, None) if none."""
    toks = list(_NAME_TOK.finditer(window))
    for i, t in enumerate(toks):
        for k in range(min(3, len(toks) - i) - 1, -1, -1):
            run = "".join(x.group(0) for x in toks[i:i + k + 1])
            key = idx.get((_fold(run), year))
            if key:
                return t.start(), key
    return None, None

def _cite_spans(text):
    """Non-overlapping (start, end, bibkey) spans for author-year and series cites."""
    aidx, sidx = _citation_index(), _series_index()
    spans = []
    for ym in _YEAR_RE.finditer(text):
        wstart = max(0, ym.start() - 60)
        rel, key = _find_cite_span(text[wstart:ym.start()], ym.group(1), aidx)
        if key:
            spans.append((wstart + rel, ym.end(), key))
    for sm in _SERIES_RE.finditer(text):
        key = sidx.get((sm.group(1).upper().replace(" ", "").replace(".", ""), sm.group(2)))
        if key:
            spans.append((sm.start(), sm.end(), key))
    spans.sort()
    kept, last_end = [], 0
    for s, e, key in spans:
        if s < last_end:                 # overlaps a span already kept -> skip
            continue
        kept.append((s, e, key))
        last_end = e
    return kept

def linkify_citations(text):
    """Wrap author-year and series citations with in-app links to their bib entry."""
    if not text:
        return text
    spans = _cite_spans(text)
    if not spans:
        return text
    out, last = [], 0
    for s, e, key in spans:
        out.append(text[last:s])
        out.append(f'<a href="?nav=Bibliography&ref={key}" '
                   f'title="{key} — see Bibliography">{text[s:e]}</a>')
        last = e
    out.append(text[last:])
    return "".join(out)

@st.cache_data
def _bib_cited_by():
    """bibkey -> sorted list of source sigla that cite it (from the catalogue)."""
    rev = {}
    for r in catalogue_rows():
        sig = r.get("_sig") or r.get("filename", "")
        blob = " ".join(str(r.get(k, "")) for k in
                        ("publication", "edition", "source", "source_note",
                         "recension", "note", "_reason"))
        for _s, _e, key in _cite_spans(blob):
            rev.setdefault(key, set()).add(sig)
    return {k: sorted(v) for k, v in rev.items()}

def normalize_genre(g):
    """Canonical short genre name: lowercased, trailing 'omen(s)' dropped,
    synonyms merged (e.g. 'astrological omens' -> 'astrology')."""
    if not g:
        return "Unspecified"
    g = re.sub(r'\s+omens?$', '', g.strip().lower())
    synonyms = {
        "astrological": "astrology",
    }
    return synonyms.get(g, g) if g else "Unspecified"

# --- Sources catalogue (the "Sources" tab) -------------------------------------
# A live "Catalogue of Sources" built straight from every text's YAML frontmatter,
# grouped by discipline -> period, used vs. excluded. Kept in sync with the print
# appendix produced by scripts/build_catalogue.py (same fields, same grouping).
CAT_DISCIPLINE = {
    "astrological omens": "Celestial / Astrological (Enūma Anu Enlil)",
    "terrestrial omens":  "Terrestrial (Šumma Ālu)",
    "izbu omens":         "Teratological (Šumma Izbu)",
    "extispicy omens":    "Extispicy (bārûtu)",
    "diagnostic omens":   "Diagnostic / Medical (Sakikkû)",
    "extispicy model":    "Extispicy models & orientation texts",
    "lecanomancy":        "Lecanomancy",
    # a witness to EAE 15, held out of the astrology counts as a parallel
    "astrology (EAE 15 parallel)": "Celestial / Astrological (Enūma Anu Enlil)",
    # not divination at all — these two are genres, not disciplines of it
    "prayer":             "Other genres (comparanda)",
    "incantation":        "Other genres (comparanda)",
}
CAT_DISCIPLINE_ORDER = [
    "Celestial / Astrological (Enūma Anu Enlil)", "Terrestrial (Šumma Ālu)",
    "Teratological (Šumma Izbu)", "Extispicy (bārûtu)", "Diagnostic / Medical (Sakikkû)",
    "Extispicy models & orientation texts", "Lecanomancy",
    "Other genres (comparanda)", "Unspecified",
]
CAT_PERIOD_ORDER = [
    "Old Babylonian", "Late Old Babylonian", "Early Middle Babylonian", "Middle Babylonian",
    "Middle Assyrian", "Neo-Assyrian", "Neo-Assyrian / Late Babylonian", "Neo-Babylonian",
    "Late Babylonian",
]

def _cat_sigfmt(s):
    """Standard museum siglum from a filename stem: LETTERS.NUMBER -> 'LETTERS NUMBER'."""
    m = re.match(r'^([A-Za-z]{1,6})\.(\d.*)$', s)
    return f"{m.group(1)} {m.group(2)}" if m else s

# How each text is segmented into omens (the `counting:` frontmatter field).
_COUNTING_GLOSS = {
    "line": "one omen per transliterated line (label lists and broken texts)",
    "§":    "one omen per section marker (§)",
}
def counting_label(val):
    """Human-readable description of a text's omen-counting convention, for the
    Text-view metadata panel. Particle delimiters (DIŠ, BE, BAD, UD, AŠ, šum-ma, …)
    each open a new omen; `line` counts every line; `§` counts by section marker."""
    c = str(val or "").strip()
    if not c or c in ("-", "None", "nan"):
        return "numbered lines (fallback)"
    if c in _COUNTING_GLOSS:
        return f"{c} — {_COUNTING_GLOSS[c]}"
    return f"{c} — new omen at each opening particle “{c}”"

@st.cache_data
def catalogue_rows():
    """Parse every data/*.txt frontmatter into a row for the Sources catalogue.
    Reads the raw frontmatter (not just yaml) so the inline `# reason` after an
    `exclude:` line is preserved. Cached; use catalogue_rows.clear() to refresh."""
    rows = []
    for dp, _, fs in os.walk("data"):
        for f in sorted(fs):
            if not f.endswith(".txt"):
                continue
            txt = open(os.path.join(dp, f), encoding="utf-8").read()
            m = re.match(r'^---\s*\n(.*?)\n---', txt, re.S)
            raw = m.group(1) if m else ""
            try:
                fm = yaml.safe_load(raw) if raw else {}
                if fm and 'discipline' in fm and 'genre' not in fm:
                    fm['genre'] = fm['discipline']
            except yaml.YAMLError as e:
                # Surface it: a broken header drops the file's period/genre/counting
                # from the catalogue entirely. Usually an unquoted ': ' in a prose value.
                st.warning(f"Unparsable YAML frontmatter in {f} — metadata ignored: {e}")
                fm = {}
            fm = fm if isinstance(fm, dict) else {}
            fm["filename"] = f
            genre = str(fm.get("genre", "") or "")
            period = str(fm.get("period", "") or "Unspecified")
            fm["_discipline"] = CAT_DISCIPLINE.get(genre, "Unspecified")
            fm["_period"] = "Neo-Babylonian" if period == "Neo Babylonian" else period
            fm["_sig"] = _cat_sigfmt(f[:-4])
            fm["_excluded"] = fm.get("exclude") is True
            rm = re.search(r'^exclude:\s*true\s*#\s*(.*)$', raw, re.M)
            fm["_reason"] = rm.group(1).strip() if rm else ""
            fm["_supplementary"] = fm["_excluded"] and "supplementary" in fm["_reason"].lower()
            # data/<period>/<discipline>/<topic>/<feature>/file.txt — the layout
            # load_local_data takes its defaults from; frontmatter wins where set.
            parts = os.path.relpath(dp, "data").split(os.sep)
            fm["_topic"] = str(fm.get("topic") or
                               (parts[2].replace("-", " ") if len(parts) >= 3 else "")).strip()
            fm["_feature"] = str(fm.get("feature") or
                                 (parts[3].replace("-", " ") if len(parts) >= 4 else "")).strip()
            rows.append(fm)
    return rows

def _cat_pub(row):
    for k in ("publication", "edition", "source"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

# --- The catalogue as one sortable sheet (the Sources tab) ---------------------
# The tab renders a single flat table: every manuscript a row, every field a
# sortable column. The default order is catalogue order — museum number, letters
# before numbers — and any column header re-sorts from there.

def _cat_natkey(sig):
    """Sort key for a museum number: sigla opening with a letter come first, and the
    numbers inside compare as numbers, so 'A 63' precedes 'A 120' (a plain string sort
    would not). Sigla opening with a digit sort after all lettered ones."""
    s = str(sig or "")
    parts = [p for p in re.split(r'(\d+)', s) if p]
    return (0 if s[:1].isalpha() else 1,
            tuple((1, int(p)) if p.isdigit() else (0, p.lower()) for p in parts))

def catalogue_ldi():
    """Per-text LDI for the catalogue sheet, keyed by filename.

    Baseline conventions, the same slice trio() scores: determinatives excluded,
    content-less omens dropped, the opening particle counted, ina/ana syllabic,
    restorations counted. Covers the corpus plus the supplementary and comparanda
    sets; a text in no set (never tokenized) is simply absent.

    Cached in session state against the token count, so an import or a reset
    recomputes it; the Sources tab's ↻ Refresh drops it explicitly."""
    anns = (list(st.session_state.get('annotations', []))
            + list(st.session_state.get('supplementary', []))
            + list(st.session_state.get('comparanda', [])))
    cached = st.session_state.get('_cat_ldi')
    if cached and cached[0] == len(anns):
        return cached[1]

    out = {}
    d = pd.DataFrame(anns)
    if not d.empty and {'filename', 'omen_id', 'token', 'type'} <= set(d.columns):
        # omens are counted before content-less ones are dropped: they are still
        # omens on the tablet, they just carry no signal to score
        omens = d.drop_duplicates(subset=['filename', 'omen_id']).groupby('filename').size()
        d = _drop_contentless(d)
        d = d[d['type'].isin(['logogram', 'phonetic'])]   # determinatives excluded
        sc = list(d['token'].map(_sign_counts))
        d = d.assign(_nl=[a for a, _ in sc], _nph=[b for _, b in sc])
        den = d['_nl'] + d['_nph']
        d = d.assign(_deg=d['_nl'] / den.where(den > 0))
        g = d.groupby('filename')
        nl, nph = g['_nl'].sum(), g['_nph'].sum()
        binv, macro, words = g['type'].apply(lambda s: (s == 'logogram').mean()), g['_deg'].mean(), g.size()
        micro = nl / (nl + nph).where((nl + nph) > 0)
        # pure / mixed / syllabic shares through the app's own helper, so the sheet
        # cannot drift from the composition rows in the Text and Tools reports
        comp = {f: word_composition(sub['_nl'], sub['_nph']) for f, sub in g}
        for f in binv.index:
            pu, mx, sy, _n = comp.get(f, (float('nan'),) * 4)
            out[f] = {"bin": binv[f], "macro": macro[f], "micro": micro[f],
                      "pure": pu, "mixed": mx, "syll": sy,
                      "words": int(words[f]), "omens": int(omens.get(f, 0))}
    st.session_state['_cat_ldi'] = (len(anns), out)
    return out

# Columns shown by default; the rest are opt-in from the "add columns" picker, so
# the sheet opens readable and can be widened to the full record on demand.
CAT_COLS_DEFAULT = ["#", "Museum no.", "Status", "Period", "Chron.", "Discipline", "Topic",
                    "Publication / edition", "Provenance", "eBL", "LDI (bin)", "Omens"]
CAT_COLS_OPTIONAL = ["Era", "Region", "Feature", "Tradition", "Series / recension",
                     "Counting", "LDI (macro)", "LDI (micro)",
                     "Pure-log. %", "Mixed %", "Syllabic %", "Words scored",
                     "eBL link", "Reason (if excluded)", "Note", "File"]

# Columns the search box looks in — the prose ones. Numbers are excluded on purpose:
# typing "3" should not match every tablet with 3 omens.
CAT_SEARCH_COLS = ["Museum no.", "Status", "Period", "Era", "Discipline", "Topic", "Feature",
                   "Publication / edition", "Provenance", "Region", "Tradition",
                   "Series / recension", "Reason (if excluded)", "Note", "File"]

def catalogue_table():
    """The whole catalogue as a DataFrame: one row per manuscript, one column per
    field, in catalogue order. `_blob` (search) and `_sort` (order) are working
    columns, hidden from the sheet."""
    ldi = catalogue_ldi()
    recs = []
    for r in catalogue_rows():
        m = ldi.get(r.get("filename"), {})
        url, _label, inferred = ebl_url_for(r)
        period = r["_period"]
        prov = str(r.get("provenance") or "").strip()
        rec = {
            "Museum no.": r["_sig"],
            "Status": ("Supplementary" if r["_supplementary"]
                       else "Excluded" if r["_excluded"] else "Analysed"),
            "Period": period,
            # a sortable stand-in for the period: clicking "Period" sorts the names
            # alphabetically, which puts Late Babylonian before Old Babylonian
            "Chron.": (CAT_PERIOD_ORDER.index(period) + 1) if period in CAT_PERIOD_ORDER else None,
            "Era": period_disp(PERIOD_MAPPING.get(period, period)),
            "Discipline": r["_discipline"],
            "Topic": r.get("_topic") or "",
            "Feature": r.get("_feature") or "",
            "Publication / edition": _cat_pub(r),
            "Provenance": prov,
            "Region": region_or_unknown(prov, period),
            "eBL": url or None,
            "eBL link": "inferred" if (url and inferred) else "recorded" if url else "—",
            "LDI (bin)": m.get("bin"),
            "LDI (macro)": m.get("macro"),
            "LDI (micro)": m.get("micro"),
            "Pure-log. %": m.get("pure"),
            "Mixed %": m.get("mixed"),
            "Syllabic %": m.get("syll"),
            "Omens": m.get("omens"),
            "Words scored": m.get("words"),
            "Tradition": str(r.get("tradition") or "").strip(),
            "Series / recension": " · ".join(
                s for s in (str(r.get("series") or "").strip(),
                            str(r.get("recension") or "").strip()) if s),
            "Counting": str(r.get("counting") or "").strip(),
            "Reason (if excluded)": r["_reason"],
            "Note": " ".join(str(r.get(k) or "").strip()
                             for k in ("note", "source_note")).strip(),
            "File": r.get("filename", ""),
        }
        rec["_sort"] = _cat_natkey(r["_sig"])
        rec["_blob"] = " ".join(str(rec[k]) for k in CAT_SEARCH_COLS).lower()
        recs.append(rec)
    df = pd.DataFrame(recs).sort_values("_sort").reset_index(drop=True)
    df.insert(0, "#", range(1, len(df) + 1))
    # nullable ints, so an unscored text is blank rather than "7.0" on screen and in
    # the CSV export (a float column would carry NaN and print every count as a float)
    for c in ("Chron.", "Omens", "Words scored"):
        df[c] = df[c].astype("Int64")
    return df

# Region grouping for the Region view — by find-spot (where the manuscript was
# excavated): the southern Mesopotamian heartland (Babylonia), the northern one
# (Assyria), and sites outside Mesopotamia proper (Periphery). Multi-site canonical
# composites and unknown/siglum-only provenances belong to no single city and fall to
# "Unassigned" — shown explicitly, not silently dropped (see the Region view).
REGION_ORDER = ["Babylonia", "Assyria", "Periphery", "Tigunanum",
                "Unknown OB", "Unknown MB", "Unknown MA", "Unknown NB", "Unknown LB",
                "Unassigned"]

# Checked Periphery-first: a peripheral entry can also name a heartland site in passing
# (e.g. "imported from Assur"), and the find-spot is what we group on.
_REGION_KEYWORDS = (
    ("Tigunanum", ("tigunanum",)),   # upper-Tigris kingdom; its own group (CUSAS 18 nos 17-21)
    ("Periphery", ("hattusa", "ḫattuša", "bogazkoy", "boğazköy", "bogh", "emar",
                   "meskene", "susa", "elam", "mari", "nuzi", "ugarit", "alalakh",
                   "qatna", "ekalte", "periphery")),
    ("Assyria",   ("assur", "aššur", "nineveh", "ninive", "kuyunjik", "kalhu", "kalḫu",
                   "nimrud", "sultantepe", "huzirina", "šapiya", "sapiya")),
    ("Babylonia", ("babylon", "babylonia", "nippur", "sippar", "uruk", "warka",
                   "sealand", "kish", "borsippa", "larsa", "merkes", "southern",
                   "umma", "jokha")),
)

def provenance_to_region(prov):
    """Map a raw `provenance` string to Babylonia / Assyria / Periphery / Unassigned.

    Composites (canonical series reconstructed from manuscripts at several sites) and
    unknown or museum-siglum-only provenances have no single find-spot → 'Unassigned'."""
    if not isinstance(prov, str) or not prov.strip():
        return "Unassigned"
    p = prov.lower()
    if any(w in p for w in ("canonical", "composite", "manuscript")):
        return "Unassigned"
    for region, keys in _REGION_KEYWORDS:
        if any(k in p for k in keys):
            return region
    return "Unassigned"

# Ductus (paleographic period) abbreviations — used to bucket unprovenanced single
# tablets by script-date when there is no find-spot ("Unknown OB", "Unknown MB", …).
_DUCTUS_SHORT = {
    "Old Babylonian": "OB", "Early Old Babylonian": "OB", "Late Old Babylonian": "OB",
    "Old Assyrian": "OA",
    "Middle Babylonian": "MB", "Early Middle Babylonian": "MB", "Late Middle Babylonian": "MB",
    "Middle Assyrian": "MA",
    "Neo Babylonian": "NB", "Neo-Babylonian": "NB", "Neo-Assyrian": "NA",
    "Late Babylonian": "LB", "Late-Babylonian": "LB",
}

def region_or_unknown(prov, period_raw):
    """Region by find-spot; but a single tablet with no find-spot (provenance
    'unknown'/empty, not a multi-site composite) is bucketed by its ductus —
    'Unknown OB', 'Unknown MB', 'Unknown MA', … — instead of lumped as Unassigned."""
    base = provenance_to_region(prov)
    if base != "Unassigned":
        return base
    pl = prov.lower() if isinstance(prov, str) else ""
    if any(w in pl for w in ("canonical", "composite", "manuscript")):
        return "Unassigned"   # reconstructed multi-site text — no single tablet/find-spot
    short = _DUCTUS_SHORT.get(str(period_raw).strip())
    return f"Unknown {short}" if short else "Unassigned"

# Broad period → data/ subfolder, for saving edited/imported texts back to disk.
PERIOD_FOLDER = {
    "Old Babylonian": "old",
    "Middle Babylonian/Assyrian": "middle",
    "Neo-Babylonian/Assyrian + Late Babylonian": "new",
}
def data_path_for(period, genre, filename):
    """Where a text with this (raw) period/genre should live under data/."""
    broad = PERIOD_MAPPING.get(period, period)
    pf = PERIOD_FOLDER.get(broad, "new")
    gf = re.sub(r"[^a-z0-9]+", "-", str(genre).lower()).strip("-") or "unspecified"
    return os.path.join("data", pf, gf, filename)

# Mapping for Diachronic Analysis (Approximated for Broad Periods)
PERIOD_TO_YEAR_MAP = {
    "Old Babylonian": -1800,
    "Middle Babylonian/Assyrian": -1200,
    "Neo-Babylonian/Assyrian + Late Babylonian": -700,
}

# Chronological Order for UI Sorting
PERIOD_ORDER = [
    "Old Babylonian",
    "Middle Babylonian/Assyrian",
    "Neo-Babylonian/Assyrian + Late Babylonian"
]

# Short display labels. The full names are the data's; charts and tables show
# Old / Middle / Neo, which is what the article uses and what fits an axis tick
# or a narrow table column.
PERIOD_DISPLAY = {
    "Old Babylonian": "Old",
    "Middle Babylonian/Assyrian": "Middle",
    "Neo-Babylonian/Assyrian + Late Babylonian": "Neo",
}
def period_disp(p):
    return PERIOD_DISPLAY.get(p, p)

def get_token_type(token):
    # Rule 1: Logograms (All caps OR specific particles)
    # Check if purely uppercase alphabetic sequences (ignoring punctuation for check if needed, 
    # but simplest is .isupper() which works for "GUD")
    # Clean token for check? The prompt implies "Tokens" are space separated.
    # We might have punctuation attached. For now, we'll check the token as is.
    if token in LOGOGRAM_PARTICLES:
        return "logogram"
    if token.rstrip('?!') in NUMBER_LOGOGRAMS:  # 15/150/30 (right/left/Sîn)
        return "logogram"
    if any(c.isupper() for c in token):
        return "logogram"
    
    # Rule 2: Phonetic (Contains lowercase)
    # "i-na-at", "šum-ma"
    if any(c.islower() for c in token):
        return "phonetic"
    
    return "other" # Fallback

def _clean_for_class(s):
    """Strip damage/format markers so a token can be classified. Kept separate
    from display: '#' (half-bracket), '[ ]' (break), '|' (case divider) and the
    '!(SIGN)' corrected-sign notation all vanish for scoring only — the raw form
    with these markers is preserved for the front-end presentation."""
    s = s.replace('#', '').replace('[', '').replace(']', '').replace('|', '')
    s = re.sub(r'!\([^()]*\)', '!', s)
    return s

def annotate_omen(text, omen_id, metadata, preserved_only=False):
    # preserved_only drops the editor's '[ … ]' restorations so the LDI reflects
    # only what physically survives on the tablet (same rule as compute_ratios).
    if preserved_only:
        text = strip_restored(text)
    # Split by space first to get rough chunks
    raw_tokens = text.strip().split()
    annotations = []
    global_index = 0

    def add(token, display, t_type):
        # Each annotation carries both the cleaned `token` (drives classification
        # and every LDI count) and the raw `display` (drives the front-end, so
        # brackets and damage markers survive on screen). 'broken'-typed rows are
        # display-only: they are excluded from all scoring.
        nonlocal global_index
        ann = {"token": token, "display": display, "type": t_type,
               "omen_id": omen_id, "index": global_index}
        ann.update(metadata)
        annotations.append(ann)
        global_index += 1

    for raw_token in raw_tokens:
        # Skip line numbers (digits + dot) e.g. "1.", "1'.", or the eBL relative
        # form "a+34." — a line label, not a word to display or score.
        if re.match(r"^(?:[a-zA-Z]{1,2}\+)?\d+'?\.$", raw_token):
             continue

        clean_token_str = _clean_for_class(raw_token)

        # Empty after cleaning, a pure break/illegible marker ('...', 'x'), or a
        # ditto/restoration sign like {(U)}: keep it VISIBLE so the reader still
        # sees the damage, but type it 'broken' so it never enters an LDI count.
        if (not clean_token_str
                or clean_token_str in IGNORE_TOKENS
                or re.fullmatch(r'\{\(U\)#?\}', clean_token_str)):
            add(clean_token_str, raw_token, "broken")
            continue

        # Split the RAW token on determinatives {…}; classify each piece by its
        # cleaned form but display it with its damage markers intact.
        parts = []
        last_pos = 0
        for match in re.finditer(r'\{([^{}]+)\}', raw_token):
            if match.start() > last_pos:
                pre_text = raw_token[last_pos:match.start()]
                if pre_text:
                    parts.append({'raw': pre_text, 'clean': _clean_for_class(pre_text), 'is_det': False})
            parts.append({'raw': match.group(1), 'clean': _clean_for_class(match.group(1)), 'is_det': True})
            last_pos = match.end()
        if last_pos < len(raw_token):
            tail = raw_token[last_pos:]
            parts.append({'raw': tail, 'clean': _clean_for_class(tail), 'is_det': False})

        for i, part in enumerate(parts):
            if not part['clean']:
                # Cleaned away to nothing but still carries a visible marker
                # (e.g. a stray '[') — show it, don't score it.
                if part['raw']:
                    add(part['raw'], part['raw'], "broken")
                continue

            p_clean = part['clean']

            if part['is_det']:
                t_type = "determinative"
            else:
                # Check for God Numbers (e.g. {d}30)
                is_god_number = (p_clean.isdigit() and i > 0
                                 and parts[i-1]['is_det'] and parts[i-1]['clean'] == 'd')
                t_type = "logogram" if is_god_number else get_token_type(p_clean)

            add(p_clean, part['raw'], t_type)

    return annotations

def line_ldi(text, monogram=False, preserved=False, no_particles=False):
    """Measure one input line/omen.

    Returns (bin, macro, micro, html, words, nl, nph, composition), where
    composition is (pure %, mixed %, syllabic %, scored words) — the breakdown the
    three measures summarise.

    Same rules as the corpus: determinatives excluded, number-logograms
    (15/150/30) counted, the opening particle (DIŠ/…) counted unless
    no_particles, ina/ana optionally logographic, and restorations '[ … ]'
    optionally dropped. `html` is the colour-coded line."""
    anns = annotate_omen(text, "input", {}, preserved_only=preserved)
    parts = []
    for a in anns:
        tok, t = a['token'], a['type']
        disp = a.get('display', tok)
        if t == 'broken':
            cls = 'broken'
        elif tok in MONOGRAM_PARTICLES and t == 'phonetic':
            cls = 'monogram'
        elif t == 'logogram':
            cls = 'particle' if tok in LOGOGRAM_PARTICLES else 'logogram'
        elif t == 'determinative':
            cls = 'determinative'
        else:
            cls = 'phonetic'
        parts.append(f'<span class="{cls}">{disp}</span>')
    html = " ".join(parts)

    lp = [a for a in anns if a['type'] in ('logogram', 'phonetic')]  # determinatives excluded
    if no_particles:
        lp = [a for a in lp
              if not (a['type'] == 'logogram' and a['token'] in LOGOGRAM_PARTICLES)]
    def is_mono(a):
        return monogram and a['token'] in MONOGRAM_PARTICLES and a['type'] == 'phonetic'
    binvals = [1 if (a['type'] == 'logogram' or is_mono(a)) else 0 for a in lp]
    binv = sum(binvals) / len(binvals) if binvals else float('nan')
    nl = nph = 0
    degs = []
    per_word_l, per_word_p = [], []
    for a in lp:
        x, y = _sign_counts(a['token'])
        if is_mono(a):
            x += 1; y -= 1
        per_word_l.append(x); per_word_p.append(y)
        nl += x; nph += y
        if x + y > 0:
            degs.append(x / (x + y))
    micro = nl / (nl + nph) if (nl + nph) > 0 else float('nan')
    macro = sum(degs) / len(degs) if degs else float('nan')
    return (binv, macro, micro, html, len(lp), nl, nph,
            word_composition(per_word_l, per_word_p))

def calculate_ldi(annotations):
    # Word-level binary LDI: logograms / (logograms + phonetic). Omen particles
    # (DIŠ, BE, …) are logograms and are always counted as such.
    if not annotations:
        return 0.0

    logogram_count = 0
    total_tokens = 0

    for ann in annotations:
        if ann['type'] in ('other', 'broken'):
            continue

        if ann['type'] == 'logogram':
            logogram_count += 1

        total_tokens += 1

    if total_tokens == 0:
        return 0.0

    return logogram_count / total_tokens

# --- Helper: Mock Data ---
def generate_mock_data():
    # 50 omens spread across 1000 years
    # OB (Old Babylonian) ~ -1800 -> Less logograms
    # NA (Neo-Assyrian) ~ -700 -> More logograms
    mock_data = []
    periods = ["Old Babylonian", "Middle Babylonian", "Middle Assyrian", "Neo-Assyrian"]
    
    # We'll just generate synthetic points for the trend line
    import random
    
    years = sorted(random.sample(range(-2000, -600), 50))
    
    for i, year in enumerate(years):
        # Linearly increase prob of logogram
        # Normalized time: 0 (at -2000) to 1 (at -600)
        norm_time = (year - (-2000)) / 1400
        ldi_target = 0.3 + (0.5 * norm_time) # 0.3 to 0.8
        
        # Determine period label roughly
        if year < -1595: period = "Old Babylonian"
        elif year < -1155: period = "Middle Babylonian"
        elif year < -911: period = "Middle Assyrian"
        else: period = "Neo-Assyrian"
        
        # Create a dummy entry just for the chart - wait, the chart needs LDI.
        # We can either generate full tokens OR just store the computed LDI for the mock CSV.
        # The prompt asks for "Mock CSV with 50 omens", implying we might need text?
        # "Generate a mock CSV ... to demonstrate the trend line."
        # For simplicity, let's create a DataFrame with 'Period', 'Year', 'LDI' directly if this function is called for the CSV download.
        # But if it's for the app internal flow, we need annotations.
        # Let's mock the annotations structure to feed the LDI calculator? 
        # Actually easier to just return a DataFrame for the trend demo.
        pass # Will implement in the UI part
    
    return []

# eBL-ATF paratext handling — mirrors compute_ratios.strip_paratext so the app
# and the batch script segment identically. Discourse sections (@colophon,
# @catchline, …) are tablet furniture, not omen text; !cm/!qt/!zz open an
# eBL-ATF commentary span that !bs closes.
NON_TEXT_SECTIONS = {'colophon', 'catchline', 'date', 'signature', 'signatures',
                     'summary', 'witnesses'}
PROTOCOL_RE = re.compile(r"^((?:[a-zA-Z]{1,2}\+)?\d+'?\.\s*)?!(bs|cm|qt|zz)\b\s*(.*)$")


def strip_paratext(lines):
    """Drop paratext lines before omen segmentation (see compute_ratios)."""
    out = []
    in_paratext = False
    in_commentary = False
    for line in lines:
        s = line.strip()
        if s.startswith('@'):
            name = s.lstrip('@').strip().lower()
            in_paratext = bool(name) and name.split()[0] in NON_TEXT_SECTIONS
            out.append(line)
            continue
        if in_paratext:
            continue
        m = PROTOCOL_RE.match(s)
        if m:
            in_commentary = m.group(2) != 'bs'
            rest = (m.group(1) or '') + (m.group(3) or '')
            if not in_commentary and m.group(3):
                out.append(rest)
            continue
        if in_commentary:
            continue
        out.append(line)
    return out


def load_local_data(base_path="data", include_excluded=False, sources=None, preserved_only=False):
    """
    Recursively load .txt files from data/old, data/middle, data/new
    Returns a list of annotations.

    include_excluded: when True, also keep texts marked `exclude: true` in their
    frontmatter (used to load the comparanda set).
    """
    all_anns = []
    
    # Map folder names to Display Periods
    folder_map = {
        "old": "Old Babylonian",
        "middle": "Middle Babylonian", 
        "new": "Neo-Assyrian" 
    }

    if not os.path.exists(base_path):
        st.error(f"Data directory '{base_path}' not found.")
        return []

    for root, dirs, files in os.walk(base_path):
        # Don't descend into _comparanda (and other "_"-prefixed) folders.
        dirs[:] = [d for d in dirs if not d.startswith('_')]
        for file in files:
            if file.endswith(".txt"):
                # Determine hierarchy
                # data / <period> / <genre> / <topic> / <feature> / file.txt
                # Deeper folders set defaults for topic (level 3) and feature
                # (level 4); shallower layouts still work. Frontmatter overrides.

                # Get relative path components
                rel_path = os.path.relpath(root, base_path)
                path_parts = rel_path.split(os.sep)

                default_period = "Unspecified"
                default_genre = "Unspecified"
                default_topic = None
                default_feature = None

                if len(path_parts) >= 1:
                    # First level is probably period
                    p_folder = path_parts[0]
                    default_period = folder_map.get(p_folder, p_folder.title())

                    if len(path_parts) >= 2:
                        # Second level is Genre (if it exists)
                        # data/old/astrology -> path_parts=['old', 'astrology']
                        default_genre = path_parts[1].title()

                    if len(path_parts) >= 3 and path_parts[2] not in ('.', ''):
                        # Third level is Topic (e.g. extispicy/lung, extispicy/liver)
                        default_topic = path_parts[2].replace('-', ' ')

                    if len(path_parts) >= 4 and path_parts[3] not in ('.', ''):
                        # Fourth level is Feature (e.g. liver/martu, liver/bab-ekallim)
                        default_feature = path_parts[3].replace('-', ' ')

                # The folders below the discipline, verbatim, for the Text tree.
                # topic/feature above are defaults that frontmatter may replace with
                # prose; this stays structural.
                _sub = [p for p in path_parts[2:] if p not in ('.', '')]

                # Full path
                file_path = os.path.join(root, file)

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    if sources is not None:        # remember raw source for the editor
                        sources[file] = {"path": file_path, "content": content}

                    # Parse Frontmatter
                    metadata = {
                        "filename": file,
                        "period": default_period,
                        "genre": default_genre,
                        "section": "Unspecified"
                    }
                    if default_topic:
                        metadata["topic"] = default_topic
                    if default_feature:
                        metadata["feature"] = default_feature
                    
                    body = content
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            yaml_content = parts[1]
                            body = parts[2]
                            try:
                                fm_data = yaml.safe_load(yaml_content)
                                if fm_data:
                                    # `discipline:` is the corpus field; `genre:`
                                    # is still read (older files, and the prayer
                                    # and incantation comparanda).
                                    if 'discipline' in fm_data and 'genre' not in fm_data:
                                        fm_data['genre'] = fm_data['discipline']
                                    metadata.update(fm_data)
                            except yaml.YAMLError as e:
                                st.warning(f"Error parsing YAML in {file}: {e}")
                    
                    # Normalize Period
                    raw_period = metadata.get("period", "Unspecified")
                    metadata["period_raw"] = raw_period   # ungrouped (ductus) period, e.g. "Middle Assyrian"
                    # defaults to raw_period if not in map (e.g. "Unspecified")
                    metadata["period"] = PERIOD_MAPPING.get(raw_period, raw_period)

                    # Normalize Genre (merge synonyms, drop "omens" suffix)
                    metadata["genre"] = normalize_genre(metadata.get("genre"))
                    metadata["subpath"] = "/".join(_sub)

                    # Skip documented comparanda / excluded texts (mirror compute_ratios),
                    # unless the caller explicitly wants them (comparanda tab).
                    if metadata.get("exclude") and not include_excluded:
                        continue

                    # Parse Body
                    current_section = "Unspecified"
                    current_omen_id = "Unknown"

                    lines = strip_paratext(body.splitlines())
                    
                    # Special parsing for counting: §
                    if metadata.get("counting") == "§":
                        # Dictionary to accumulate text for each section omen
                        # Key: omen_id, Value: list of strings (lines)
                        section_omens = {}
                        current_section_omen_id = None
                        
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            
                            if line.startswith('@'):
                                current_section = line.strip('@').title()
                                continue
                            if line.startswith('$'):
                                continue
                                
                            # Check for § marker e.g. "§1"
                            # Regex to match § followed by digits, then space, then maybe line number stuff?
                            # Example: "§1 3'. [...]"
                            # We want to extract "1" as ID and the rest as content
                            
                            # Match §<digits>
                            match = re.match(r'§(\S+)\s+(.*)', line)
                            if match:
                                current_section_omen_id = match.group(1)
                                content = match.group(2)
                                
                                if current_section_omen_id not in section_omens:
                                    section_omens[current_section_omen_id] = []
                                
                                # We also need to strip the line number if present in the rest content "3'. [...]"
                                # Using standard regex for line number at start of content
                                content = re.sub(r'^\d+\'?\.\s*', '', content)
                                section_omens[current_section_omen_id].append({'text': content, 'section': current_section})
                                
                            elif current_section_omen_id and line.startswith('§'):
                                # If it starts with § but didn't match regex (unlikely if regex is good), or new § id?
                                # Wait, if it starts with § it should match. 
                                # If it DOES NOT start with §, we SKIP it as per user instruction.
                                # "The line with only line number should be skipped"
                                pass
                        
                        # Now process the accumulated omens
                        for oid, data_list in section_omens.items():
                             # We'll take the section of the first occurrence
                             if not data_list: continue
                             
                             combined_text = " ".join([d['text'] for d in data_list])
                             first_section = data_list[0]['section']
                             
                             omen_meta = metadata.copy()
                             omen_meta['section'] = first_section
                             
                             all_anns.extend(annotate_omen(combined_text, oid, omen_meta, preserved_only))
                             
                    elif metadata.get("counting") == "line":
                        # Line counting: each physical text line is its own counting unit (omen).
                        # Section (@), ruling ($) and translation/comment (#tr.en:, etc.) lines are skipped.
                        line_counter = 0
                        for line in lines:
                            line = line.strip()
                            if not line: continue

                            if line.startswith('@'):
                                current_section = line.strip('@').title()
                                continue
                            if line.startswith('$') or line.startswith('#'):
                                continue

                            # Each counted line is a distinct omen (use line number if present)
                            id_match = re.match(r'^(\d+\'?)\.', line)
                            if id_match:
                                current_omen_id = id_match.group(1)
                            else:
                                line_counter += 1
                                current_omen_id = f"l{line_counter}"

                            line_metadata = metadata.copy()
                            line_metadata['section'] = current_section
                            all_anns.extend(annotate_omen(line, current_omen_id, line_metadata, preserved_only))

                    elif metadata.get("counting"):
                        # Generic Token Parsing (e.g. "BAD", "DIŠ")
                        # Treats the specified token as the Start-of-Omen delimiter.
                        delimiter = metadata.get("counting")
                        
                        current_omen_data = {'lines': [], 'section': "Unspecified"}
                        current_omen_id = 1
                        
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            
                            if line.startswith('@'):
                                current_section = line.strip('@').title()
                                continue
                            if line.startswith('$') or line.startswith('#'):
                                continue

                            # Check if line starts with delimiter (ignoring potential line number, brackets "12. [B]AD")
                            # Strategy: Strip brackets from the line ONLY for the check.
                            temp_line = line.replace('[', '').replace(']', '')
                            
                            # Regex: Optional line number, optional %lang marker (e.g. %sux for
                            # a Sumerian line), then the delimiter. The language marker precedes
                            # the delimiter, so a "%sux DI\u0160 \u2026" line still starts its own omen.
                            # STRICT CHECK: Delimiter must NOT be followed by digits, subscripts, letters, or hyphen.
                            # Line number may be plain (12.) or eBL relative (a+1., a+41.).
                            clean_regex = r'^(?:(?:[a-zA-Z]{1,2}\+)?\d+\'?\.\s*)?\s*(?:%\w+\s+)?' + re.escape(delimiter) + r'(?![0-9\u2080-\u2089a-zA-Z\-])'
                            
                            if re.match(clean_regex, temp_line):
                                # Flush previous omen
                                if current_omen_data['lines']:
                                    text = " ".join(current_omen_data['lines'])
                                    md = metadata.copy()
                                    md['section'] = current_omen_data['section']
                                    all_anns.extend(annotate_omen(text, str(current_omen_id), md, preserved_only))
                                    current_omen_id += 1
                                
                                # Start new omen
                                # We assume we keep the line content (including the delimiter)
                                current_omen_data = {'lines': [line], 'section': current_section}
                            
                            else:
                                # Not a start line, append to current (even if it's the start of the file)
                                # This handles cases where the start of the omen is broken/lost
                                current_omen_data['lines'].append(line)
                        
                        # Flush final omen
                        if current_omen_data['lines']:
                             text = " ".join(current_omen_data['lines'])
                             md = metadata.copy()
                             md['section'] = current_omen_data['section']
                             all_anns.extend(annotate_omen(text, str(current_omen_id), md, preserved_only))
                                     
                    else:
                        # Standard Parsing
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            
                            # Check for Section Marker
                            if line.startswith('@'):
                                current_section = line.strip('@').title()
                                continue
                                
                            # Check for comments / rulings / translation lines (#tr.en:, etc.)
                            if line.startswith('$') or line.startswith('#'):
                                continue

                            # Check for Explicit ID "1. " or "1'. "
                            id_match = re.match(r'^(\d+\'?)\.', line)
                            if id_match:
                                current_omen_id = id_match.group(1)
                                
                            # Prepare metadata for this line
                            line_metadata = metadata.copy()
                            line_metadata['section'] = current_section
                            
                            # Annotate
                            all_anns.extend(annotate_omen(line, current_omen_id, line_metadata, preserved_only))
                    
                    # Logic fix in next step or combined here if possible? 
                    # I need to change the proceeding `else:` to `elif metadata.get("counting"):` 
                    # and leave the original `else:` (lines 346+) for standard.
                    # But tool `replace_file_content` replaces a chunks.
                    # I will replace the `else:` block labeled "# Standard Parsing" with the ELIF block AND the ELSE block.

                
                except Exception as e:
                    st.warning(f"Failed to read {file}: {e}")

    return all_anns

def _load_both(tmp):
    """Parse a staged dir in both modes → (full, preserved) annotation lists."""
    return (load_local_data(tmp, include_excluded=True, preserved_only=False),
            load_local_data(tmp, include_excluded=True, preserved_only=True))

def load_uploads(txt_files=None, zip_bytes=None):
    """Ingest uploaded material by staging it in a temp dir and running it through
    load_local_data — so frontmatter and every counting mode work exactly as for the
    built-in corpus. Session only: the temp dir is removed once parsed.
    Returns (full, preserved) annotation lists so both display modes stay populated."""
    full, pres = [], []
    if txt_files:
        tmp = tempfile.mkdtemp(prefix="omen_txt_")
        try:
            for f in txt_files:
                with open(os.path.join(tmp, os.path.basename(f.name)), "wb") as out:
                    out.write(f.getvalue())
            f_, p_ = _load_both(tmp); full += f_; pres += p_
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if zip_bytes:
        tmp = tempfile.mkdtemp(prefix="omen_zip_")
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                z.extractall(tmp)
            f_, p_ = _load_both(tmp); full += f_; pres += p_
        except zipfile.BadZipFile:
            st.error("That file is not a valid .zip archive.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return full, pres

def _ingest_text(filename, content):
    """Stage one constructed .txt (frontmatter + ATF) in a temp dir and parse it via
    load_local_data. Returns (full, preserved) annotation lists."""
    tmp = tempfile.mkdtemp(prefix="omen_fetch_")
    try:
        with open(os.path.join(tmp, filename), "w", encoding="utf-8") as f:
            f.write(content)
        return _load_both(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _reload_corpus():
    """Reload the whole data/ corpus into memory (after writing files to disk),
    in both display modes (full + preserved)."""
    src = {}
    st.session_state['annotations'] = load_local_data(sources=src, preserved_only=False)
    st.session_state['annotations_pres'] = load_local_data(preserved_only=True)
    st.session_state['text_sources'] = src

def _front_pg(content):
    """Read period/genre from a text's YAML frontmatter (to choose its data/ path)."""
    period, genre = "Unspecified", "Unspecified"
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                period = fm.get('period', period)
                genre = fm.get('discipline', fm.get('genre', genre))
            except Exception:
                pass
    return period, genre

def _persist_text(filename, content, period=None, genre=None):
    """Write a text into data/ at its period/genre-derived path; return the path."""
    if period is None or genre is None:
        period, genre = _front_pg(content)
    path = data_path_for(period, genre, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return path

def _commit_import(filename, content, period, genre, save_to_data, mode):
    """Persist a fetched text to data/ (+ reload) or add/replace it in-session.
    Returns (status, path): status in {'saved', 'session', 'empty'}."""
    if save_to_data:
        path = _persist_text(filename, content, period, genre)
        _reload_corpus()
        return "saved", path
    anns, anns_p = _ingest_text(filename, content)
    if not anns:
        return "empty", None
    if mode.startswith("Replace"):
        st.session_state['annotations'] = anns
        st.session_state['annotations_pres'] = anns_p
    else:
        st.session_state['annotations'] = st.session_state.get('annotations', []) + anns
        st.session_state['annotations_pres'] = st.session_state.get('annotations_pres', []) + anns_p
    st.session_state.setdefault('text_sources', {})[filename] = {
        "path": data_path_for(period, genre, filename), "content": content}
    return "session", None

def _save_text_edit(filename, new_content):
    """Write an edited text back to data/, re-parse it, and swap its annotations in
    (session + disk). Preserves the resolved period/genre if the file lacks frontmatter."""
    sources = st.session_state.setdefault('text_sources', {})
    path = sources.get(filename, {}).get('path') or os.path.join("data", "_edited", filename)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_content)
    except Exception as e:
        st.error(f"Could not write {path}: {e}")
        return False
    sources[filename] = {"path": path, "content": new_content}

    old = [a for a in st.session_state.get('annotations', []) if a.get('filename') == filename]
    new_anns, new_pres = _ingest_text(filename, new_content)
    for lst in (new_anns, new_pres):
        if lst and old:   # keep folder-derived period/genre if the re-parse lost them
            if lst[0].get('period') in (None, "Unspecified") and old[0].get('period'):
                for a in lst:
                    a['period'] = old[0]['period']
            if lst[0].get('genre') in (None, "Unspecified") and old[0].get('genre'):
                for a in lst:
                    a['genre'] = old[0]['genre']
    st.session_state['annotations'] = [a for a in st.session_state.get('annotations', [])
                                       if a.get('filename') != filename] + new_anns
    st.session_state['annotations_pres'] = [a for a in st.session_state.get('annotations_pres', [])
                                            if a.get('filename') != filename] + new_pres
    return True

@st.dialog("Edit text", width="large")
def edit_text_dialog(filename):
    src = st.session_state.get('text_sources', {}).get(filename, {})
    content = src.get('content', "")
    st.caption(f"Editing **{filename}** — full eBL-ATF including the YAML frontmatter. "
               "On save it is written to `data/` and re-analysed.")
    if not content:
        st.warning("No editable source is available for this text in this session.")
    if _HAS_ACE:
        edited = st_ace(value=content, language="yaml", theme="github", wrap=True,
                        show_gutter=True, auto_update=True, font_size=14, height=440,
                        key=f"ace_{filename}")
    else:
        st.caption("Install `streamlit-ace` (`pip install streamlit-ace`) for a richer editor.")
        edited = st.text_area("ATF", value=content, height=440, key=f"ta_{filename}",
                              label_visibility="collapsed")
    c1, c2 = st.columns(2)
    if c1.button("💾 Save & re-analyse", type="primary", key=f"save_{filename}"):
        if _save_text_edit(filename, edited):
            st.rerun()
    if c2.button("Cancel", key=f"cancel_{filename}"):
        st.rerun()

def _ebl_genre(genres):
    """Map an eBL `genres` field (hierarchical subject tags) to our internal genre key."""
    blob = ""
    for g in genres or []:
        cats = g.get("category", []) if isinstance(g, dict) else [g]
        blob += " " + " ".join(str(c) for c in cats)
    t = blob.lower()
    for key, kw in (("izbu", "teratolog"), ("astrology", "astrolog"),
                    ("diagnostic", "diagnostic"), ("terrestrial", "terrestrial"),
                    ("extispicy", "extispic")):
        if kw in t:
            return key
    return "Unspecified"

def fetch_ebl_fragment(frag_id):
    """Fetch a fragment from the eBL fragmentarium API. Returns (atf_body, meta).
    Raises on network/HTTP error. The API is public (no auth)."""
    url = f"{EBL_BASE}/api/fragments/{urllib.parse.quote(frag_id)}"
    req = urllib.request.Request(url, headers={"User-Agent": "logograms-analyser"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.load(resp)
    body_lines = []
    for line in data.get("text", {}).get("lines", []):
        if line.get("type") == "TextLine":
            toks = [t.get("displayValue", t.get("value", "")) for t in line.get("content", [])]
            body_lines.append(f"{line.get('prefix', '')} {' '.join(toks)}".strip())
        elif line.get("type") == "SurfaceAtLine":
            disp = "".join(t.get("value", "") for t in line.get("content", []))
            body_lines.append("@" + disp.lstrip("@"))
    meta = {
        "museum": frag_id,
        "period": (data.get("script") or {}).get("period") or "Unspecified",
        "genre": _ebl_genre(data.get("genres")),
        "publication": data.get("publication") or "",
        "n_lines": sum(1 for l in data.get("text", {}).get("lines", []) if l.get("type") == "TextLine"),
    }
    return "\n".join(body_lines), meta

# eBL stage codes → our period labels (PERIOD_MAPPING then folds these into the broad buckets).
_STAGE_PERIOD = {"OB": "Old Babylonian", "MB": "Middle Babylonian", "MA": "Middle Assyrian",
                 "SB": "Neo-Assyrian", "NA": "Neo-Assyrian", "NB": "Neo-Babylonian",
                 "LB": "Late Babylonian", "JN": "Late Babylonian", "Per": "Late Babylonian"}
# eBL corpus (genre, category) → our genre key.
_CORPUS_GENRE = {("D", "1"): "astrology", ("D", "2"): "terrestrial"}

def parse_corpus_path(raw):
    """Pull (genre, category, index, stage, name) from a corpus URL / api path / bare path."""
    m = re.search(r"/api/texts/([^/]+)/([^/]+)/([^/]+)/chapters/([^/]+)/([^/?#]+)", raw)
    if m:
        return m.groups()
    m = re.search(r"/corpus/([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/?#]+)", raw)
    if m:
        return m.groups()
    parts = [p for p in raw.strip().strip("/").split("/") if p]
    return tuple(parts) if len(parts) == 5 else None

def fetch_ebl_corpus(genre, category, index, stage, name):
    """Fetch a corpus chapter and return its composite (reconstructed) ATF + meta.
    The chapter score is large, so allow a longer timeout."""
    url = f"{EBL_BASE}/api/texts/{genre}/{category}/{index}/chapters/{stage}/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": "logograms-analyser"})
    with urllib.request.urlopen(req, timeout=120) as resp:   # chapter score is large/slow
        data = json.load(resp)
    body_lines, n = [], 0
    for line in data.get("lines", []):
        if line.get("isBeginningOfSection"):
            body_lines.append("")
        variants = line.get("variants") or []
        if not variants:
            continue
        text = str(variants[0].get("reconstruction", "")).split("\n")[0].strip()
        if not text:
            continue
        body_lines.append(f"{line.get('number', '')}. {text}")
        n += 1
    meta = {
        "genre": _CORPUS_GENRE.get((str(genre), str(category)), "Unspecified"),
        "period": _STAGE_PERIOD.get(str(stage).upper(), "Neo-Assyrian"),
        "n_lines": n,
        "manuscripts": len(data.get("manuscripts", [])),
        "path": f"{genre}/{category}/{index}/chapters/{stage}/{name}",
    }
    return "\n".join(body_lines), meta

# --- UI Setup ---

# --- Header: title (left, acts as Home) + nav tabs (right) on one line,
#     sharing a bottom border that reads as the tab strip's baseline. ---
NAV = ["LDI", "Sources", "Bibliography", "Tools"]
_PAGES = ["Introduction"] + NAV
# The four LDI analyses used to be top-level tabs; they now live as sub-views
# inside the single "LDI" tab, switched by a lazy selector (only the chosen one
# renders). "Overview" is the former "Global" page.
LDI_SUBPAGES = ["Overview", "Discipline", "Region", "Topics", "Text"]
_LEGACY_SUB = {"Global": "Overview", "Genre": "Discipline", "Text": "Text",     # old ?nav= targets → LDI subpage
               "Region": "Region", "Topics": "Topics"}

# In-app links (e.g. "?nav=Introduction" inside markdown/tables) navigate here.
# A "&ref=<bibkey>" (from a linkified citation) opens the Bibliography on that entry.
_qp_nav = st.query_params.get("nav")
_qp_ref = st.query_params.get("ref")
if _qp_nav in _PAGES:
    st.session_state['page'] = _qp_nav
elif _qp_nav in _LEGACY_SUB:
    # Old bookmarks (?nav=Global|Genre|Region|Topics) → the LDI tab, right sub-view.
    st.session_state['page'] = "LDI"
    st.session_state['ldi_sub'] = _LEGACY_SUB[_qp_nav]
if _qp_ref:
    st.session_state['bib_ref'] = _qp_ref
    if _qp_nav not in _PAGES:
        st.session_state['page'] = "Bibliography"
if _qp_nav is not None or _qp_ref is not None:
    st.query_params.clear()

# A Genre-node click parks a navigation request here; apply it before the nav renders.
if 'goto_nav' in st.session_state:
    st.session_state['page'] = st.session_state.pop('goto_nav')
if 'goto_sub' in st.session_state:          # e.g. a node click opening LDI ▸ Text
    st.session_state['ldi_sub'] = st.session_state.pop('goto_sub')
st.session_state.setdefault('page', "Introduction")
st.session_state.setdefault('ldi_sub', "Overview")

def _nav_to(p):
    st.session_state['page'] = p

with st.container(key="appheader"):
    h_title, h_nav = st.columns([7, 5], vertical_alignment="bottom")
    with h_title:
        with st.container(horizontal=True, vertical_alignment="bottom", key="brandrow"):
            if _MARK_URI:
                st.markdown(f'<img class="brandmark" src="{_MARK_URI}" alt="" width="54" height="54"/>',
                            unsafe_allow_html=True)
            st.button("The Logogram Density Index (LDI)", key="home_btn",
                      on_click=_nav_to, args=("Introduction",))
    with h_nav:
        nav_cols = st.columns(len(NAV))
        for i, p in enumerate(NAV):
            nav_cols[i].button(
                p, key=f"nav_{p}", use_container_width=True,
                type="primary" if st.session_state['page'] == p else "secondary",
                on_click=_nav_to, args=(p,))

page = st.session_state['page']

# Highlight the active tab reliably (independent of Streamlit's primary-button markup).
if page in NAV:
    st.markdown(
        f"<style>.st-key-nav_{page} button {{ color:#D32F2F !important; "
        f"border-bottom:3px solid #D32F2F !important; }}</style>",
        unsafe_allow_html=True)

# State Management — the local corpus loads by default; the Import tab can
# replace it or add to it (session only). BOTH the full and the preserved-only
# (restorations dropped) token sets are loaded, so each chart can switch between
# them independently via its own "drop restorations" control. The preserved set
# uses the same strip_restored rule as compute_ratios, so the numbers agree.
if 'annotations' not in st.session_state:
    st.session_state['annotations'] = []

if not st.session_state['annotations']:
    _src = {}
    st.session_state['annotations'] = load_local_data(sources=_src, preserved_only=False)
    st.session_state['annotations_pres'] = load_local_data(preserved_only=True)
    st.session_state['text_sources'] = _src

# Comparanda (kept out of the main corpus) — both modes, loaded once.
if 'comparanda' not in st.session_state:
    _csrc = {}
    st.session_state['comparanda'] = load_local_data(
        "data/_comparanda", include_excluded=True, sources=_csrc, preserved_only=False)
    st.session_state['comparanda_pres'] = load_local_data(
        "data/_comparanda", include_excluded=True, preserved_only=True)
    st.session_state.setdefault('text_sources', {}).update(_csrc)

# Supplementary witnesses (data/kal5) — held out of the LDI counts but browsable
# in the Text tab alongside the corpus and comparanda.
if 'supplementary' not in st.session_state:
    st.session_state['supplementary'] = load_local_data(
        "data/kal5", include_excluded=True, preserved_only=False)
    st.session_state['supplementary_pres'] = load_local_data(
        "data/kal5", include_excluded=True, preserved_only=True)

# --- UI: Main Layout ---

if page == "Introduction":
    # Landing / index — a companion-to-the-article introduction.
    st.markdown("### A Digital Tool for Analyzing Logographic Density in Cuneiform Omen Texts")
    st.markdown(
        "_Introduction — to be written._\n\n"
        "This application is a companion to **[article title / citation — to fill in]**. "
        "It measures the **Logogram Density Index (LDI)** of cuneiform omen texts — the "
        "proportion of each omen written with logograms rather than syllabically — and tracks "
        "how it shifts across the Old, Middle, and Neo periods.\n\n"
        "**How to use it** — the LDI tab holds five views:\n\n"
        "- **Overview** — the diachronic trend: pooled LDI per period, then per discipline.\n"
        "- **Discipline** — one node per text; click a node to open that tablet in the Text view.\n"
        "- **Region** — the same by find-spot, and discipline against region.\n"
        "- **Topics** — by sub-chapter: liver regions and lung, celestial body and phenomenon.\n"
        "- **Text** — a single tablet, colour-coded sign by sign, with per-line and whole-text "
        "LDI. The **Text set** switch beside the views opens the comparanda and the KAL 5 "
        "supplement, both held out of the corpus counts.\n\n"
        "Every chart has a **bin / macro / micro** switch directly above it. The counting "
        "conventions are not switches: each report table prints them as columns — *ina*/*ana* "
        "read as logographic, the editor's restorations dropped, the omen-opening particle "
        "(DIŠ, BE, …) dropped — beside the baseline figure, so you can see what each decision "
        "is worth instead of toggling it and reading the chart twice."
    )

    st.divider()
    st.markdown("#### The three LDI measures")
    st.markdown(
        "The same text can be scored three ways. "
        "They differ in **what counts as the unit** — the whole word, or the individual sign — "
        "and in how they treat **mixed words** (a logogram carrying a phonetic complement, "
        "e.g. `LUGAL-um`) and **determinatives** (`{d}`, `{ki}`, …):\n\n"
        "- **bin — word-level binary.** Every word is scored 0 or 1: a word counts as logographic "
        "if it contains *any* logogram. `LUGAL-um` counts as fully logographic. "
        "Determinatives are excluded.\n"
        "- **macro — per-word graded, then averaged.** Each word gets a fraction = its logographic "
        "signs ÷ its total signs (so `LUGAL-um` = 0.5), and the omen's score is the **mean of the "
        "word fractions**. Determinatives are excluded.\n"
        "- **micro — strict per-sign.** Pool every sign in the slice: logographic signs ÷ all signs. "
        "Long words weigh more than short ones. Determinatives are excluded."
    )

    st.markdown("**Worked example** — the omen `DIŠ LUGAL-um i-na-aḫ` "
                "(*“If the king …”*; DIŠ and LUGAL are logograms, *-um* is a phonetic complement, "
                "*i-na-aḫ* is spelled out syllabically):")
    st.markdown(
        "| Word | Signs | logographic signs | bin (word) | macro (word fraction) |\n"
        "|------|-------|:-----------------:|:----------:|:---------------------:|\n"
        "| `DIŠ` | DIŠ | 1 / 1 | logographic = 1 | 1.00 |\n"
        "| `LUGAL-um` | LUGAL · um | 1 / 2 | logographic = 1 | 0.50 |\n"
        "| `i-na-aḫ` | i · na · aḫ | 0 / 3 | syllabic = 0 | 0.00 |"
    )
    st.markdown(
        "- **bin** = 2 logographic words ÷ 3 words = **0.67**\n"
        "- **macro** = mean(1.00, 0.50, 0.00) = **0.50**\n"
        "- **micro** = 2 logographic signs ÷ 6 signs total = **0.33**\n\n"
        "Same text, three numbers, and only one ordering is guaranteed: **bin ≥ macro** always, "
        "since a word containing a logogram scores 1 in bin and at most 1 in macro. **macro and "
        "micro are not ordered** — macro weighs every word alike, micro weighs each by its number "
        "of signs, so which is greater depends on whether a text's long words are its logographic "
        "ones. Across this corpus micro is the greater in 7 of the 196 texts and in 10.6 % of "
        "omens, and in three texts it exceeds even bin. Comparing the three is a quick read on "
        "*how* a text is logographic — whole-word substitution versus dense sign-by-sign writing."
    )

    st.divider()
    st.markdown("#### The ina / ana monogram")
    st.markdown(
        "Two very common function words sit on the border between syllabic and logographic writing: "
        "the prepositions **ina** “in/on” and **ana** “to/for”. *ina* is routinely written with the "
        "single sign **AŠ**, and *ana* likewise as a one-sign unit — a **monogram**: one sign standing "
        "for a whole word. They look syllabic (lowercase in transliteration), so **by default the "
        "analyzer counts them as syllabic**.\n\n"
        "Because they recur constantly, they can noticeably move a score. Every report table therefore "
        "carries an **ina/ana** column: the same slice scored with the two monograms read as logograms, "
        "printed beside the baseline rather than swapped in for it, so you can see how much of a text's "
        "logographic density rests on them. Of the conventions reported here this one moves the corpus "
        "furthest — pooled bin rises from 0.679 to 0.735 — and single tablets move further still: a "
        "heavily *ina*-laden Middle Assyrian eclipse tablet rises from bin 0.744 to 0.857."
    )

elif page == "Tools":
    # --- Measure a single line/omen ---
    st.subheader("Measure a line")
    st.caption("Paste one transliterated line or omen (eBL-ATF: logograms UPPERCASE, "
               "syllabic lowercase, `{det}` determinatives, `[ … ]` restorations). Its LDI "
               "is computed live with the same tokenizer as the corpus.")
    line_in = st.text_area("Line / omen", key="measure_line", height=80,
                           label_visibility="collapsed",
                           placeholder="DIŠ ina {iti}BÁR AN.MI GAR-ma DINGIR ina KAN₅-šú …")
    if line_in.strip():
        # The conventions are reported, not switched: the baseline is scored once
        # and each convention is shown for what it is worth, so the reader sees the
        # figure and its sensitivity together (as in the article's specimen report).
        b, ma, mi, html, nwords, nl, nph, (pu, mx, sy, nw) = line_ldi(line_in)
        _f = lambda v: f"{v:.3f}" if pd.notna(v) else "–"
        _p = lambda v: f"{v:.1f} %" if pd.notna(v) else "–"
        v_pres = line_ldi(line_in, preserved=True)[0]
        v_mono = line_ldi(line_in, monogram=True)[0]
        v_nop = line_ldi(line_in, no_particles=True)[0]

        st.markdown(LEGEND_HTML, unsafe_allow_html=True)
        st.markdown(f'<div class="omen-line">{html}</div>', unsafe_allow_html=True)

        # The standard report, one row: the same columns every other view uses.
        _ltab = pd.DataFrame(
            [["1", str(nwords), _f(b), _f(ma), _f(mi),
              _f(v_mono), _f(v_pres), _f(v_nop), _p(pu), _p(mx), _p(sy)]],
            index=["this line"],
            columns=["texts", "omens", "bin", "macro", "micro",
                     "ina/ana", "restor.", "no particle",
                     "pure %", "mixed %", "syll %"])
        _ltab.index.name = ""
        st.table(report_style(_ltab))
        st.caption(
            f"**{nwords}** scored words · **{nl}** logographic signs · **{nph}** "
            "syllabic signs (determinatives excluded). "
            "Baseline: particle counted, ina/ana syllabic, restorations counted; "
            "the next three columns give bin under each of those conventions "
            "instead, and the last three are the word composition the measures "
            "summarise.")
    st.divider()

    st.subheader("Import your own texts")

    save_to_data = st.checkbox(
        "💾 Save imported texts into `data/` (permanent)", value=True, key="imp_save",
        help="On: imported texts are written into the data/ folder and the corpus is reloaded, "
             "so they persist across restarts. Off: session-only (in memory until reload).")
    if save_to_data:
        st.caption("Imported texts will be **written into `data/`** and the corpus reloaded — "
                   "they become a permanent part of your local corpus.")
    else:
        st.info("**Session-only:** texts live in memory until you reload; nothing is written to disk.")

    mode = st.radio("When session-only, imported texts should…",
                    ["Add to the current corpus", "Replace the corpus (analyse only my texts)"],
                    key="imp_mode", disabled=save_to_data,
                    help="Only applies in session-only mode; when saving to data/, the full corpus is reloaded.")

    # --- Online import from eBL. The eBL API is public and CORS-open, so this also
    # works in the browser (stlite/WebAssembly) via pyodide-http; a failed fetch is
    # caught per-request below, so the offline case degrades to a graceful error
    # rather than hiding the feature. ---
    if _OFFLINE:
        st.caption("eBL import runs in your browser against the public eBL API and needs "
                   "an internet connection; if a fetch fails, paste the eBL-ATF below.")
    if True:  # eBL is no longer gated off in the stlite/WebAssembly build
        # --- Method 1: fetch straight from the eBL fragmentarium API ---
        st.markdown("#### Fetch from eBL by museum number")
        st.caption("Enter a fragmentarium number (e.g. `K.4031`, `BM.33793`) or paste its eBL URL. "
                   "The transliteration is pulled from the eBL API; genre and period are auto-detected.")
        fc1, fc2 = st.columns([3, 1], vertical_alignment="bottom")
        frag_in = fc1.text_input("eBL number / URL", key="ebl_fetch_id", placeholder="K.4031")
        counting_choice = fc2.selectbox("counting", ["line", "DIŠ", "BE", "§"], index=0,
                                        key="ebl_fetch_counting",
                                        help="How omens are delimited in this text.")
        if st.button("Fetch & import from eBL", type="primary", key="ebl_fetch_go"):
            raw = frag_in.strip()
            if not raw:
                st.warning("Enter an eBL number or URL first.")
            else:
                mm = re.search(r"/(?:library|fragmentarium|fragments)/([^/?#]+)", raw)
                frag_id = mm.group(1) if mm else raw
                try:
                    body, fmeta = fetch_ebl_fragment(frag_id)
                except Exception as e:
                    body, fmeta = None, None
                    st.error(f"Could not fetch “{frag_id}” from eBL: {e}")
                if body is not None and fmeta is not None:
                    if fmeta["n_lines"] == 0 or not body.strip():
                        st.warning(f"“{frag_id}” has no transliterated lines in eBL.")
                    else:
                        pub = f"eBL fragment {frag_id}"
                        if fmeta["publication"]:
                            pub += f"; {fmeta['publication']}"
                        content = (f"---\ngenre: {fmeta['genre']}\nperiod: {fmeta['period']}\n"
                                   f"counting: {counting_choice}\npublication: {pub}\n---\n"
                                   f"@text\n{body}\n")
                        status, path = _commit_import(f"{frag_id}.txt", content, fmeta['period'],
                                                      fmeta['genre'], save_to_data, mode)
                        if status == "empty":
                            st.warning("Fetched, but produced no countable tokens.")
                        else:
                            where = f"saved to `{path}`" if status == "saved" else "added (session-only)"
                            st.success(f"Imported **{frag_id}** ({where}) — genre **{fmeta['genre']}**, "
                                       f"period **{fmeta['period']}**, {fmeta['n_lines']} lines.")
                            with st.expander("Show fetched eBL-ATF"):
                                st.code(content, language="text")

        # --- Method 2: fetch a canonical corpus chapter (EAE, Šumma Ālu, …) ---
        st.markdown("#### Fetch a corpus chapter from eBL")
        st.caption("Paste a corpus chapter URL (e.g. `https://www.ebl.lmu.de/corpus/D/1/4/SB/57` for "
                   "EAE 57) or its `genre/category/index/stage/name` path. The composite (reconstructed) "
                   "text is pulled — the chapter score is large, so this can take a few seconds.")
        cc1, cc2 = st.columns([3, 1], vertical_alignment="bottom")
        corpus_in = cc1.text_input("Corpus URL / path", key="ebl_corpus_id", placeholder="D/1/4/SB/57")
        corpus_counting = cc2.selectbox("counting", ["DIŠ", "line", "BE", "§"], index=0,
                                        key="ebl_corpus_counting",
                                        help="Canonical omens are usually delimited by the DIŠ protasis marker.")
        if st.button("Fetch & import corpus chapter", type="primary", key="ebl_corpus_go"):
            parsed = parse_corpus_path(corpus_in.strip())
            if not corpus_in.strip():
                st.warning("Enter a corpus URL or path first.")
            elif not parsed:
                st.error("Could not read a corpus path — expected genre/category/index/stage/name, "
                         "e.g. `D/1/4/SB/57`.")
            else:
                g, c, i, stg, nm = parsed
                try:
                    cbody, cmeta = fetch_ebl_corpus(g, c, i, stg, nm)
                except Exception as e:
                    cbody, cmeta = None, None
                    st.error(f"Could not fetch corpus chapter {g}/{c}/{i}/{stg}/{nm}: {e}")
                if cbody is not None:
                    if cmeta["n_lines"] == 0 or not cbody.strip():
                        st.warning("That corpus chapter returned no composite lines.")
                    else:
                        content = (f"---\ngenre: {cmeta['genre']}\nperiod: {cmeta['period']}\n"
                                   f"counting: {corpus_counting}\n"
                                   f"publication: eBL corpus {cmeta['path']} ({cmeta['manuscripts']} mss)\n"
                                   f"edition: fetched from /api/texts/{cmeta['path']}\n---\n"
                                   f"@text\n{cbody}\n")
                        fname = f"eBL-corpus-{g}{c}{i}-{stg}{nm}.txt"
                        status, path = _commit_import(fname, content, cmeta['period'],
                                                      cmeta['genre'], save_to_data, mode)
                        if status == "empty":
                            st.warning("Fetched, but produced no countable tokens.")
                        else:
                            where = f"saved to `{path}`" if status == "saved" else "added (session-only)"
                            st.success(f"Imported corpus **{cmeta['path']}** ({where}) — "
                                       f"genre **{cmeta['genre']}**, period **{cmeta['period']}**, "
                                       f"{cmeta['n_lines']} lines ({cmeta['manuscripts']} mss).")
                            with st.expander("Show fetched eBL-ATF"):
                                st.code(content, language="text")

    st.divider()
    st.markdown("#### …or paste / upload manually")

    st.markdown(
        "Texts are read in **eBL-ATF** — the ATF transliteration of the "
        "[electronic Babylonian Library](https://www.ebl.lmu.de/). The cleanest workflow is to "
        "**edit and save your text in eBL first**, then bring the transliteration here: that keeps "
        "logograms (UPPERCASE), syllabic signs (lowercase), determinatives `{…}`, restorations "
        "`[…]` and illegible signs `x` in the conventions the analyzer expects "
        "([ATF reference](https://www.ebl.lmu.de/about/projects))."
    )
    st.markdown("Each file is a `.txt` with a **YAML frontmatter** header followed by the ATF body:")
    st.code(
        "---\n"
        "discipline: extispicy     # astrology | diagnostic | extispicy | izbu | terrestrial\n"
        "period: Neo-Assyrian      # folded into Old / Middle / Neo automatically\n"
        "provenance: Assur (N4)\n"
        "counting: DIŠ             # DIŠ | BE | § | line — how omens are delimited\n"
        "publication: ...          # optional bibliography\n"
        "---\n"
        "@text\n"
        "1. DIŠ ...\n"
        "2. DIŠ ...",
        language="yaml")

    st.markdown(
        "**Folder import.** A folder must mirror the built-in corpus layout — period, then genre, "
        "then optional topic/feature subfolders. Folder names set *defaults*; the YAML "
        "`period:`/`genre:` inside each file always take precedence."
    )
    st.code(
        "data/\n"
        "  old/   middle/   new/\n"
        "    extispicy/\n"
        "      liver/\n"
        "        MyTablet.txt",
        language="text")

    st.divider()

    up = st.file_uploader("Upload .txt file(s)", type="txt", accept_multiple_files=True, key="imp_txt")
    zf = st.file_uploader("…or upload a .zip of your data folder", type="zip", key="imp_zip")
    path = st.text_input("…or a folder path on this machine (local/self-hosted use only)", key="imp_path")

    if st.button("Import", type="primary", key="imp_go"):
        if save_to_data:
            # Collect raw (filename, content) from every source, then write to data/ and reload.
            items = []
            for f in (up or []):
                try:
                    items.append((os.path.basename(f.name), f.getvalue().decode("utf-8")))
                except Exception:
                    pass
            if zf:
                try:
                    with zipfile.ZipFile(io.BytesIO(zf.getvalue())) as z:
                        for n in z.namelist():
                            if n.endswith(".txt") and not n.endswith("/"):
                                items.append((os.path.basename(n), z.read(n).decode("utf-8", "replace")))
                except zipfile.BadZipFile:
                    st.error("That file is not a valid .zip archive.")
            if path.strip():
                if os.path.isdir(path.strip()):
                    for root, _d, files in os.walk(path.strip()):
                        for fn in files:
                            if fn.endswith(".txt"):
                                with open(os.path.join(root, fn), encoding="utf-8") as fh:
                                    items.append((fn, fh.read()))
                else:
                    st.error(f"Folder not found: {path}")
            if items:
                saved = [_persist_text(fn, content) for fn, content in items]
                _reload_corpus()
                st.success(f"Saved {len(saved)} text(s) into `data/` and reloaded the corpus.")
            else:
                st.warning("Nothing imported — add .txt file(s), a .zip, or a valid folder path above.")
        else:
            new_full, new_pres = load_uploads(txt_files=up, zip_bytes=(zf.getvalue() if zf else None))
            if path.strip():
                if os.path.isdir(path.strip()):
                    new_full += load_local_data(path.strip(), include_excluded=True, preserved_only=False)
                    new_pres += load_local_data(path.strip(), include_excluded=True, preserved_only=True)
                else:
                    st.error(f"Folder not found: {path}")
            if new_full:
                if mode.startswith("Replace"):
                    st.session_state['annotations'] = new_full
                    st.session_state['annotations_pres'] = new_pres
                else:
                    st.session_state['annotations'] = st.session_state['annotations'] + new_full
                    st.session_state['annotations_pres'] = st.session_state.get('annotations_pres', []) + new_pres
                n_texts = len({a.get('filename') for a in new_full})
                st.success(f"Imported {n_texts} text(s) — {len(new_full)} tokens (session-only).")
            else:
                st.warning("Nothing imported — add .txt file(s), a .zip, or a valid folder path above.")

    st.divider()
    cur_texts = len({a.get('filename') for a in st.session_state.get('annotations', [])})
    st.caption(f"Corpus currently in memory: **{cur_texts}** text(s).")
    if st.button("Reset to the built-in corpus", key="imp_reset"):
        st.session_state['annotations'] = load_local_data(preserved_only=False)
        st.session_state['annotations_pres'] = load_local_data(preserved_only=True)
        st.success("Reloaded the built-in corpus.")

elif page == "Sources":
    # --- Catalogue of Sources: one sortable sheet, live from the frontmatter ---
    # Formerly three grouped markdown parts (analysed / supplementary / excluded);
    # now a single table so any column can order it. Grouping survives as columns —
    # Status, Discipline, Period, Region — which is what the grouping encoded.
    tbl = catalogue_table()
    _by_file = {r.get("filename"): r for r in catalogue_rows()}
    _n = tbl["Status"].value_counts()

    st.subheader("Catalogue of Sources")
    st.caption(
        f"Every manuscript in the corpus ({len(tbl)}: {_n.get('Analysed', 0)} analysed, "
        f"{_n.get('Supplementary', 0)} supplementary, {_n.get('Excluded', 0)} excluded), "
        "straight from the text frontmatter. Click a column header to sort by it; click "
        "**#** to return to catalogue order (museum number, letters before numbers). "
        "Select a row for the full record, its citations and its eBL link.")

    c1, c2, c3, c4 = st.columns([3, 2.2, 2.8, 1], vertical_alignment="bottom")
    q = c1.text_input("Search (any column)", key="cat_q").strip().lower()
    statuses = c2.multiselect("Status", ["Analysed", "Supplementary", "Excluded"],
                              default=["Analysed", "Supplementary", "Excluded"],
                              key="cat_status")
    extra = c3.multiselect("Add columns", CAT_COLS_OPTIONAL, key="cat_extra",
                           help="The rest of the record: era, region, tradition, series, "
                                "counting convention, the other two LDI measures, notes.")
    if c4.button("↻ Refresh", key="cat_refresh", help="Re-read the corpus from disk"):
        catalogue_rows.clear()
        _bib_cited_by.clear()             # built from the same rows — clear it together
        st.session_state.pop('_cat_ldi', None)
        st.rerun()

    view = tbl[tbl["Status"].isin(statuses)] if statuses else tbl
    if q:
        view = view[view["_blob"].str.contains(q, regex=False, na=False)]

    cols = CAT_COLS_DEFAULT + [c for c in CAT_COLS_OPTIONAL if c in extra]
    _ldi_help = ("Baseline conventions: determinatives excluded, opening particle counted, "
                 "ina/ana syllabic, restorations counted — the same scoring as the charts. "
                 "Blank where the text is not scored (excluded sources).")
    cfg = {
        "#": st.column_config.NumberColumn(
            "#", width="small",
            help="Catalogue order: museum number, letters before numbers, numbers "
                 "compared as numbers (A 63 before A 120). Sort by this to undo a re-sort."),
        "Museum no.": st.column_config.TextColumn("Museum no.", pinned=True, width="medium"),
        "Chron.": st.column_config.NumberColumn(
            "Chron.", format="%d", width="small",
            help="Chronological rank of the period (1 = Old Babylonian). Sort by this to "
                 "put the sheet in date order — sorting the Period names alphabetically "
                 "would file Late Babylonian before Old Babylonian."),
        "Publication / edition": st.column_config.TextColumn(
            "Publication / edition", width="large",
            help="The recorded publication and excavation numbers. Select the row to "
                 "follow its citations into the Bibliography."),
        "eBL": st.column_config.LinkColumn(
            "eBL", display_text="open ↗", width="small",
            help="The online edition. Most links are built from the museum number using "
                 "eBL's standard URL pattern rather than recorded in the frontmatter, so "
                 "they may not resolve — add the “eBL link” column to see which is which."),
        "LDI (bin)": st.column_config.NumberColumn("LDI (bin)", format="%.3f", help=_ldi_help),
        "LDI (macro)": st.column_config.NumberColumn("LDI (macro)", format="%.3f", help=_ldi_help),
        "LDI (micro)": st.column_config.NumberColumn("LDI (micro)", format="%.3f", help=_ldi_help),
        "Pure-log. %": st.column_config.NumberColumn(
            "Pure-log. %", format="%.1f",
            help="Share of scored words written with logograms and no phonetic "
                 "complement — what the three measures summarise. Two texts can agree "
                 "in bin and differ several-fold here."),
        "Mixed %": st.column_config.NumberColumn(
            "Mixed %", format="%.1f", help="Share of scored words that are a logogram "
                                          "carrying a phonetic complement (LUGAL-um)."),
        "Syllabic %": st.column_config.NumberColumn(
            "Syllabic %", format="%.1f", help="Share of scored words written syllabically."),
        "Omens": st.column_config.NumberColumn("Omens", format="%d", width="small"),
        "Words scored": st.column_config.NumberColumn("Words scored", format="%d"),
        "Note": st.column_config.TextColumn("Note", width="large"),
        "Reason (if excluded)": st.column_config.TextColumn("Reason (if excluded)", width="large"),
    }

    if view.empty:
        st.info("No sources match the current search.")
    else:
        event = st.dataframe(view[cols], column_config=cfg, hide_index=True, height=620,
                             use_container_width=True, key="cat_table",
                             on_select="rerun", selection_mode="single-row")

        picked = (event.selection.rows or [None])[0] if hasattr(event, "selection") else None
        if picked is not None:
            row = view.iloc[picked]
            r = _by_file.get(row["File"], {})
            st.divider()
            h1, h2 = st.columns([3, 1], vertical_alignment="center")
            h1.markdown(f"#### {row['Museum no.']}  ·  {row['Status']}")
            # Only corpus texts open in the Text view; the comparanda and the KAL 5
            # supplement live in their own sets there and are reached from that tab.
            if row["Status"] == "Analysed" and h2.button("📖 Open in Text view",
                                                         key="cat_goto",
                                                         use_container_width=True):
                st.session_state['goto_nav'] = "LDI"
                st.session_state['goto_sub'] = "Text"
                st.session_state['goto_file'] = row["File"]
                st.rerun()

            meta = [f"**Period:** {row['Period']} ({row['Era']})",
                    f"**Discipline:** {row['Discipline']}"
                    + (f" — {row['Topic']}" if row['Topic'] else "")
                    + (f" / {row['Feature']}" if row['Feature'] else ""),
                    f"**Provenance:** {row['Provenance'] or '—'} ({row['Region']})",
                    f"**Counting:** {counting_label(r.get('counting'))}"]
            if row["Tradition"]:
                meta.append(f"**Tradition:** {row['Tradition']}")
            if row["Series / recension"]:
                meta.append(f"**Series:** {row['Series / recension']}")
            # Citations link into the Bibliography here, where the text is markdown
            # (a dataframe cell cannot carry an in-app link).
            if row["Publication / edition"]:
                meta.append("**Publication / edition:** "
                            + linkify_citations(row["Publication / edition"]))
            meta += [ln for ln in biblio_and_ebl_lines(r) if ln.startswith("**eBL:**")]
            if row["Reason (if excluded)"]:
                meta.append("**Held out because:** "
                            + linkify_citations(row["Reason (if excluded)"]))
            if pd.notna(row["LDI (bin)"]):
                meta.append(f"**LDI:** bin {row['LDI (bin)']:.3f} · macro "
                            f"{row['LDI (macro)']:.3f} · micro {row['LDI (micro)']:.3f} "
                            f"({int(row['Omens'])} omens, {int(row['Words scored'])} scored words)")
            if row["Note"]:
                meta.append(f"**Note:** {row['Note']}")
            st.markdown("  \n".join(meta), unsafe_allow_html=True)

    # --- Supplementary data (downloads) ---
    st.divider()
    st.markdown("#### Supplementary data")
    _cat_md = os.path.join("docs", "catalogue-of-sources.md")
    _kal5_csv = os.path.join("docs", "kal5-ldi-by-tradition.csv")
    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇ This table (CSV)",
                       data=view[cols].to_csv(index=False).encode("utf-8"),
                       file_name="catalogue-of-sources.csv", mime="text/csv",
                       key="cat_view_dl", use_container_width=True,
                       help="Exactly the rows and columns shown, in the order shown.")
    if os.path.exists(_cat_md):
        d2.download_button("⬇ Catalogue of Sources (Markdown)",
                           data=open(_cat_md, encoding="utf-8").read(),
                           file_name="catalogue-of-sources.md", mime="text/markdown",
                           key="cat_dl", use_container_width=True,
                           help="The print appendix: the same catalogue grouped by "
                                "discipline and period.")
    if os.path.exists(_kal5_csv):
        d3.download_button("⬇ KAL 5 per-tablet LDI (CSV)",
                           data=open(_kal5_csv, encoding="utf-8").read(),
                           file_name="kal5-ldi-by-tradition.csv", mime="text/csv",
                           key="kal5_dl", use_container_width=True,
                           help="Per-tablet LDI and token counts for all 106 scored "
                                "Opferschau tablets of Heeßel 2012 (KAL 5), by tradition/period.")

elif page == "Bibliography":
    # --- Bibliography: references.bib rendered as a searchable, linkable list ---
    entries = parse_bibtex()
    cited_by = _bib_cited_by()
    active = st.session_state.pop("bib_ref", None)   # highlight target from a citation link

    st.subheader("Bibliography")
    if not entries:
        st.info("No `references.bib` found next to the app.")
    else:
        st.caption(
            f"{len(entries)} references, parsed live from `references.bib`. "
            "Citations of the form *Author YEAR* in the Sources tab link here; each entry "
            "lists the corpus sources that cite it.")

        if active and any(e["key"] == active for e in entries):
            st.success(f"Jumped to **{active}** (from a citation link). It is highlighted below.")

        q = st.text_input("Search (author · title · year · key)", key="bib_q").strip().lower()

        def _sortkey(e):
            sns = _bib_surnames(e["fields"])
            return ((sns[0].lower() if sns else "zzz"), _bib_year(e["fields"]), e["key"])

        shown = 0
        for e in sorted(entries, key=_sortkey):
            f = e["fields"]
            authors = _delatex(f.get("author") or f.get("editor") or "").replace(" and ", "; ")
            if not (f.get("author") or "").strip() and f.get("editor"):
                authors += " (ed.)"
            year = _bib_year(f) or _delatex(f.get("year", ""))
            title = _delatex(f.get("title", ""))
            series = _delatex(f.get("series", ""))
            imprint = ", ".join(x for x in (_delatex(f.get("publisher", "")),
                                            _delatex(f.get("address", ""))) if x)
            note = _delatex(f.get("note", ""))
            doi = f.get("doi", "").strip()
            url = _delatex(f.get("howpublished", "")).strip()
            link = url or (f"https://doi.org/{doi}" if doi else "")

            blob = " ".join((e["key"], authors, title, series, year, note)).lower()
            if q and q not in blob:
                continue
            shown += 1

            # Anchor so a future #ref-<key> jump can land here.
            st.markdown(f'<a id="ref-{e["key"]}"></a>', unsafe_allow_html=True)
            with st.container(border=True):
                head = f"**{authors or '—'}**"
                if year:
                    head += f" ({year})"
                head += f". *{title}*." if title else "."
                if series:
                    head += f" {series}."
                if imprint:
                    head += f" {imprint}."
                st.markdown(("⭐ " if e["key"] == active else "") + head)

                meta = [f"`{e['key']}`"]
                if link:
                    meta.append(f"[link]({link})")
                if doi and "doi.org" not in link:
                    meta.append(f"[doi:{doi}](https://doi.org/{doi})")
                st.caption(" · ".join(meta))

                if note:
                    st.caption(note)

                cb = cited_by.get(e["key"])
                if cb:
                    st.markdown("**Cited by:** " + ", ".join(
                        f"[{s}](?nav=Sources)" for s in cb), unsafe_allow_html=True)

        if q and shown == 0:
            st.caption("No references match the current search.")

elif st.session_state['annotations']:

    # --- Sign-level enrichment for graded (macro/micro) metrics ---
    # Each word token is split on '.'/'-' into signs (determinatives sit in their own
    # rows, excluded from graded metrics). These columns are MONOGRAM-INDEPENDENT;
    # the active counts are derived per chart by with_active() below.
    def enrich_signs(frame):
        frame = frame.copy()
        _sc = frame['token'].map(_sign_counts)
        frame['_nl'] = [a for a, _ in _sc]
        frame['_nph'] = [b for _, b in _sc]
        frame['_mono'] = frame['token'].isin(MONOGRAM_PARTICLES) & (frame['type'] == 'phonetic')
        # Content-less omens are decided once per frame. Every trio()/comp() call
        # would otherwise re-run the groupby behind _omen_has_signal on its slice;
        # omens never straddle a slice, so the verdict is the same either way.
        if 'omen_id' in frame.columns and not frame.empty:
            frame['_signal'] = _omen_has_signal(frame)
        return frame

    def with_active(frame, monogram):
        """Add the monogram-dependent active columns (_anl/_anph/_islog/_deg) for a
        given monogram choice, so the report can price that convention per slice."""
        frame = frame.copy()
        ma = frame['_mono'] & monogram
        frame['_anl'] = frame['_nl'] + ma.astype(int)         # active logogram-sign count
        frame['_anph'] = frame['_nph'] - ma.astype(int)       # active phonetic-sign count
        frame['_islog'] = (frame['type'] == 'logogram') | ma  # word counts as logographic (bin)
        den = frame['_anl'] + frame['_anph']
        frame['_deg'] = frame['_anl'] / den.where(den > 0)    # per-word logogram fraction (NaN if no signs)
        return frame

    def build_frames(anns, comps, supps=None):
        """Prepare one display mode's frames from a token list: the main df (genre
        display names, sign enrichment, region, section), the unique-omen frame, the
        bin/graded frames (determinatives excluded), the enriched comparanda df, and
        the enriched supplementary (data/kal5) df.
        Called once per mode — FRAMES[False] = full text, FRAMES[True] = preserved-only."""
        d = pd.DataFrame(anns)
        d['genre'] = d['genre'].map(lambda g: GENRE_DISPLAY.get(g, str(g).title()))
        d = enrich_signs(d)
        _prov = d['provenance'] if 'provenance' in d.columns else pd.Series(pd.NA, index=d.index)
        _praw = d['period_raw'] if 'period_raw' in d.columns else pd.Series(pd.NA, index=d.index)
        d['region'] = [region_or_unknown(pr, prw) for pr, prw in zip(_prov, _praw)]
        if 'section' not in d.columns:
            d['section'] = "Unspecified"
        d['section'] = d['section'].fillna("Unspecified").replace("", "Unspecified")
        uo = d.drop_duplicates(subset=['filename', 'omen_id'])
        lp = d['type'].isin(['logogram', 'phonetic'])   # determinatives excluded from bin & graded
        def _held(items):
            hd = pd.DataFrame(items or [])
            if not hd.empty:
                hd['genre'] = hd['genre'].map(lambda g: GENRE_DISPLAY.get(g, str(g).title()))
                hd = enrich_signs(hd)
            return hd
        return {'df': d, 'uo': uo, 'bframe': d[lp], 'gframe': d[lp],
                'comp': _held(comps), 'supp': _held(supps)}

    # Both display modes, so the report's "restor." column can be filled from the
    # preserved-only slice without reloading.
    # Built once per loaded corpus, not once per rerun. Every interaction — opening
    # a folder in the tree, switching a toggle, changing tab — reruns this script,
    # and build_frames maps the sign tokenizer over ~90k rows and derives the region
    # per row, twice (full text and preserved-only). Rebuilding that on a click cost
    # ~20 s a view; the annotations only change on load/import, so key the cache on
    # their size and reuse the frames until they do.
    _frames_sig = (len(st.session_state['annotations']),
                   len(st.session_state.get('annotations_pres') or ()),
                   len(st.session_state.get('comparanda') or ()),
                   len(st.session_state.get('comparanda_pres') or ()),
                   len(st.session_state.get('supplementary') or ()),
                   len(st.session_state.get('supplementary_pres') or ()))
    if st.session_state.get('_frames_sig') != _frames_sig:
        st.session_state['_frames'] = {
            False: build_frames(st.session_state['annotations'],
                                st.session_state.get('comparanda', []),
                                st.session_state.get('supplementary', [])),
            True:  build_frames(st.session_state.get('annotations_pres', st.session_state['annotations']),
                                st.session_state.get('comparanda_pres', st.session_state.get('comparanda', [])),
                                st.session_state.get('supplementary_pres', st.session_state.get('supplementary', []))),
        }
        st.session_state['_frames_sig'] = _frames_sig
    FRAMES = st.session_state['_frames']

    def pick(preserved):
        """Frame-set (df, uo, bframe, gframe, comp) for a chart's restorations choice."""
        return FRAMES[bool(preserved)]

    # Defaults = full text; each page/chart rebinds these to its own mode via pick().
    _F = FRAMES[False]
    df, unique_omens_df = _F['df'], _F['uo']
    bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

    # (bin, macro, micro) for any slice, for a given monogram setting. Omen particles
    # (DIŠ, BE, …) are logograms and are counted as such unless no_particles is set.
    def trio(sub, monogram, no_particles=False):
        sub = _drop_contentless(sub)   # lone-DIŠ / all-broken omens carry no signal
        if no_particles:
            sub = _drop_particles(sub)
        ma = sub['_mono'] & monogram
        anl = sub['_nl'] + ma.astype(int)
        anph = sub['_nph'] - ma.astype(int)
        islog = (sub['type'] == 'logogram') | ma
        is_b = sub['type'].isin(['logogram', 'phonetic'])  # determinatives excluded (as in macro/micro)
        is_g = sub['type'].isin(['logogram', 'phonetic'])
        binv = islog[is_b].mean() if is_b.any() else float('nan')
        nl, nph = anl[is_g].sum(), anph[is_g].sum()
        micro = nl / (nl + nph) if (nl + nph) > 0 else float('nan')
        den = (anl + anph)
        deg = anl / den.where(den > 0)
        macro = deg[is_g].mean() if is_g.any() else float('nan')
        return binv, macro, micro

    # Word composition (pure-logographic / mixed / syllabic) for any slice — the
    # breakdown the three measures summarise. Same conventions as trio().
    def comp(sub, monogram, no_particles=False):
        sub = _drop_contentless(sub)
        if no_particles:
            sub = _drop_particles(sub)
        sub = sub[sub['type'].isin(['logogram', 'phonetic'])]   # determinatives excluded
        ma = sub['_mono'] & monogram
        return word_composition(sub['_nl'] + ma.astype(int),
                                sub['_nph'] - ma.astype(int))

    def _fmt(v):
        return f"{v:.3f}" if pd.notna(v) else "–"

    def _pct(v):
        return f"{v:.1f} %" if pd.notna(v) else "–"

    # One horizontal report: a row per group, the measures and the conventions
    # across the columns. The conventions are reported rather than switched, so a
    # reader sees the figure and what each counting decision is worth to it at the
    # same time, rather than switching a toggle and reading the figure twice.
    def report_row(full, pres=None, uo=None):
        """One row of REPORT_COLS for a slice, always at the baseline."""
        b, ma, mi = trio(full, False)
        pu, mx, sy, nwords = comp(full, False)
        texts = str(uo['filename'].nunique()) if uo is not None else "1"
        omens = str(len(uo)) if uo is not None else str(nwords)
        return [texts, omens, _fmt(b), _fmt(ma), _fmt(mi),
                _fmt(trio(full, True)[0]),
                _fmt(trio(pres, False)[0]) if pres is not None else "–",
                _fmt(trio(full, False, True)[0]),
                _pct(pu), _pct(mx), _pct(sy)]

    def corpus_report_row():
        """The whole-corpus row, computed once per loaded corpus.

        It is identical for every text and every rerun, but costs five passes over
        ~90k rows — enough to make opening a folder in the tree feel slow."""
        if st.session_state.get('_corpus_row_sig') != _frames_sig:
            st.session_state['_corpus_row'] = report_row(
                FRAMES[False]['df'], FRAMES[True]['df'], FRAMES[False]['uo'])
            st.session_state['_corpus_row_sig'] = _frames_sig
        return st.session_state['_corpus_row']

    def standard_table(slices, index_name):
        """The standard report: one row per slice, REPORT_COLS across.

        `slices` is a list of (label, full_df, pres_df, unique_omens_df); pass
        uo=None where the row is a single text or a pasted line."""
        rows, idx = [], []
        for label, full, pres, uo in slices:
            if full is None or len(full) == 0:
                continue
            rows.append(report_row(full, pres, uo))
            idx.append(label)
        if not rows:
            return None
        out = pd.DataFrame(rows, index=idx, columns=REPORT_COLS)
        out.index.name = index_name
        return out

    def convention_table(slices, max_cols=6):
        """Groups as columns, conventions as rows — the aggregate form of the report.

        `slices` is a list of (label, full_df, pres_df). Each column is scored at
        the baseline and then under each convention in turn, so a reader can see
        both the level and how much of it depends on a counting decision. This is
        the shape the article uses for periods; it works for any grouping whose
        columns fit on the page, hence max_cols."""
        slices = [s for s in slices if s[1] is not None and not s[1].empty][:max_cols]
        if not slices:
            return None
        data = {}
        for label, full, pres in slices:
            pu, mx, sy, _n = comp(full, False)
            data[label] = [
                _fmt(trio(full, False)[0]),
                _fmt(trio(full, False)[1]),
                _fmt(trio(full, False)[2]),
                _fmt(trio(full, True)[0]),
                _fmt(trio(pres, False)[0]) if pres is not None else "–",
                _fmt(trio(full, False, True)[0]),
                _pct(pu), _pct(mx), _pct(sy)]
        return pd.DataFrame(data, index=[
            "bin (baseline)", "macro", "micro",
            "bin, ina/ana logographic", "bin, restorations dropped",
            "bin, particle excluded",
            "pure-logographic words", "mixed words", "syllabic words"])

    def report_table(full, pres, corpus_full=None, corpus_pres=None):
        """The reporting format the article recommends, as a table.

        The conventions are not switches here: the baseline (particle counted,
        ina/ana syllabic, restorations counted) is reported together with what
        each convention does to it, so a reader sees the figure and its
        sensitivity at once instead of one value at a time. The composition rows
        are what the three measures summarise. Variants are given in bin, which
        is where the paper measures them."""
        def column(f, p):
            b, ma, mi = trio(f, False)
            pu, mx, sy, _n = comp(f, False)
            return [_fmt(b), _fmt(ma), _fmt(mi), _pct(pu), _pct(mx), _pct(sy),
                    _fmt(trio(p, False)[0]) if p is not None else "–",
                    _fmt(trio(f, True)[0]),
                    _fmt(trio(f, False, True)[0])]

        rows = ["bin", "macro", "micro",
                "pure-logographic words", "mixed words", "syllabic words",
                "bin, restorations dropped", "bin, ina/ana logographic",
                "bin, particle excluded"]
        data = {"this text": column(full, pres)}
        if corpus_full is not None:
            data["whole corpus"] = column(corpus_full, corpus_pres)
        return pd.DataFrame(data, index=rows)

    def render_text_block(text_df, text_df_pres, period, title, key_prefix):
        """Shared per-text view: colour legend, whole-text LDI (all three metrics),
        the colour-coded omen lines with per-line LDI, and a per-omen LDI chart.
        Used by both the Text and Comparanda tabs. Pass the full and preserved-only
        slices of the same text; the report's "restor." column comes from the second."""
        # The measure radio is not here but just above the per-omen chart below.
        mono, pres, nopart = False, False, False   # canonical: the report table prices the variants
        text_df_full = text_df              # baseline for the report, before `pres` rebinds
        text_df = text_df_pres if pres else text_df

        # Precompute per-omen LDI + the colour-coded line HTML (used by both the
        # chart and the text below).
        omens = []
        for oid in text_df['omen_id'].unique():
            omen_tokens = text_df[text_df['omen_id'] == oid]
            # A %sux line is Sumerian — colour the whole line with the sux colour.
            is_sux = (omen_tokens['token'] == "%sux").any()
            html_parts = [f'<span class="omen-id">{oid}.</span>']
            for _, token_row in omen_tokens.iterrows():
                token_text = token_row['token']
                if token_text == "%sux":
                    continue   # language marker — drives line colour, not shown
                # Show the raw form (brackets/damage markers preserved); fall back
                # to the cleaned token for any row without a display field.
                disp = token_row['display'] if ('display' in token_row and pd.notna(token_row['display'])) else token_text
                t_type = token_row['type']
                if t_type == "broken":
                    css_class = "broken"
                elif is_sux:
                    css_class = "sux"
                elif token_text in MONOGRAM_PARTICLES and t_type == "phonetic":
                    css_class = "monogram"
                elif t_type == "logogram":
                    css_class = "particle" if token_text in LOGOGRAM_PARTICLES else "logogram"
                elif t_type == "determinative":
                    css_class = "determinative"
                else:
                    css_class = "phonetic"
                html_parts.append(f'<span class="{css_class}">{disp}</span>')
            b, ma, mi = trio(omen_tokens, mono, nopart)
            omens.append({"omen": str(oid), "html": " ".join(html_parts),
                          "bin": b, "macro": ma, "micro": mi})

        # 1) The standard report — this text against the corpus it belongs to —
        #    then the per-omen chart, at the canonical convention.
        if omens:
            st.divider()
            _tuo = text_df_full.drop_duplicates(subset=['filename', 'omen_id'])
            _cuo = FRAMES[False]['uo']
            _ttab = pd.DataFrame(
                [report_row(text_df_full, text_df_pres, _tuo), corpus_report_row()],
                index=[title, "whole corpus"], columns=REPORT_COLS)
            _ttab.index.name = ""
            if _ttab is not None:
                st.caption(STANDARD_CAPTION)
                render_table_with_copy(report_style(_ttab), _ttab,
                                       f"{key_prefix}_text_report")
            st.markdown("#### LDI per omen")
            st.markdown(f'<div class="charttitle">{title} — LDI per omen</div>',
                        unsafe_allow_html=True)
            chart_df = pd.DataFrame(omens)
            chart_df['seq'] = range(len(chart_df))
            def _chart(metric, chart_df=chart_df, period=period, title=title, text_df=text_df,
                       key_prefix=key_prefix):
                col = color_map.get(period, '#1f77b4')

                fig_text = go.Figure()
                # Grey dotted line UNDER the coloured one, bridging content-less omens
                # (lone-DIŠ / all-broken lines carry no LDI, so they leave a gap in the
                # coloured trace). connectgaps spans the gap so the reading stays visually
                # continuous without inventing a value for the broken omens.
                if chart_df[metric].isna().any():
                    fig_text.add_trace(go.Scatter(
                        x=chart_df['seq'], y=chart_df[metric], mode='lines',
                        line=dict(width=1.5, color='#BDBDBD', dash='dot'),
                        connectgaps=True, hoverinfo='skip', showlegend=False
                    ))
                fig_text.add_trace(go.Scatter(
                    x=chart_df['seq'], y=chart_df[metric], mode='lines',
                    line=dict(width=2.5, shape='spline', smoothing=1.0, color=col),
                    connectgaps=False, hoverinfo='skip', showlegend=False
                ))
                fig_text.add_trace(go.Scatter(
                    x=chart_df['seq'], y=chart_df[metric], mode='markers',
                    marker=dict(size=12, color=col, line=dict(width=1, color='white')),
                    customdata=chart_df[['omen', 'bin', 'macro', 'micro']].to_numpy(),
                    hovertemplate="omen %{customdata[0]}<br>"
                                  "bin %{customdata[1]:.2f} · macro %{customdata[2]:.2f} · micro %{customdata[3]:.2f}"
                                  "<extra></extra>",
                    showlegend=False
                ))
                # Highest / whole-text / lowest LDI, labelled at the top. "whole" is the
                # pooled LDI for the entire text (not the mean of the per-omen dots).
                ys = chart_df[metric]
                whole = trio(text_df, mono, nopart)[{"bin": 0, "macro": 1, "micro": 2}[metric]]
                fig_text.add_annotation(
                    x=(chart_df['seq'].min() + chart_df['seq'].max()) / 2, y=1.02,
                    xref='x', yref='y',
                    text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                    showarrow=False, yanchor='bottom', align='center', font=dict(size=11, color=col),
                )
                show_ticks = len(chart_df) <= 40
                fig_text.update_layout(
                    margin=dict(t=14),   # no chart title to make room for
                    template="simple_white", font_family="Arial",
                    xaxis_title="Omen (in text order)", yaxis_title=f"LDI — {metric}",
                    yaxis=dict(range=[-0.05, 1.30], tickmode='array',
                               tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
                    xaxis=dict(tickmode='array', tickvals=chart_df['seq'], ticktext=chart_df['omen'])
                          if show_ticks else dict(showticklabels=False),
                    height=480, hovermode="closest"
                )
                st.plotly_chart(fig_text, use_container_width=True, key=f"{key_prefix}_omen_ldi")
            metric_block(key_prefix, _chart)

        # 2) Text after — colour-coded omen on the left, per-line LDI on the right.
        st.divider()
        h_text, h_ldi = st.columns([5, 2])
        h_text.caption("Omen")
        h_ldi.markdown('<div class="ldi-val"><b>bin · macro · micro</b></div>', unsafe_allow_html=True)
        for o in omens:
            c_text, c_ldi = st.columns([5, 2])
            c_text.markdown(f'<div class="omen-line">{o["html"]}</div>', unsafe_allow_html=True)
            c_ldi.markdown(
                f'<div class="ldi-val">{_fmt(o["bin"])} · {_fmt(o["macro"])} · {_fmt(o["micro"])}</div>',
                unsafe_allow_html=True)

    # (Region, section, unique-omen and bin/graded frames are prepared per mode in
    # build_frames above; `df`/`unique_omens_df`/`bframe`/`gframe` default to full text
    # and each page rebinds them via pick(preserved).)

    color_map = {
        "Old Babylonian": "#1f77b4", "Middle Babylonian/Assyrian": "#ff7f0e",
        "Neo-Babylonian/Assyrian + Late Babylonian": "#2ca02c",
    }

    # Page is chosen by the header nav (built at the top of the script).
    # The five LDI views share one "LDI" tab; a lazy sub-selector picks which
    # one renders — only the chosen sub-view's body below executes, so switching
    # never recomputes the others ("auf Bestellung"). Text is one of them.
    # NB: use a distinctive name — the chart blocks below reuse `sub` as a
    # throwaway per-period DataFrame slice, so the view flag must not be `sub`.
    ldi_view = st.session_state.get('ldi_sub', "Overview")
    text_set = st.session_state.get('text_set', "Corpus")
    # Each view's title lives in the header row, not at the top of its body, so
    # the line reads: title (left) ... tabs (right). The captions below each
    # title carry what the old parentheticals said.
    LDI_TITLES = {
        "Overview": "Overview",
        "Discipline": "Discipline-Specific Analysis",
        "Region": "Regional Analysis",
        "Topics": "Topic Analysis",
        "Text": "Text",
    }
    if page == "LDI":
        # Title and tabs in ONE container, not two columns: a horizontal layout
        # puts them on a single line and lets the strip be pushed hard right
        # (margin-left:auto in the CSS) against the edge of the page.
        with st.container(horizontal=True, vertical_alignment="bottom",
                          key="ldihead"):
            # The strip comes first, so it anchors the left of the row and keeps
            # the same place whatever the title beside it says.
            # Initial selection comes from session_state['ldi_sub'] (pre-seeded
            # above / by the legacy deep-link map); no `default=` here, to avoid
            # Streamlit's "default value but also set via Session State" warning.
            ldi_view = st.segmented_control(
                "LDI view", LDI_SUBPAGES,
                key='ldi_sub', label_visibility="collapsed") or "Overview"
            st.markdown(f'<div class="setlabel">{LDI_TITLES.get(ldi_view, "LDI")}</div>',
                        unsafe_allow_html=True)

    # --- LDI ▸ Overview (formerly the "Global" tab) ---
    if page == "LDI" and ldi_view == "Overview":
        # Page-level controls drive both the LDI-by-Period table and the trend chart.
        mono, pres, nopart = False, False, False   # canonical: the report table prices the variants
        _F = pick(pres)
        df, unique_omens_df = _F['df'], _F['uo']
        bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

        # LDI by Period — texts · omens · bin · macro · micro (same styling as the
        # Genre table: shaded LDI columns, left-aligned, Period in the first column).
        st.markdown("#### LDI by Period")
        st.caption("Baseline (particle counted, ina/ana syllabic, restorations counted) "
                   "with what each convention is worth beside it, and the word composition "
                   "the three measures summarise. **Total** pools across periods.")

        def _f(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        _FULL, _PRES = FRAMES[False]['df'], FRAMES[True]['df']
        rows, idx, chart_pts = [], [], []
        for period in PERIOD_ORDER + ["Total"]:
            uo = unique_omens_df if period == "Total" else unique_omens_df[unique_omens_df['period'] == period]
            if uo.empty:
                continue
            full = _FULL if period == "Total" else _FULL[_FULL['period'] == period]
            pres = _PRES if period == "Total" else _PRES[_PRES['period'] == period]
            rows.append(report_row(full, pres, uo))
            idx.append(period_disp(period))
            if period != "Total":   # the trend chart plots periods only, not the pooled Total
                dd = df if period == "Total" else df[df['period'] == period]
                b, ma, mi = trio(dd, mono, nopart)   # canonical: the table prices the rest
                chart_pts.append({'period': period_disp(period), 'bin': b, 'macro': ma, 'micro': mi})

        if rows:
            ptdf = pd.DataFrame(rows, index=idx, columns=REPORT_COLS)
            ptdf.index.name = "Period"
            render_table_with_copy(report_style(ptdf), ptdf, "period_ldi")

        # All three LDI measures on one chart, across the broad periods (Total excluded).
        if chart_pts:
            cdf = pd.DataFrame(chart_pts)
            st.markdown("#### Diachronic LDI — bin · macro · micro")
            st.caption("All three measures on one chart across periods (the pooled **Total** "
                       "is omitted), at the canonical convention — the report above "
                       "prices each variant.")
            fig_period = go.Figure()
            for m_name, mcol in [("bin", "#1f77b4"), ("macro", "#ff7f0e"), ("micro", "#2ca02c")]:
                fig_period.add_trace(go.Scatter(
                    x=cdf['period'], y=cdf[m_name], mode="lines+markers", name=m_name,
                    line=dict(width=3, color=mcol, shape="spline", smoothing=1.3),
                    marker=dict(size=10),
                    hovertemplate=f"<b>{m_name}</b><br>%{{x}}<br>LDI = %{{y:.2f}}<extra></extra>"))
            fig_period.update_layout(
                margin=dict(t=14),   # no chart title to make room for
                template="simple_white", font_family="Arial",
                xaxis_title="Period", yaxis_title="LDI",
                yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                height=460, hovermode="x unified", legend_title_text="Measure")
            st.plotly_chart(fig_period, use_container_width=True, key="period_trio")

        st.divider()

        # Global Chart — one trend line per genre across periods
        st.subheader("Logographic Shift by Discipline (diachronic trend)")

        # The standard report, one row per discipline, pooled across periods.
        _DFULL, _DPRES, _DUO = FRAMES[False]['df'], FRAMES[True]['df'], FRAMES[False]['uo']
        _dsl = []
        for _g in sorted(_DFULL['genre'].dropna().unique(),
                         key=lambda x: -len(_DFULL[_DFULL['genre'] == x])):
            _dsl.append((str(_g), _DFULL[_DFULL['genre'] == _g],
                         _DPRES[_DPRES['genre'] == _g], _DUO[_DUO['genre'] == _g]))
        _dsl.append(("Total", _DFULL, _DPRES, _DUO))
        _dtab = standard_table(_dsl, "Discipline")
        if _dtab is not None:
            st.caption(STANDARD_CAPTION + " **Total** pools across disciplines.")
            render_table_with_copy(report_style(_dtab), _dtab, "discipline_ldi")

        if not bframe.empty:
            st.markdown('<div class="charttitle">Pooled LDI per discipline, '
                        'across periods</div>', unsafe_allow_html=True)
            bf, gf = with_active(bframe, mono), with_active(gframe, mono)
            # One pooled trend line per genre, across periods (Old -> Middle -> Neo).
            gpk = ['genre', 'period']
            t_bin = bf.groupby(gpk)['_islog'].mean().rename('bin')
            t_agg = gf.groupby(gpk).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
            t_agg['micro'] = t_agg['_nl'] / (t_agg['_nl'] + t_agg['_np']).where((t_agg['_nl'] + t_agg['_np']) > 0)
            t_n = unique_omens_df.groupby(gpk).size().rename('n')
            trend = pd.concat([t_bin, t_agg[['macro', 'micro']], t_n], axis=1).reset_index()
            trend = trend.dropna(subset=['genre', 'period'])
            trend['period'] = pd.Categorical(trend['period'], categories=PERIOD_ORDER, ordered=True)
            trend = trend.sort_values(['genre', 'period'])

            def _chart(metric, trend=trend):
                fig_trend = px.line(
                    trend, x='period', y=metric, color='genre', markers=True,
                    category_orders={'period': PERIOD_ORDER},
                    custom_data=['genre', 'n'], line_shape='spline',
                    template="simple_white"
                )
                fig_trend.update_traces(
                    line=dict(width=3, shape='spline', smoothing=1.0), marker=dict(size=11),
                    hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>"
                                  + metric + " = %{y:.3f}<br>omens = %{customdata[1]}<extra></extra>"
                )
                fig_trend.update_layout(
                    margin=dict(t=14),   # no chart title to make room for
                    font_family="Arial", xaxis_title="Period",
                    yaxis_title=f"LDI — {metric}",
                    yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                    height=780,
                    legend_title_text="Discipline", hovermode="closest"
                )
                # Two-line tick labels so the long Neo period isn't clipped.
                fig_trend.update_xaxes(tickmode='array', tickvals=PERIOD_ORDER,
                                       ticktext=[period_disp(p) for p in PERIOD_ORDER])
                st.plotly_chart(fig_trend, use_container_width=True, key="genre_trend")
                st.caption(f"Each line = one discipline; y = pooled **{metric}** LDI per period "
                           "(hover for omen counts). The radio above the chart switches measure.")
            metric_block("global", _chart)

    # --- LDI ▸ Region (find-spot: Babylonia / Assyria / Periphery) ---
    if page == "LDI" and ldi_view == "Region":
        st.caption("Texts grouped by where the manuscript was excavated — **Babylonia** "
                   "(southern heartland), **Assyria** (northern heartland), **Periphery** "
                   "(outside Mesopotamia: Ḫattuša, Emar, Susa). **Unassigned** = unknown "
                   "provenance or multi-site canonical composites, which belong to no single "
                   "city. This isolates how much of the logographic shift is *regional* rather "
                   "than diachronic — i.e. whether the LDI holds across Babylonia, Assyria and "
                   "the periphery, or splits between them.")

        mono, pres, nopart = False, False, False   # canonical: the report table prices the variants
        _F = pick(pres)
        df, unique_omens_df = _F['df'], _F['uo']
        bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

        # LDI by Region — texts · omens · bin · macro · micro (pooled across periods).
        st.markdown("#### LDI by Region")
        st.caption(STANDARD_CAPTION + " **Total** pools across regions.")

        _RFULL, _RPRES = FRAMES[False]['df'], FRAMES[True]['df']
        _rsl = []
        for region in REGION_ORDER + ["Total"]:
            uo = unique_omens_df if region == "Total" else unique_omens_df[unique_omens_df['region'] == region]
            if uo.empty:
                continue
            _rsl.append((region,
                         _RFULL if region == "Total" else _RFULL[_RFULL['region'] == region],
                         _RPRES if region == "Total" else _RPRES[_RPRES['region'] == region],
                         uo))
        rtdf = standard_table(_rsl, "Region")
        if rtdf is not None:
            rsty = report_style(rtdf)
            render_table_with_copy(rsty, rtdf, "region_ldi")

        st.divider()

        # Region trend — one line per region across periods (does the gap widen over time?).
        st.subheader("Logographic Shift by Region (diachronic trend)")

        if not bframe.empty:
            st.markdown('<div class="charttitle">Pooled LDI per region, '
                        'across periods</div>', unsafe_allow_html=True)
            bf, gf = with_active(bframe, mono), with_active(gframe, mono)
            rpk = ['region', 'period']
            r_bin = bf.groupby(rpk)['_islog'].mean().rename('bin')
            r_agg = gf.groupby(rpk).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
            r_agg['micro'] = r_agg['_nl'] / (r_agg['_nl'] + r_agg['_np']).where((r_agg['_nl'] + r_agg['_np']) > 0)
            r_n = unique_omens_df.groupby(rpk).size().rename('n')
            rtrend = pd.concat([r_bin, r_agg[['macro', 'micro']], r_n], axis=1).reset_index()
            rtrend = rtrend.dropna(subset=['region', 'period'])
            rtrend['period'] = pd.Categorical(rtrend['period'], categories=PERIOD_ORDER, ordered=True)
            rtrend = rtrend.sort_values(['region', 'period'])

            def _chart(metric, rtrend=rtrend):
                fig_region = px.line(
                    rtrend, x='period', y=metric, color='region', markers=True,
                    category_orders={'period': PERIOD_ORDER, 'region': REGION_ORDER},
                    custom_data=['region', 'n'], line_shape='spline',
                    template="simple_white"
                )
                fig_region.update_traces(
                    line=dict(width=3, shape='spline', smoothing=1.0), marker=dict(size=11),
                    hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>"
                                  + metric + " = %{y:.3f}<br>omens = %{customdata[1]}<extra></extra>"
                )
                fig_region.update_layout(
                    margin=dict(t=14),   # no chart title to make room for
                    font_family="Arial", xaxis_title="Period",
                    yaxis_title=f"LDI — {metric}",
                    yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                    height=780,
                    legend_title_text="Region", hovermode="closest"
                )
                fig_region.update_xaxes(tickmode='array', tickvals=PERIOD_ORDER,
                                        ticktext=[period_disp(p) for p in PERIOD_ORDER])
                st.plotly_chart(fig_region, use_container_width=True, key="region_trend")
                st.caption(f"Each line = one region; y = pooled **{metric}** LDI per period "
                           "(hover for omen counts). Gaps mean that region has no texts in that "
                           "period. The regional signal is strongest in the Old/Middle periods — "
                           "much first-millennium material is composite and lands in *Unassigned*.")
            metric_block("region", _chart)

        st.divider()

        # Genre × Region — controls for genre mix: does each region's LDI hold within a
        # genre, or is the regional gap just an artefact of which genres each region has?
        st.subheader("LDI by Discipline × Region")
        metric = metric_control("region_matrix")
        st.caption("Each cell is the pooled **" + metric + "** LDI for one genre in one region. "
                   "This separates a real regional effect from a genre-mix artefact — if a "
                   "region's LDI holds *within* genres, the effect is regional. Empty cells "
                   "(–) mean that genre has no texts from that region; cells from very few "
                   "omens are noisy (hover the chart for omen counts).")

        regions_present = [r for r in REGION_ORDER if (unique_omens_df['region'] == r).any()]
        genres_present = sorted(g for g in df['genre'].dropna().unique())

        grx = []
        for g in genres_present:
            for r in regions_present:
                sub = df[(df['genre'] == g) & (df['region'] == r)]
                if sub.empty:
                    continue
                b, ma, mi = trio(sub, mono, nopart)
                val = {'bin': b, 'macro': ma, 'micro': mi}[metric]
                n = unique_omens_df[(unique_omens_df['genre'] == g)
                                    & (unique_omens_df['region'] == r)].shape[0]
                grx.append({'genre': GENRE_DISPLAY.get(g, str(g).title()),
                            'region': r, 'ldi': val, 'n': n})
        grdf = pd.DataFrame(grx)

        if not grdf.empty:
            # Matrix table — genres (rows) × regions (cols), formatted LDI.
            pivot = (grdf.pivot(index='genre', columns='region', values='ldi')
                     .reindex(columns=regions_present))
            ptbl = pivot.copy()
            for c in ptbl.columns:
                ptbl[c] = pivot[c].map(lambda v: f"{v:.2f}" if pd.notna(v) else "–")
            ptbl.index.name = "Discipline"
            psty = (ptbl.style
                    .set_properties(**{'background-color': '#f2f2f2'})
                    .set_table_styles([
                        {'selector': '', 'props': [('border-collapse', 'collapse')]},
                        {'selector': 'th.col_heading', 'props': [('text-align', 'center'),
                                                                 ('padding', '4px 12px')]},
                        {'selector': 'th.row_heading', 'props': [('text-align', 'left'),
                                                                 ('padding', '4px 12px')]},
                        {'selector': 'td', 'props': [('text-align', 'center'),
                                                     ('padding', '4px 12px'),
                                                     ('border-bottom', '1px solid #f0f0f0')]},
                    ]))
            render_table_with_copy(psty, ptbl, "genre_region_matrix")

        # One diachronic chart per genre: within a genre, LDI by region across periods,
        # so the regional contrast is read genre-by-genre (e.g. extispicy = its own chart
        # with a Babylonia / Assyria / Periphery line each).
        st.markdown("#### Per-genre regional trends")
        st.caption("One chart per genre. Each line is a region across Old → Middle → Neo; a "
                   "lone marker means that region has only one period for this genre. Level "
                   "lines = the LDI is region-independent within that genre; spreading lines = "
                   "the region matters there.")

        if not bframe.empty:
            bf, gf = with_active(bframe, mono), with_active(gframe, mono)
            grp = ['genre', 'region', 'period']
            gtb = bf.groupby(grp)['_islog'].mean().rename('bin')
            gta = gf.groupby(grp).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
            gta['micro'] = gta['_nl'] / (gta['_nl'] + gta['_np']).where((gta['_nl'] + gta['_np']) > 0)
            gtn = unique_omens_df.groupby(grp).size().rename('n')
            gtr = pd.concat([gtb, gta[['macro', 'micro']], gtn], axis=1).reset_index()
            gtr = gtr.dropna(subset=['genre', 'region', 'period'])
            gtr['period'] = pd.Categorical(gtr['period'], categories=PERIOD_ORDER, ordered=True)

            for g in genres_present:
                sub = gtr[gtr['genre'] == g].sort_values(['region', 'period'])
                if sub.empty or sub[metric].dropna().empty:
                    continue
                disp = GENRE_DISPLAY.get(g, str(g).title())
                st.markdown(f'<div class="charttitle">{disp} — LDI by region '
                            f'across periods</div>', unsafe_allow_html=True)
                def _chart(metric, sub=sub, disp=disp, g=g, regions_present=regions_present):
                    fig_g = px.line(
                        sub, x='period', y=metric, color='region', markers=True,
                        category_orders={'period': PERIOD_ORDER, 'region': regions_present},
                        custom_data=['region', 'n'], line_shape='spline',
                        template="simple_white"
                    )
                    fig_g.update_traces(
                        line=dict(width=3, shape='spline', smoothing=1.0), marker=dict(size=11),
                        hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>"
                                      + metric + " = %{y:.3f}<br>omens = %{customdata[1]}<extra></extra>")
                    fig_g.update_layout(
                        margin=dict(t=14),   # no chart title to make room for
                        font_family="Arial", xaxis_title="Period",
                        yaxis_title=f"LDI — {metric}",
                        yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                        height=420, legend_title_text="Region", hovermode="closest")
                    fig_g.update_xaxes(tickmode='array', tickvals=PERIOD_ORDER,
                                       ticktext=[period_disp(p) for p in PERIOD_ORDER])
                    st.plotly_chart(fig_g, use_container_width=True, key=f"region_genre_{g}")
                metric_block(f"region_genre_{g}", _chart)

    # --- LDI ▸ Topics (intra-genre sub-chapters) ---
    if page == "LDI" and ldi_view == "Topics":
        st.caption("Omens split by **sub-chapter / subject** within a discipline — extispicy by "
                   "liver region & lung (bārûtu chapters), astrology by celestial body & "
                   "phenomenon, Sakikkû by canonical tablet, izbu by human / animal section, "
                   "Šumma Ālu by subject (snakes, lizards, house, sleep, behaviour). Each "
                   "series is edited differently, so the sub-chapter is read from whichever "
                   "field carries it. Pick a discipline below; one chart per topic, each omen "
                   "a node across the periods.")

        mono, pres, nopart = False, False, False   # canonical: the report table prices the variants
        _F = pick(pres)
        df, unique_omens_df = _F['df'], _F['uo']
        bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

        # Period labels come from PERIOD_DISPLAY (Old / Middle / Neo) like every
        # other chart and table; this alias keeps the local call sites unchanged.
        _short = period_disp

        def _section_table_style(styler):
            return (styler
                    .set_properties(**{'background-color': '#f2f2f2'})
                    .set_table_styles([
                        {'selector': '', 'props': [('border-collapse', 'collapse')]},
                        {'selector': 'th.col_heading', 'props': [('text-align', 'center'),
                                                                 ('padding', '4px 12px')]},
                        {'selector': 'th.row_heading', 'props': [('text-align', 'left'),
                                                                 ('padding', '4px 12px')]},
                        {'selector': 'td', 'props': [('text-align', 'center'),
                                                     ('padding', '4px 12px'),
                                                     ('border-bottom', '1px solid #f0f0f0')]},
                    ]))

        def _f(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        # --- Per-discipline topic labelling ---------------------------------------------
        # Every label function takes a row of that text's metadata, because each
        # series records its sub-chapter somewhere else: the folder path for
        # extispicy, `topic` for astrology, `series` for Sakikkû,
        # `canonical_tablet` for izbu, the `publication` line for Šumma Ālu.
        _TOPIC_FIELDS = ('topic', 'feature', 'series', 'canonical_tablet',
                         'publication', 'note', 'source_note', 'recension', 'subpath')

        def _blob(row, *fields):
            """The named fields as one lower-cased string, for keyword matching."""
            return " ".join(str(row.get(f) or "") for f in fields).lower()

        # Extispicy: topic/feature come from the folder path (extispicy/<topic>/<feature>).
        EXT_FEATURE = {
            "bab ekallim": "bāb ekallim", "martu": "martu", "naplastu": "naplastu",
            "padanu": "padānu", "pu": "pû", "qerbu": "qerbu",
        }
        def _ext_label(row):
            # The folder is the structural fact (extispicy/liver/martu); a few texts
            # carry prose in `topic:` instead ("manzāzu / the Station (ki.gub …)"),
            # which would otherwise split them off as chapters of their own.
            # folder names hyphenate (liver/bab-ekallim); EXT_FEATURE is keyed on spaces
            parts = [x.strip().lower().replace('-', ' ')
                     for x in str(row.get('subpath') or '').split('/') if x.strip()]
            topic, feature = row.get('topic'), row.get('feature')
            t = parts[0] if parts else (topic.strip().lower() if isinstance(topic, str) else "")
            f = (parts[1] if len(parts) > 1
                 else (feature.strip().lower() if isinstance(feature, str) else ""))
            if t == "lung":
                return "Lung (ḫašû)"
            if t == "liver":
                return f"Liver — {EXT_FEATURE.get(f, f)}" if f else "Liver — (unsorted)"
            if not t:
                return "(unspecified)"
            return f"{t.title()} — {f}" if f else t.title()
        EXT_ORDER = [
            "Liver — bāb ekallim", "Liver — martu", "Liver — naplastu",
            "Liver — padānu", "Liver — pû", "Liver — qerbu",
            "Liver — (unsorted)", "Lung (ḫašû)",
        ]

        # Astrology: classified from the `topic` field (free text) / EAE folder.
        def _astro_label(row):
            topic = row.get('topic')
            t = topic.lower() if isinstance(topic, str) else ""
            if any(k in t for k in ("solar", "šamaš", "shamash", "samas")):
                return "Solar (Šamaš — halo, setting, eclipse)"
            if any(k in t for k in ("stellar", "planet", "star", "eae55", "eae 55", "eae57", "eae 57", "ištar")):
                return "Stellar / planetary (EAE 55, 57)"
            if "lunar" in t and "eclipse" in t:
                return "Lunar — eclipse (antalû; EAE 20–22)"
            if "lunar" in t:
                return "Lunar — other (horns, halo, colour)"
            return "(unclassified)"
        ASTRO_ORDER = [
            "Lunar — eclipse (antalû; EAE 20–22)",
            "Lunar — other (horns, halo, colour)",
            "Solar (Šamaš — halo, setting, eclipse)",
            "Stellar / planetary (EAE 55, 57)",
        ]

        # Sakikkû: the canonical manuscripts name their tablet in `series`
        # ("Sakikkû (Diagnostic Handbook) Tablet 14"); everything without one is a
        # forerunner, and in this corpus those are all Old/Middle.
        DIAG_TABLETS = {3: "Sakikkû 3 — head & scalp",
                        4: "Sakikkû 4 — face, neck, trunk",
                        14: "Sakikkû 14 — Hand-of-the-god"}
        def _diag_label(row):
            s = _blob(row, 'series', 'recension', 'subpath')
            m = (re.search(r'sakikk[ûu][^0-9]*tablet\s*(\d+)', s)
                 or re.search(r'tablet\s*(\d+)', s))
            if m:
                n = int(m.group(1))
                return DIAG_TABLETS.get(n, f"Sakikkû {n}")
            return "Pre-canonical forerunners"
        DIAG_ORDER = ["Sakikkû 3 — head & scalp", "Sakikkû 4 — face, neck, trunk",
                      "Sakikkû 14 — Hand-of-the-god", "Pre-canonical forerunners"]

        # Šumma izbu: `canonical_tablet` gives the series tablet; 1–4 are the human
        # births, 5–24 the animal section (De Zorzi). Manuscripts without one are
        # the Old Babylonian forerunners and the peripheral copies.
        def _izbu_label(row):
            s = _blob(row, 'canonical_tablet', 'topic', 'source_note')
            if 'compendium' in s:
                return "Compendia (mixed sections)"
            m = re.search(r'tablet\s*(\d+)', s)
            if m:
                return ("Human births (Tablets 1–4)" if int(m.group(1)) <= 4
                        else "Animal births (Tablets 5–24)")
            if 'human' in s:
                return "Human births (Tablets 1–4)"
            if any(k in s for k in ('animal', 'equid', 'pig', 'sow')):
                return "Animal births (Tablets 5–24)"
            return "Forerunners & peripheral copies"
        IZBU_ORDER = ["Human births (Tablets 1–4)", "Animal births (Tablets 5–24)",
                      "Compendia (mixed sections)", "Forerunners & peripheral copies"]

        # Šumma Ālu: the subject is named in the publication line — the KAL 1
        # forerunners as "≈ ŠÀ 22-23 (snakes)", the canonical tablets by their
        # subject. Keyword order matters: the first match wins.
        TERR_SUBJECTS = [
            ("Snakes (Ālu 22–24)", ('snake',)),
            ("Lizards (Ālu 32–33)", ('lizard', 'eme.dir', 'eme.šid')),
            ("House & building", ('house omens', 'house (', 'building')),
            ("Sleep & bed", ('sleep', 'bed omens', 'bed (')),
            ("Human behaviour & sex", ('behaviour', 'behavior', 'sex ', 'sexual')),
            ("Birds", ('bird',)),
        ]
        def _terr_label(row):
            s = _blob(row, 'topic', 'publication', 'note', 'source_note', 'series')
            for label, keys in TERR_SUBJECTS:
                if any(k in s for k in keys):
                    return label
            return "Other subjects"
        TERR_ORDER = [lab for lab, _ in TERR_SUBJECTS] + ["Other subjects"]

        TOPIC_GENRES = {
            "Extispicy": (_ext_label, EXT_ORDER),
            "Astrological Omens": (_astro_label, ASTRO_ORDER),
            "Diagnostic Omens": (_diag_label, DIAG_ORDER),
            "Teratological Omens": (_izbu_label, IZBU_ORDER),
            "Terrestrial Omens": (_terr_label, TERR_ORDER),
        }
        avail_genres = [g for g in TOPIC_GENRES if not df[df['genre'] == g].empty]
        if not avail_genres:
            st.info("No texts of a discipline with sub-chapters in the current corpus.")
            EXT = None
        else:
            EXT = st.radio("Discipline", avail_genres, horizontal=True, key="topic_genre")
        _label_fn, TOPIC_ORDER = TOPIC_GENRES.get(EXT, (None, []))

        def _label_col(frame):
            """Label per text, then map onto the rows — the metadata is file-level,
            so one call per text instead of one per token."""
            if frame.empty or _label_fn is None:
                return []
            have = [f for f in _TOPIC_FIELDS if f in frame.columns]
            per_text = frame.groupby('filename')[have].first().to_dict('index')
            lab = {fn: _label_fn(rec) for fn, rec in per_text.items()}
            return frame['filename'].map(lab).tolist()

        ext_df = df[df['genre'] == EXT].copy() if EXT else df.iloc[0:0].copy()
        if ext_df.empty:
            if EXT:
                st.info(f"No {EXT} texts in the current corpus.")
        else:
            ext_df['topic_label'] = _label_col(ext_df)
            ext_uo = unique_omens_df[unique_omens_df['genre'] == EXT].copy()
            ext_uo['topic_label'] = _label_col(ext_uo)
            ext_lp = ext_df[ext_df['type'].isin(['logogram', 'phonetic'])]

            # Texts flagged `pooled_exclude` (orthographic outliers, e.g. a syllabic Babylonian
            # copy filed under a Neo cell) are dropped from the pooled LDI / counts but still
            # shown independently on the chart.
            def _excl(frame):
                if 'pooled_exclude' in frame.columns:
                    return frame['pooled_exclude'].fillna(False).astype(bool)
                return pd.Series(False, index=frame.index)
            ext_uo_pool = ext_uo[~_excl(ext_uo)]
            ext_df_pool = ext_df[~_excl(ext_df)]
            ext_lp_pool = ext_lp[~_excl(ext_lp)]
            ext_lp_excl = ext_lp[_excl(ext_lp)]

            periods_present = [p for p in PERIOD_ORDER if not ext_df[ext_df['period'] == p].empty]
            labels = list(ext_uo['topic_label'].dropna().unique())
            topics_present = sorted(
                labels,
                key=lambda l: (TOPIC_ORDER.index(l) if l in TOPIC_ORDER else len(TOPIC_ORDER), l))

            # Coverage table — omens (texts) per topic × period.
            cov_rows = []
            for tlab in topics_present:
                tu = ext_uo[ext_uo['topic_label'] == tlab]
                row = []
                for p in periods_present:
                    tp = tu[tu['period'] == p]
                    row.append(f"{len(tp)} ({tp['filename'].nunique()})" if len(tp) else "–")
                row.append(f"{len(tu)} ({tu['filename'].nunique()})")
                cov_rows.append(row)
            trow = []
            for p in periods_present:
                pp = ext_uo[ext_uo['period'] == p]
                trow.append(f"{len(pp)} ({pp['filename'].nunique()})" if len(pp) else "–")
            trow.append(f"{len(ext_uo)} ({ext_uo['filename'].nunique()})")
            cov_rows.append(trow)
            cov_df = pd.DataFrame(cov_rows, index=topics_present + ["Total"],
                                  columns=[_short(p) for p in periods_present] + ["Total"])
            cov_df.index.name = "Topic"
            st.caption("**omens (texts)** per topic × period.")
            render_table_with_copy(_section_table_style(cov_df.style), cov_df, "topic_cov")

            st.divider()

            # One chart per topic — each OMEN is a node, in chronological (period) order,
            # coloured by period (mirrors the Genre chart, but at omen level).
            for ti, tlab in enumerate(topics_present):
                tb = with_active(ext_lp_pool[ext_lp_pool['topic_label'] == tlab], mono)
                if tb.empty:
                    continue
                okeys = ['period', 'filename', 'omen_id']
                o_bin = tb.groupby(okeys)['_islog'].mean().rename('bin')
                o_agg = tb.groupby(okeys).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                o_agg['micro'] = o_agg['_nl'] / (o_agg['_nl'] + o_agg['_np']).where((o_agg['_nl'] + o_agg['_np']) > 0)
                ostats = pd.concat([o_bin, o_agg[['macro', 'micro']]], axis=1).reset_index()
                ostats[['bin', 'macro', 'micro']] = ostats[['bin', 'macro', 'micro']].fillna(0.0)
                ostats['period'] = pd.Categorical(ostats['period'], categories=PERIOD_ORDER, ordered=True)
                ostats = ostats.sort_values(['period', 'filename', 'omen_id'])
                if ostats.empty:
                    continue
                ostats['seq_index'] = range(len(ostats))

                # Three LDI measures for this topic, by period — shown before the chart.
                st.markdown(f"#### {tlab}")
                _TPRES = FRAMES[True]['df']
                _tsl = []
                for p in PERIOD_ORDER + ["Total"]:
                    tuo = ext_uo_pool[ext_uo_pool['topic_label'] == tlab]
                    tuo = tuo if p == "Total" else tuo[tuo['period'] == p]
                    if tuo.empty:
                        continue
                    tdd = ext_df_pool[ext_df_pool['topic_label'] == tlab]
                    tdd = tdd if p == "Total" else tdd[tdd['period'] == p]
                    tpr = _TPRES[_TPRES['filename'].isin(tdd['filename'].unique())]
                    tpr = tpr if p == "Total" else tpr[tpr['period'] == p]
                    _tsl.append((period_disp(p), tdd, tpr, tuo))
                # Excluded texts get their own independent row (own LDI; not in the pooled rows).
                ex_tu_all = ext_uo[ext_uo['topic_label'] == tlab]
                ex_tu_all = ex_tu_all[_excl(ex_tu_all)]
                for fn in sorted(ex_tu_all['filename'].unique()):
                    ftu = ex_tu_all[ex_tu_all['filename'] == fn]
                    ftd = ext_df[(ext_df['topic_label'] == tlab) & (ext_df['filename'] == fn)]
                    _tsl.append((f"{fn} (excl.)", ftd,
                                 _TPRES[_TPRES['filename'] == fn], ftu))
                ltdf = standard_table(_tsl, "Period")
                if ltdf is not None:
                    lsty = report_style(ltdf)
                    render_table_with_copy(lsty, ltdf, f"topic_ldi_{ti}")

                # This topic's own switch, under its title and over its charts.
                st.markdown(f'<div class="charttitle">{tlab} — LDI per omen '
                            f'({len(ostats)} omens)</div>', unsafe_allow_html=True)

                def _chart(metric, ostats=ostats, tlab=tlab, ti=ti, tb=tb):
                    fig = go.Figure()
                    # One spline per period segment (its own colour), bridged so there are no gaps.
                    periods_here = [p for p in PERIOD_ORDER if (ostats['period'] == p).any()]
                    for i, period in enumerate(periods_here):
                        sub = ostats[ostats['period'] == period]
                        xs, ys = sub['seq_index'].tolist(), sub[metric].tolist()
                        lx, ly = list(xs), list(ys)
                        if i + 1 < len(periods_here):
                            nxt = ostats[ostats['period'] == periods_here[i + 1]].iloc[0]
                            lx.append(nxt['seq_index']); ly.append(nxt[metric])
                        fig.add_trace(go.Scatter(
                            x=lx, y=ly, mode='lines',
                            line=dict(width=2, shape='spline', smoothing=1.0, color=color_map.get(period, '#444')),
                            hoverinfo='skip', showlegend=False))
                        fig.add_trace(go.Scatter(
                            x=xs, y=ys, mode='markers',
                            marker=dict(size=9, color=color_map.get(period, '#444'),
                                        line=dict(width=1, color='white')),
                            name=period_disp(period),
                            customdata=sub[['omen_id', 'filename', 'bin', 'macro', 'micro']].to_numpy(),
                            hovertemplate="<b>omen %{customdata[0]}</b> · %{customdata[1]}<br>" + period_disp(period) + "<br>"
                                          + metric + " = %{y:.3f}<br>"
                                          "bin %{customdata[2]:.2f} · macro %{customdata[3]:.2f} · micro %{customdata[4]:.2f}"
                                          "<extra></extra>"))

                    # Excluded texts (pooled_exclude) — plotted independently as grey ◆ to the right,
                    # kept out of the pooled line, the "whole" labels and the table above.
                    ex_tb = with_active(ext_lp_excl[ext_lp_excl['topic_label'] == tlab], mono)
                    if not ex_tb.empty:
                        ex_bin = ex_tb.groupby(okeys)['_islog'].mean().rename('bin')
                        ex_agg = ex_tb.groupby(okeys).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                        ex_agg['micro'] = ex_agg['_nl'] / (ex_agg['_nl'] + ex_agg['_np']).where((ex_agg['_nl'] + ex_agg['_np']) > 0)
                        exstats = pd.concat([ex_bin, ex_agg[['macro', 'micro']]], axis=1).reset_index()
                        exstats[['bin', 'macro', 'micro']] = exstats[['bin', 'macro', 'micro']].fillna(0.0)
                        exstats = exstats.sort_values(['filename', 'omen_id'])
                        exstats['seq_index'] = range(len(ostats), len(ostats) + len(exstats))
                        fig.add_trace(go.Scatter(
                            x=exstats['seq_index'], y=exstats[metric], mode='markers',
                            marker=dict(size=9, color='#9e9e9e', symbol='diamond',
                                        line=dict(width=1, color='white')),
                            name='excluded (independent)',
                            customdata=exstats[['omen_id', 'filename', 'bin', 'macro', 'micro']].to_numpy(),
                            hovertemplate="<b>omen %{customdata[0]}</b> · %{customdata[1]} <i>(excluded)</i><br>"
                                          + metric + " = %{y:.3f}<br>"
                                          "bin %{customdata[2]:.2f} · macro %{customdata[3]:.2f} · micro %{customdata[4]:.2f}"
                                          "<extra></extra>"))

                    # Per-period pooled "whole" LDI + highest/lowest omen dot, labelled at the top.
                    midx = {"bin": 0, "macro": 1, "micro": 2}[metric]
                    for period in periods_here:
                        sub = ostats[ostats['period'] == period]
                        xs, ys = sub['seq_index'], sub[metric]
                        x0, x1 = float(xs.min()), float(xs.max())
                        col = color_map.get(period, '#444')
                        whole = trio(ext_df_pool[(ext_df_pool['topic_label'] == tlab) & (ext_df_pool['period'] == period)], mono, nopart)[midx]
                        fig.add_annotation(
                            x=(x0 + x1) / 2, y=1.02, xref='x', yref='y',
                            text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                            showarrow=False, yanchor='bottom', align='center', font=dict(size=10, color=col))

                    fig.update_layout(
                        margin=dict(t=14),   # no chart title to make room for
                        template="simple_white", font_family="Arial",
                        xaxis_title="Omens (chronological)", yaxis_title=f"LDI — {metric}",
                        yaxis=dict(range=[-0.05, 1.30], tickmode='array',
                                   tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
                        xaxis=dict(showticklabels=False), height=420,
                        legend_title_text="Period", hovermode="closest")
                    st.plotly_chart(fig, use_container_width=True, key=f"topic_omen_chart_{ti}")
                    if not ex_tb.empty:
                        exnames = ", ".join(sorted(ex_tb['filename'].unique()))
                        st.caption(f"Grey ◆ = excluded from the pooled LDI and shown independently: "
                                   f"**{exnames}** (see the text's frontmatter note for why).")

                    # Text-level view — one node per tablet (like the Genre chart). Only for topics
                    # that span ≥2 periods (e.g. extispicy martu, naplastu, padānu, lung).
                    t_bin = tb.groupby(['period', 'filename'])['_islog'].mean().rename('bin')
                    t_agg = tb.groupby(['period', 'filename']).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                    t_agg['micro'] = t_agg['_nl'] / (t_agg['_nl'] + t_agg['_np']).where((t_agg['_nl'] + t_agg['_np']) > 0)
                    t_n = ext_uo_pool[ext_uo_pool['topic_label'] == tlab].groupby(['period', 'filename']).size().rename('n')
                    tstats = pd.concat([t_bin, t_agg[['macro', 'micro']], t_n], axis=1).reset_index()
                    tstats[['bin', 'macro', 'micro']] = tstats[['bin', 'macro', 'micro']].fillna(0.0)
                    tstats['period'] = pd.Categorical(tstats['period'], categories=PERIOD_ORDER, ordered=True)
                    tstats = tstats.sort_values(['period', 'filename'])
                    tperiods = [p for p in PERIOD_ORDER if (tstats['period'] == p).any()]
                    if len(tperiods) >= 2:
                        tstats['seq_index'] = range(len(tstats))
                        figt = go.Figure()
                        for i, period in enumerate(tperiods):
                            sub = tstats[tstats['period'] == period]
                            xs, ys = sub['seq_index'].tolist(), sub[metric].tolist()
                            lx, ly = list(xs), list(ys)
                            if i + 1 < len(tperiods):
                                nxt = tstats[tstats['period'] == tperiods[i + 1]].iloc[0]
                                lx.append(nxt['seq_index']); ly.append(nxt[metric])
                            figt.add_trace(go.Scatter(
                                x=lx, y=ly, mode='lines',
                                line=dict(width=2.5, shape='spline', smoothing=1.0, color=color_map.get(period, '#444')),
                                hoverinfo='skip', showlegend=False))
                            figt.add_trace(go.Scatter(
                                x=xs, y=ys, mode='markers',
                                marker=dict(size=12, color=color_map.get(period, '#444'),
                                            line=dict(width=1, color='white')),
                                name=period_disp(period),
                                customdata=sub[['filename', 'bin', 'macro', 'micro', 'n']].to_numpy(),
                                hovertemplate="<b>%{customdata[0]}</b><br>" + period_disp(period) + "<br>"
                                              + metric + " = %{y:.3f}<br>"
                                              "bin %{customdata[1]:.2f} · macro %{customdata[2]:.2f} · micro %{customdata[3]:.2f}"
                                              "<br>omens = %{customdata[4]}<extra></extra>"))
                        # Per-period highest / whole / lowest labelled at the top, mirroring the
                        # per-omen chart. Highest/lowest are the extreme text (tablet) LDIs;
                        # "whole" is the pooled LDI for that period.
                        for period in tperiods:
                            sub = tstats[tstats['period'] == period]
                            xs, ys = sub['seq_index'], sub[metric]
                            x0, x1 = float(xs.min()), float(xs.max())
                            col = color_map.get(period, '#444')
                            whole = trio(ext_df_pool[(ext_df_pool['topic_label'] == tlab) & (ext_df_pool['period'] == period)], mono, nopart)[midx]
                            figt.add_annotation(
                                x=(x0 + x1) / 2, y=1.02, xref='x', yref='y',
                                text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                                showarrow=False, yanchor='bottom', align='center', font=dict(size=10, color=col))
                        figt.update_layout(
                            title=f"{tlab} — {metric} LDI per text ({len(tstats)} tablets)",
                            template="simple_white", font_family="Arial",
                            xaxis_title="Texts (chronological)", yaxis_title=f"LDI — {metric}",
                            yaxis=dict(range=[-0.05, 1.30], tickmode='array',
                                       tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
                            xaxis=dict(showticklabels=False), height=380,
                            legend_title_text="Period", hovermode="closest")
                        st.plotly_chart(figt, use_container_width=True,
                                        key=f"topic_text_chart_{ti}")
                metric_block(f"topics_{ti}", _chart)

    # --- LDI ▸ Genre ---
    if page == "LDI" and ldi_view == "Discipline":
        st.caption("Each marker is a whole text (its pooled LDI), not a single omen — so the "
                   "curve traces tablet-by-tablet, coloured by period. **Click a node to open "
                   "that tablet in the Text view.**")

        def _f(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        if not bframe.empty:
            for gi, genre in enumerate(sorted(unique_omens_df['genre'].dropna().unique())):
                g_uo = unique_omens_df[unique_omens_df['genre'] == genre]
                st.markdown(f"#### {genre}: {g_uo['filename'].nunique()} texts — {len(g_uo)} omens")
                mono, pres, nopart = False, False, False   # canonical: the report table prices the variants
                _F = pick(pres)
                df, unique_omens_df = _F['df'], _F['uo']
                bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

                # LDI by Period for this genre — texts · omens · bin · macro · micro.
                # Canonical convention; Total pools across periods.
                _GFULL, _GPRES = FRAMES[False]['df'], FRAMES[True]['df']
                _gf = _GFULL[_GFULL['genre'] == genre]
                _gp = _GPRES[_GPRES['genre'] == genre]
                _gsl = []
                for period in PERIOD_ORDER + ["Total"]:
                    puo = g_uo if period == "Total" else g_uo[g_uo['period'] == period]
                    if puo.empty:
                        continue
                    _gsl.append((period_disp(period),
                                 _gf if period == "Total" else _gf[_gf['period'] == period],
                                 _gp if period == "Total" else _gp[_gp['period'] == period],
                                 puo))
                gtdf = standard_table(_gsl, "Period")
                if gtdf is not None:
                    gtsty = report_style(gtdf)
                    render_table_with_copy(gtsty, gtdf, f"genre_period_{gi}")

                st.markdown(f'<div class="charttitle">{genre} — LDI per text '
                            f'(Old → Neo)</div>', unsafe_allow_html=True)

                # Per-TEXT aggregate (one node per file) for this genre + monogram choice.
                bf = with_active(bframe[bframe['genre'] == genre], mono)
                gf = with_active(gframe[gframe['genre'] == genre], mono)
                fkeys = ['period', 'filename']
                f_bin = bf.groupby(fkeys)['_islog'].mean().rename('bin')
                f_agg = gf.groupby(fkeys).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                f_agg['micro'] = f_agg['_nl'] / (f_agg['_nl'] + f_agg['_np']).where((f_agg['_nl'] + f_agg['_np']) > 0)
                f_n = g_uo.groupby(fkeys).size().rename('n')
                gstats = pd.concat([f_bin, f_agg[['macro', 'micro']], f_n], axis=1).reset_index()
                gstats[['bin', 'macro', 'micro']] = gstats[['bin', 'macro', 'micro']].fillna(0.0)
                gstats['period'] = pd.Categorical(gstats['period'], categories=PERIOD_ORDER, ordered=True)
                gstats = gstats.sort_values(['period', 'filename'])
                if gstats.empty:
                    continue
                gstats['seq_index'] = range(len(gstats))

                def _chart(metric, gstats=gstats, genre=genre):
                    fig_genre = go.Figure()
                    # One connected spline, but each period's segment takes that period's colour.
                    # A segment is bridged into the first point of the next period so there are no gaps.
                    periods_here = [p for p in PERIOD_ORDER if (gstats['period'] == p).any()]
                    for i, period in enumerate(periods_here):
                        sub = gstats[gstats['period'] == period]
                        xs, ys = sub['seq_index'].tolist(), sub[metric].tolist()
                        lx, ly = list(xs), list(ys)
                        if i + 1 < len(periods_here):              # bridge to next period
                            nxt = gstats[gstats['period'] == periods_here[i + 1]].iloc[0]
                            lx.append(nxt['seq_index']); ly.append(nxt[metric])
                        fig_genre.add_trace(go.Scatter(
                            x=lx, y=ly, mode='lines',
                            line=dict(width=2.5, shape='spline', smoothing=1.0, color=color_map.get(period, '#444')),
                            hoverinfo='skip', showlegend=False
                        ))
                        fig_genre.add_trace(go.Scatter(
                            x=xs, y=ys, mode='markers',
                            marker=dict(size=12, color=color_map.get(period, '#444'),
                                        line=dict(width=1, color='white')),
                            name=period_disp(period),
                            customdata=sub[['filename', 'bin', 'macro', 'micro', 'n']].to_numpy(),
                            hovertemplate="<b>%{customdata[0]}</b><br>" + period_disp(period) + "<br>"
                                          + metric + " = %{y:.3f}<br>"
                                          "bin %{customdata[1]:.2f} · macro %{customdata[2]:.2f} · micro %{customdata[3]:.2f}"
                                          "<br>omens = %{customdata[4]}"
                                          "<br><i>↪ click to open in Text view</i><extra></extra>"
                        ))

                    # Per-period region: highest / whole / lowest LDI labelled at the top.
                    # "whole" is the pooled LDI for that period (not the mean of the dots).
                    midx = {"bin": 0, "macro": 1, "micro": 2}[metric]
                    for period in periods_here:
                        sub = gstats[gstats['period'] == period]
                        xs, ys = sub['seq_index'], sub[metric]
                        x0, x1 = float(xs.min()), float(xs.max())
                        col = color_map.get(period, '#444')
                        whole = trio(df[(df['genre'] == genre) & (df['period'] == period)], mono, nopart)[midx]
                        fig_genre.add_annotation(
                            x=(x0 + x1) / 2, y=1.02, xref='x', yref='y',
                            text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                            showarrow=False, yanchor='bottom', align='center',
                            font=dict(size=11, color=col),
                        )

                    fig_genre.update_layout(
                        margin=dict(t=14),   # no chart title to make room for
                        template="simple_white", font_family="Arial",
                        xaxis_title="Texts (chronological)", yaxis_title=f"LDI — {metric}",
                        yaxis=dict(range=[-0.05, 1.30], tickmode='array',
                                   tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
                        xaxis=dict(showticklabels=False), height=480,
                        legend_title_text="Period", hovermode="closest"
                    )
                    event = st.plotly_chart(fig_genre, use_container_width=True,
                                            key=f"chart_{genre}", on_select="rerun")

                    # Clicking a node jumps to the Text view with that text open. The
                    # filename rides in customdata[0]; guard against the selection
                    # re-firing when the user navigates back to this chart.
                    clicked = None
                    try:
                        for pt in event["selection"]["points"]:
                            cd = pt.get("customdata")
                            if cd:
                                clicked = cd[0]
                                break
                    except (KeyError, TypeError):
                        clicked = None

                    if clicked and st.session_state.get(f"lastsel_{genre}") != clicked:
                        st.session_state[f"lastsel_{genre}"] = clicked
                        st.session_state['goto_nav'] = "LDI"
                        st.session_state['goto_sub'] = "Text"
                        st.session_state['goto_file'] = clicked
                        st.rerun()
                metric_block(f"genre_{genre}", _chart)

    # --- LDI ▸ Text ---
    if page == "LDI" and ldi_view == "Text":
        def _cval(row, k):
            v = row.get(k)
            return v if isinstance(v, str) and v.strip() else "-"

        def _toggle_period(p, ns='tree'):
            # a set, not a single value: opening one folder must not close
            # the others, the way a file explorer behaves
            _s = set(st.session_state.get(ns + '_open_p') or ())
            st.session_state[ns + '_open_p'] = _s ^ {p}

        def _toggle_disc(p, g, ns='tree'):
            _s = set(st.session_state.get(ns + '_open_g') or ())
            st.session_state[ns + '_open_g'] = _s ^ {(p, g)}

        def _toggle_sub(key, ns='tree'):
            _s = set(st.session_state.get(ns + '_open_s') or ())
            st.session_state[ns + '_open_s'] = _s ^ {key}

        @st.fragment
        def _tablet_tree(_df, _cur_file, _n_all, _fkey='text_file', _ns='tree'):
            """Data ▸ period ▸ discipline ▸ tablet.

            A fragment, so opening or closing a folder reruns this block alone
            and leaves the report table and chart beside it untouched. The
            folder toggles run as on_click callbacks — state is updated before
            the rerun renders, so no explicit st.rerun is needed and the labels
            are never a click out of date. Choosing a tablet is the one action
            that changes the panel, so it asks for a full rerun."""
            # Open state belongs to the tree alone — never derived from the
            # open tablet, or its folders could not be closed. Sets, so any
            # number of branches can stay open at once.
            _op = set(st.session_state.get(_ns + '_open_p') or ())
            _og = set(st.session_state.get(_ns + '_open_g') or ())

            _os = set(st.session_state.get(_ns + '_open_s') or ())

            def _branch(_frame, _prefix, _depth):
                """Folders below a discipline, then the tablets that sit there.

                extispicy has liver/lung and, under liver, martu, padanu and
                the rest; astrology has EAE20, EAE55 … A tablet appears at
                whatever depth its file does."""
                _sp = (_frame.groupby('filename')['subpath'].first()
                       if 'subpath' in _frame.columns
                       else pd.Series(dtype=object))
                _folders, _here = {}, []
                for _f, _s in _sp.items():
                    _parts = [x for x in str(_s or '').split('/') if x]
                    if len(_parts) > _depth:
                        _folders.setdefault(_parts[_depth], []).append(_f)
                    else:
                        _here.append(_f)
                _pad = 0.09 * (_depth + 2)
                for _name in sorted(_folders):
                    _key = _prefix + (_name,)
                    _i, _r = st.columns([_pad, 1 - _pad])
                    _r.button(f"{'▾' if _key in _os else '▸'} {_name}"
                              f"  ({len(_folders[_name])})",
                              key=_ns + "_s_" + "|".join(_key),
                              use_container_width=True,
                              on_click=_toggle_sub, args=(_key, _ns))
                    if _key in _os:
                        _branch(_frame[_frame['filename'].isin(_folders[_name])],
                                _key, _depth + 1)
                for _fn in sorted(_here):
                    _i, _r = st.columns([_pad, 1 - _pad])
                    if _r.button(_fn.rsplit('.txt', 1)[0],
                                 key=_ns + "_f_" + "|".join(_prefix) + "|" + _fn,
                                 use_container_width=True,
                                 type="primary" if _fn == _cur_file else "secondary"):
                        st.session_state[_fkey] = _fn
                        st.session_state[_ns + '_open_p'] = _op | {_prefix[0]}
                        st.session_state[_ns + '_open_g'] = _og | {_prefix[:2]}
                        st.session_state[_ns + '_open_s'] = _os | {
                            _prefix[:_i] for _i in range(3, len(_prefix) + 1)}
                        st.rerun()          # whole app: the open text changed

            st.markdown(f"**Data** · {_n_all} texts")
            for _p in PERIOD_ORDER:
                _pdf = _df[_df['period'] == _p]
                if _pdf.empty:
                    continue
                st.button(f"{'▾' if _p in _op else '▸'} {period_disp(_p)}"
                          f"  ({_pdf['filename'].nunique()})",
                          key=f"{_ns}_p_{_p}", use_container_width=True,
                          on_click=_toggle_period, args=(_p, _ns))
                if _p not in _op:
                    continue
                for _g in sorted(_pdf['genre'].dropna().unique()):
                    _gdf = _pdf[_pdf['genre'] == _g]
                    _i1, _r1 = st.columns([0.09, 0.91])
                    _r1.button(f"{'▾' if (_p, _g) in _og else '▸'} {_g}"
                               f"  ({_gdf['filename'].nunique()})",
                               key=f"{_ns}_g_{_p}_{_g}", use_container_width=True,
                               on_click=_toggle_disc, args=(_p, _g, _ns))
                    if (_p, _g) not in _og:
                        continue
                    _branch(_gdf, (_p, _g), 0)


        # The three sets, as tabs over the tree. "Supplementary (KAL 5)" is the
        # stored value but too long for the column, so the tab reads "KAL 5".
        _SET_TABS = {"Corpus": "Corpus", "Comparanda": "Comparanda",
                     "KAL 5": "Supplementary (KAL 5)"}
        # Read the picker itself, not the value it wrote last run: the widget is
        # rendered further down (inside the tree column), so a stored value would
        # always be one interaction behind.
        text_set = _SET_TABS.get(st.session_state.get('text_set_pick') or "Corpus", "Corpus")
        if st.session_state.get('goto_file'):
            # A Genre-node click jumps straight to a corpus text.
            st.session_state['text_set_pick'] = "Corpus"
            text_set = "Corpus"

        def _set_tabs():
            """Render the picker; the branch below reads its value on the next run."""
            # `default` only on the first run: passing it once the key exists in
            # session state makes Streamlit warn. Without it the control renders
            # with no segment marked active until the first click.
            _kw = {} if 'text_set_pick' in st.session_state else {'default': "Corpus"}
            _pick = st.segmented_control(
                "Text set", list(_SET_TABS), key="text_set_pick",
                label_visibility="collapsed", **_kw) or "Corpus"
            st.session_state['text_set'] = _SET_TABS[_pick]

        if text_set == "Corpus":
            # Honour a "jump to this text" request from a Genre-node click: pre-set the
            # three selectors (consistently) before the widgets are instantiated.
            goto = st.session_state.pop('goto_file', None)
            if goto:
                grow = df[df['filename'] == goto]
                if not grow.empty:
                    st.session_state['text_period'] = grow.iloc[0]['period']
                    st.session_state['text_genre'] = grow.iloc[0]['genre']
                    st.session_state['text_file'] = goto
                    st.session_state['tree_open_p'] = (
                        set(st.session_state.get('tree_open_p') or ())
                        | {grow.iloc[0]['period']})
                    st.session_state['tree_open_g'] = (
                        set(st.session_state.get('tree_open_g') or ())
                        | {(grow.iloc[0]['period'], grow.iloc[0]['genre'])})

            # Tablet explorer, left of the text: discipline ▸ period ▸ tablet.
            # Only the open discipline lists its texts, so the widget count stays
            # with the branch being read rather than the whole corpus.
            _all_files = sorted(df['filename'].unique())
            # Nothing is opened on the reader's behalf: an arbitrary first tablet
            # is not a choice, and picking one would also force its folder open.
            if st.session_state.get('text_file') not in _all_files:
                st.session_state['text_file'] = None
            _cur = st.session_state.get('text_file')
            _crow = df[df['filename'] == _cur] if _cur else df.iloc[0:0]
            if not _crow.empty:      # keep period/discipline consistent with the open text
                st.session_state['text_period'] = _crow.iloc[0]['period']
                st.session_state['text_genre'] = _crow.iloc[0]['genre']

            _tree, _main = st.columns([2.6, 7.4])
            with _tree:
                _set_tabs()
                with st.container(key="tabtree"):
                    _tablet_tree(df, _cur, len(_all_files))

            selected_period = st.session_state.get('text_period')
            selected_genre = st.session_state.get('text_genre')
            selected_file = st.session_state.get('text_file')
            period_df = df[df['period'] == selected_period]
            genre_df = period_df[period_df['genre'] == selected_genre]

            with _main:
                filtered_df = (genre_df[genre_df['filename'] == selected_file]
                               if selected_file else genre_df.iloc[0:0])
                if selected_file is None:
                    st.info("Select a tablet in the tree on the left to see its "
                            "transliteration, its report and its per-omen curve.")
                if not filtered_df.empty:
                    first_row = filtered_df.iloc[0]
                    _h1, _h2 = st.columns([1, 3], vertical_alignment="center")
                    _h1.subheader(selected_file.rsplit(".txt", 1)[0])   # the text/tablet number
                    _h2.markdown(LEGEND_HTML, unsafe_allow_html=True)
                    # the tablet's own period (Middle Assyrian, Late Babylonian …),
                    # not the Old/Middle/Neo bucket the charts group it into
                    meta = [f"**Period:** {first_row.get('period_raw') or first_row.get('period', '-')}",
                            f"**Discipline:** {first_row.get('genre', '-')}",
                            f"**Provenance:** {first_row.get('provenance', '-')}",
                            f"**Counting:** {counting_label(first_row.get('counting'))}"]
                    meta += biblio_and_ebl_lines(first_row)
                    st.markdown("  \n".join(meta), unsafe_allow_html=True)

                    if st.button("✏️ Edit text", key="edit_btn_text"):
                        edit_text_dialog(selected_file)

                    _pf = FRAMES[True]['df']
                    filtered_pres = _pf[_pf['filename'] == selected_file]
                    render_text_block(filtered_df, filtered_pres, selected_period, selected_file, "text")

        else:
            # Held-out sets: comparanda (data/_comparanda) or the KAL 5 supplement (data/kal5).
            if text_set == "Comparanda":
                pool, pkey = FRAMES[False]['comp'], 'comp'
                _cap = ("Comparison texts kept **out** of the main corpus (non-Akkadian parallels "
                        "or otherwise excluded). Their LDI reflects the graphic convention, not an "
                        "Akkadian logogram-vs-syllabic split — read the per-text note with care.")
                empty_msg = "No comparanda found in data/_comparanda."
            else:
                pool, pkey = FRAMES[False]['supp'], 'supp'
                _cap = ("Supplementary witnesses held **out** of the main LDI counts — the further "
                        "KAL 5 extispicy tablets (Heeßel 2012), auto-extracted from the printed "
                        "edition and glyph-remapped, not hand-collated.")
                empty_msg = "No supplementary texts found in data/kal5."

            _htree, _hmain = st.columns([2.6, 7.4])
            with _htree:
                _set_tabs()          # before the tree, and before any empty message
            with _hmain:
                st.caption(_cap)

            if pool.empty:
                with _hmain:
                    st.info(empty_msg)
            else:
                _hfiles = sorted(pool['filename'].unique())
                _hkey = f"heldout_{pkey}"
                if st.session_state.get(_hkey) not in _hfiles:
                    st.session_state[_hkey] = None
                sel = st.session_state.get(_hkey)
                with _htree:
                    with st.container(key=f"tabtree_{pkey}"):
                        _tablet_tree(pool, sel, len(_hfiles), _hkey, f"tree{pkey}")
                with _hmain:
                    if sel is None:
                        st.info("Select a text in the tree on the left.")
                hdf = pool[pool['filename'] == sel] if sel else pool.iloc[0:0]
                with _hmain:
                    if not hdf.empty:
                        hrow = hdf.iloc[0]
                        _h1, _h2 = st.columns([1, 3], vertical_alignment="center")
                        _h1.subheader(sel.rsplit(".txt", 1)[0])
                        _h2.markdown(LEGEND_HTML, unsafe_allow_html=True)
                        meta = [f"**Period:** {_cval(hrow, 'period_raw') or _cval(hrow, 'period')}",
                                f"**Discipline:** {_cval(hrow, 'genre')}",
                                f"**Language:** {_cval(hrow, 'language')}",
                                f"**Provenance:** {_cval(hrow, 'provenance')}",
                                f"**Counting:** {counting_label(_cval(hrow, 'counting'))}"]
                        meta += biblio_and_ebl_lines(hrow)
                        note = _cval(hrow, 'note')
                        if note != "-":
                            meta.append(f"**Note:** {note}")
                        st.markdown("  \n".join(meta), unsafe_allow_html=True)

                        if st.button("✏️ Edit text", key=f"edit_btn_{pkey}"):
                            edit_text_dialog(sel)

                        _cp = FRAMES[True][pkey]
                        hdf_pres = _cp[_cp['filename'] == sel] if not _cp.empty else hdf
                        render_text_block(hdf, hdf_pres, hrow.get('period'), sel, pkey)

else:
    st.info("Upload a text file or load sample data to begin.")
