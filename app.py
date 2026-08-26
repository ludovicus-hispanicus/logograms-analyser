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
# Anchor bundled files to this file, not the working directory: the frozen and
# stlite builds do not necessarily run from the app folder, and a CWD-relative
# path there silently fails the os.path.exists guards below.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_LOGO_DIR = os.path.join(_APP_DIR, "assets", "logo")

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

        /* Editor: buffer tabs, and the project tree. */
        .st-key-ed_tab_label { margin-bottom: 0 !important; }
        /* the buffer sits as close under its tabs as the rail's first button sits
           under "Sources": the gap is the vertical block's, not the tab strip's */
        [data-testid="stVerticalBlock"]:has(> .st-key-ed_tab_label) {
            gap: 0.5rem !important;
        }
        /* Editor toolbar: a narrow stack of icon buttons beside the buffer. */
        [class*="st-key-ed_x_"] button,
        [class*="st-key-ed_save_"] button,
        [class*="st-key-ed_run_"] button {
            padding: 0.2rem 0 !important;
            min-height: 0 !important;
        }
        [class*="st-key-ed_x_"] button p,
        [class*="st-key-ed_save_"] button p,
        [class*="st-key-ed_run_"] button p {
            font-size: 1.05rem !important;
            margin: 0 !important;
        }
        [class*="st-key-ed_x_"] button {
            border: none !important; background: transparent !important;
            color: #9c9791 !important;
        }
        [class*="st-key-ed_x_"] button:hover { color: #C0271F !important; }
        .edtoolsep {
            border-top: 1px solid #E0DBD2;
            margin: 0.45rem 0.15rem 0.55rem;
        }
        /* The editor pane: buffer and toolbar inside one frame. */
        .st-key-edpane {
            background: #fff;
            align-items: stretch !important;
            flex-wrap: nowrap !important;   /* the toolbar stays beside the buffer */
            gap: 0.1rem !important;        /* close to the buffer, not against it */
        }
        .st-key-edpane > div > [data-testid="stElementContainer"] { margin: 0 !important; }
        /* Streamlit wraps each child of a horizontal container in a layout wrapper
           and gives both the same flex, so the toolbar was claiming half the pane.
           The wrapper is what must be pinned, not the block inside it. */
        .st-key-edpane > [data-testid="stLayoutWrapper"]:has(> .st-key-edtool) {
            flex: 0 0 40px !important;
            width: 40px !important;
            min-width: 40px !important;
        }
        .st-key-edpane > [data-testid="stLayoutWrapper"]:not(:has(> .st-key-edtool)) {
            flex: 1 1 auto !important;
            min-width: 0 !important;
        }
        .st-key-edpane iframe { width: 100% !important; }
        /* the toolbar is exactly one icon wide */
        .st-key-edtool {
            flex: 0 0 40px !important;
            width: 40px !important;
            min-width: 40px !important;
            gap: 0.15rem !important;
        }
        .st-key-edtool button {
            width: 40px !important;
            min-width: 0 !important;
            padding: 0.18rem 0 !important;
        }
        .st-key-edtool button p { font-size: 1rem !important; }
        /* the source rail: smaller type, so the narrower column still fits */
        [class*="st-key-ed_new"] button p, [class*="st-key-ed_open"] button p,
        [class*="st-key-ed_upload"] button p, [class*="st-key-ed_paste"] button p,
        [class*="st-key-ed_ebl"] button p, [class*="st-key-ed_bulk"] button p {
            font-size: 0.84rem !important;
        }
        .st-key-ed_tab_label [data-baseweb="button-group"] { gap: 0.2rem; }
        .st-key-ed_tab_label button {
            background: #fff !important;
            border: 1px solid #e2e2e2 !important;
            border-radius: 7px 7px 0 0 !important;
            box-shadow: none !important;
            padding: 0.22rem 0.7rem !important;
            color: #5a5a5a !important;
            font-weight: 600 !important;
        }
        .st-key-ed_tab_label button p { font-size: 0.82rem !important; margin: 0 !important; }
        .st-key-ed_tab_label button[data-testid="stBaseButton-segmented_controlActive"],
        .st-key-ed_tab_label button[kind="segmented_controlActive"] {
            background: #e0e0e0 !important; color: #1a1a1a !important;
            border-color: #c4c4c4 !important;
            box-shadow: inset 0 3px 0 0 #D32F2F !important;
        }
        .railnote { font-size: 0.8rem; color: #6B655D; margin: 0 0 0.2rem 0.1rem; }
        .projnode {
            font-weight: 600; color: #262626; font-size: 0.95rem;
            margin: 0.7rem 0 0.15rem;
        }
        .projnode.projsub {
            font-weight: 500; color: #6B655D; font-size: 0.88rem;
            margin: 0.2rem 0 0.1rem 1rem;
        }
        .projfile {
            display: flex; justify-content: space-between; align-items: baseline;
            gap: 1rem; padding: 0.16rem 0 0.16rem 2rem; max-width: 46rem;
            border-bottom: 1px solid #F2EFE9;
        }
        .projname { font-size: 0.92rem; color: #1f1f1f; }
        .projmeta { font-size: 0.78rem; color: #6B655D; font-variant-numeric: tabular-nums; }
        .proj-unsaved { color: #C0271F; font-weight: 600; }
        .proj-new { color: #8a6d1f; font-weight: 600; }
        .proj-saved { color: #3f7a4a; font-weight: 600; }

        /* Editor rail: a column of source buttons and the open buffers. */
        .railhead {
            font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
            text-transform: uppercase; color: #6B655D;
            margin: 1rem 0 0.3rem 0.1rem;
        }
        [class*="st-key-ed_sel_"] button {
            text-align: left !important;
            justify-content: flex-start !important;
            font-size: 0.86rem !important;
        }
        [class*="st-key-ed_close_"] button {
            border: none !important; background: transparent !important;
            color: #9c9791 !important; padding: 0 !important;
        }

        /* Bibliography: a reference list, not a stack of cards. Rows sit tight,
           the entry hangs, and only a hairline separates one from the next. */
        .bibtable {
            width: 100%;
            border-collapse: collapse;
            font-size: 1rem;
            border: none;
        }
        .bibtable th, .bibtable td, .bibtable tr { border: none !important; }
        .bibtable th {
            text-align: left;
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #6B655D;
            padding: 0 0.8rem 0.4rem 0;
        }
        .bibtable td {
            vertical-align: top;
            padding: 0.32rem 0.8rem 0.32rem 0;
            line-height: 1.4;
        }
        .bibtable tr.bibhit td { background: #FBF1F0; }
        .bibkey {
            font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
            font-size: 0.84rem;
            color: #6B655D;
            white-space: nowrap;
        }
        .bibentry { padding-left: 1.1rem !important; text-indent: -1.1rem; }
        .bibnote, .bibcited { color: #6B655D; font-size: 0.92rem; }
        .bibcount {
            font-size: 0.86rem;
            color: #6B655D;
            margin: 0.1rem 0 0.4rem;
        }
        .bibtable a { color: #1976D2; text-decoration: none; }
        .bibtable a:hover { text-decoration: underline; }

        /* Empty states: a line of guidance, not a notice. No panel, no colour,
           centred in the space the content will fill. */
        [class*="st-key-emptystate"] [data-testid="stAlertContainer"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 2.6rem 1rem !important;
            text-align: center;
        }
        [class*="st-key-emptystate"] [data-testid="stAlertContainer"] p {
            color: #6B655D !important;
            margin: 0 auto !important;
            max-width: 34rem;
        }
        [class*="st-key-emptystate"] [data-testid="stAlertContainer"] svg { display: none; }

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
        /* The track spans the tree column, so equal quarters are wide enough for
           "Comparanda" without clipping. */
        .st-key-text_set_pick [data-testid="stButtonGroup"] { width: 100% !important; }
        .st-key-text_set_pick [data-baseweb="button-group"] {
            display: flex !important;
            position: relative;
            /* Four 80px segments, not the full column width. */
            width: 324px !important;
            max-width: none !important;   /* Streamlit caps it at fit-content */
            gap: 0 !important;
            background: #EDEBE7;
            border: 1px solid #E0DBD2;
            border-radius: 999px;
            padding: 2px;
        }
        /* The thumb: one white pill that slides under the labels. The four
           segments are equal quarters, so its travel is a plain percentage —
           no measuring, and it animates because Streamlit reuses the group
           element across reruns and only the active attribute changes. */
        .st-key-text_set_pick [data-baseweb="button-group"]::before {
            content: "";
            position: absolute;
            top: 2px; left: 2px;
            height: calc(100% - 4px);
            width: calc((100% - 4px) / 4);
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
        .st-key-text_set_pick [data-baseweb="button-group"]:has(
            button:nth-of-type(4)[kind="segmented_controlActive"])::before {
            transform: translateX(300%);
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
        /* Sources catalogue: every cell answers a click (select the row, or open
           the tablet via its museum number), so the grid gets the hand cursor. */
        [class*="st-key-cat_table"] [data-testid="stDataFrame"],
        [class*="st-key-cat_table"] canvas {
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
        # An illegible 'x' *inside* a word (ku-x) contributes no sign, matching
        # compute_ratios.annotate_signs (get_token_type types it 'other' there);
        # the corpus figures in the article come from that path, so the app must
        # stay in lockstep with it.
        if _is_nontext(s):
            continue
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
    # The post-Achaemenid horizon: scholarly tablets of these dates belong to the
    # Late Babylonian tradition the third bucket already stands for, so a text
    # dated by dynasty rather than by ductus still lands in a period the charts
    # can plot. Only the corpus uses the labels above; these serve imports.
    "Achaemenid": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Persian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Seleucid": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Hellenistic": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Parthian": "Neo-Babylonian/Assyrian + Late Babylonian",
    "Arsacid": "Neo-Babylonian/Assyrian + Late Babylonian",
}

def period_is_plottable(period):
    """True if this (already broad-mapped) period is one the charts can place.

    Anything else — no `period:` at all, or a label the mapping does not know —
    is counted in pooled figures but has no period to sit at, so the app flags
    it and offers the text for editing rather than guessing a date for it."""
    return period in PERIOD_ORDER

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

# Memoization for trio()/comp(). The slices handed to them are row-subsets of the
# session-cached frames (rebuilt only on a corpus load/import), so a (frame
# namespace, row index) pair pins the result exactly: the report tables — dozens
# of trio() calls over the same slices on every rerun — become dictionary
# lookups. Frames that change under the user's hands (the Editor's scored
# buffers, uploads) carry no namespace and are never memoized. The namespace is
# stamped onto the frames where they are built (see the FRAMES block) and rides
# through slicing via DataFrame.attrs; the store is cleared there too.
def _slice_key(sub, *flags):
    if sub is None:
        return None
    ns = sub.attrs.get('_memo_ns')
    if ns is None:
        return None
    try:
        return (ns, len(sub), hash(sub.index.to_numpy().tobytes())) + flags
    except (TypeError, ValueError):
        return None

# (bin, macro, micro) for any slice, for a given monogram setting. Omen particles
# (DIŠ, BE, …) are logograms and are counted as such unless no_particles is set.
def trio(sub, monogram, no_particles=False):
    _key = _slice_key(sub, 'trio', monogram, no_particles)
    _memo = st.session_state.setdefault('_slice_memo', {})
    if _key is not None and _key in _memo:
        return _memo[_key]
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
    if _key is not None:
        _memo[_key] = (binv, macro, micro)
    return binv, macro, micro

# Word composition (pure-logographic / mixed / syllabic) for any slice — the
# breakdown the three measures summarise. Same conventions as trio().
def comp(sub, monogram, no_particles=False):
    _key = _slice_key(sub, 'comp', monogram, no_particles)
    _memo = st.session_state.setdefault('_slice_memo', {})
    if _key is not None and _key in _memo:
        return _memo[_key]
    sub = _drop_contentless(sub)
    if no_particles:
        sub = _drop_particles(sub)
    sub = sub[sub['type'].isin(['logogram', 'phonetic'])]   # determinatives excluded
    ma = sub['_mono'] & monogram
    out = word_composition(sub['_nl'] + ma.astype(int),
                           sub['_nph'] - ma.astype(int))
    if _key is not None:
        _memo[_key] = out
    return out

def _fmt(v):
    return f"{v:.3f}" if pd.notna(v) else "–"


def per_omen_figure(chart_df, metric, color, whole=None, height=480, marker_size=12):
    """The per-omen LDI curve for ONE text — the single engine behind both the
    Text view and the Editor's report pane.

    chart_df: one row per omen, in text order, with 'seq', 'omen', the three
    metric columns, and optionally 'section' (Obverse/Reverse/...).
    whole: the pooled LDI of the whole text; when given it is labelled at the top
    beside the highest and lowest per-omen value.

    Lines are straight segments, never splines: the omens are discrete, and a
    smoothed curve would draw values between them that do not exist.
    """
    fig = go.Figure()

    # Grey dotted line UNDER the coloured one, bridging content-less omens
    # (lone-DIŠ / all-broken lines carry no LDI, so they leave a gap in the
    # coloured trace). connectgaps spans the gap so the reading stays visually
    # continuous without inventing a value for the broken omens. Only for an
    # INTERIOR gap: a leading/trailing NaN (a broken last line, say) has nothing
    # to bridge to, so the trace would be pure noise.
    y = chart_df[metric]
    valid = y.notna()
    interior_gap = (bool(valid.any())
                    and bool(y.loc[valid.idxmax():valid[::-1].idxmax()].isna().any()))
    if interior_gap:
        fig.add_trace(go.Scatter(
            x=chart_df['seq'], y=y, mode='lines',
            line=dict(width=1.5, color='#BDBDBD', dash='dot'),
            connectgaps=True, hoverinfo='skip', showlegend=False))

    fig.add_trace(go.Scatter(
        x=chart_df['seq'], y=y, mode='lines',
        line=dict(width=2.5, color=color),
        connectgaps=False, hoverinfo='skip', showlegend=False))

    _cols = [c for c in ('omen', 'bin', 'macro', 'micro') if c in chart_df.columns]
    fig.add_trace(go.Scatter(
        x=chart_df['seq'], y=y, mode='markers',
        marker=dict(size=marker_size, color=color, line=dict(width=1, color='white')),
        customdata=chart_df[_cols].to_numpy(),
        hovertemplate="omen %{customdata[0]}<br>"
                      "bin %{customdata[1]:.2f} · macro %{customdata[2]:.2f} · "
                      "micro %{customdata[3]:.2f}<extra></extra>"
                      if len(_cols) == 4 else
                      "omen %{customdata[0]}<br>" + metric + " %{y:.3f}<extra></extra>",
        showlegend=False))

    # Highest / whole-text / lowest LDI, labelled at the top. "whole" is the
    # pooled LDI for the entire text (not the mean of the per-omen dots).
    if whole is not None and valid.any():
        # Top-left in PAPER coordinates, so it cannot collide with the section
        # labels that sit above the curve at their own x.
        fig.add_annotation(
            x=0.01, y=0.99, xref='paper', yref='paper',
            text=f"highest {y.max():.2f}<br>whole {whole:.2f}<br>lowest {y.min():.2f}",
            showarrow=False, xanchor='left', yanchor='top', align='left',
            font=dict(size=11, color=color))

    # Section boundaries (obverse | reverse | edge ...): a tablet's line numbering
    # usually restarts at each side, so without a marker the curve reads as one
    # continuous run and the second side looks absent.
    if 'section' in chart_df.columns:
        # "Unspecified" is the loader's placeholder for text before any @section
        # marker, not a side of the tablet: no boundary is drawn against it.
        sec = chart_df['section'].fillna("").replace("Unspecified", "")
        for i in range(1, len(chart_df)):
            if sec.iloc[i] and sec.iloc[i - 1] and sec.iloc[i] != sec.iloc[i - 1]:
                x = (chart_df['seq'].iloc[i] + chart_df['seq'].iloc[i - 1]) / 2
                fig.add_vline(x=x, line=dict(color="#BDBDBD", width=1, dash="dash"))
                fig.add_annotation(x=x, y=1.18, xref='x', yref='y',
                                   text=str(sec.iloc[i]), showarrow=False,
                                   yanchor='bottom', font=dict(size=9, color="#9E9E9E"))

    # Omen labels on the x axis. Up to 40 omens every line number fits; beyond
    # that, label every nth (about 25 across the axis) and always keep the first
    # and the last, so a long text still says where you are in it instead of
    # showing a bare axis. The labels are the edition's own line numbers, which
    # are not always a plain 1..n (VAT 10418 runs 1'..25' then 1..25), so they
    # carry information the position alone does not.
    n = len(chart_df)
    if n <= 40:
        pick = list(range(n))
    else:
        step = (n + 24) // 25
        pick = list(range(0, n, step))
        if pick[-1] != n - 1:
            pick.append(n - 1)
    fig.update_layout(
        margin=dict(t=14), template="simple_white", font_family="Arial",
        xaxis_title="Omen (in text order)", yaxis_title=f"LDI — {metric}",
        yaxis=dict(range=[-0.05, 1.30], tickmode='array',
                   tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
        xaxis=dict(tickmode='array',
                   tickvals=chart_df['seq'].iloc[pick],
                   ticktext=chart_df['omen'].iloc[pick],
                   tickangle=0 if n <= 40 else -45,
                   tickfont=dict(size=10 if n <= 40 else 9)),
        height=height, hovermode="closest", showlegend=False)
    return fig

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

# The counting marks actually used in the corpus, most frequent first; `line`
# is the default for anything without omen divisions.
COUNTING_MARKS = ["line", "DIŠ", "BE", "šum-ma", "UD", "BAD", "AŠ", "šum₄-ma", "§"]

def frontmatter_get(text, key):
    """Read one key out of a text's YAML frontmatter (None if absent)."""
    m = re.match(r"---\n(.*?)\n---", text or "", re.S)
    if not m:
        return None
    # [ 	]* not \s*: \s matches the newline, so an empty value would swallow
    # the next line and report `discipline:` as the period
    hit = re.search(rf"^{re.escape(key)}:[ 	]*(.*)$", m.group(1), re.M)
    return hit.group(1).strip() if hit else None

def frontmatter_set(text, key, value):
    """Set one key in the frontmatter, adding the block if the text has none."""
    text = text or ""
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    if not m:
        return f"---\n{key}: {value}\n---\n\n" + text.lstrip("\n")
    body = m.group(1)
    if re.search(rf"^{re.escape(key)}:", body, re.M):
        body = re.sub(rf"^{re.escape(key)}:.*$", f"{key}: {value}", body, count=1, flags=re.M)
    else:
        body = body.rstrip() + f"\n{key}: {value}"
    return text[:m.start(1)] + body + text[m.end(1):]

@st.cache_data(show_spinner=False)
def corpus_subfolders(period, genre):
    """Sub-folders that already exist under this period/discipline, for the picker."""
    root = os.path.dirname(data_path_for(period, genre, "x.txt"))
    out = []
    if os.path.isdir(root):
        for cur, dirs, _files in os.walk(root):
            rel = os.path.relpath(cur, root).replace(os.sep, "/")
            if rel != ".":
                out.append(rel)
    return sorted(out)

def save_buffer(name, text):
    """Write a buffer to data/ and return (path, note).

    A buffer opened from the corpus goes back where it came from. A new or fetched
    one is filed by its frontmatter: the raw period is folded into Old/Middle/Neo
    (so "Middle Assyrian" and "Middle Babylonian" share data/middle/) and the
    discipline becomes the folder under it. Missing values are reported rather
    than guessed at silently."""
    src = st.session_state.get('text_sources', {}).get(name, {})
    if src.get('path'):
        return (src['path'], None) if _save_text_edit(name, text) else (None, "write failed")
    period, genre, folder = _front_pg(text)
    _dest = os.path.dirname(data_path_for(period, genre, name, folder))
    note = None
    if not str(period or "").strip() or not str(genre or "").strip():
        note = ("no period/discipline in the frontmatter, so it was filed under "
                f"`{_dest}`")
    elif period not in PERIOD_MAPPING:
        note = (f"period “{period}” is not one the corpus knows, so it was filed under "
                f"`{_dest}`")
    path = _persist_text(name, text, period, genre)
    st.session_state.setdefault('text_sources', {})[name] = {"path": path, "content": text}
    _reload_corpus()
    return path, note

def _esc_html(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def score_text(name, text):
    """Score one edited buffer on its own, without touching the loaded corpus.

    Returns the enriched full/preserved frames and the unique-omen frame, or None
    when the text carries nothing scorable."""
    anns, anns_pres = _ingest_text(name, text)
    if not anns:
        return None
    full = enrich_signs(pd.DataFrame(anns))
    pres = enrich_signs(pd.DataFrame(anns_pres)) if anns_pres else None
    uo = (full.drop_duplicates(subset=['filename', 'omen_id'])
          if 'omen_id' in full.columns else None)
    return {'full': full, 'pres': pres, 'uo': uo}

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

def render_table_with_copy(styler, source_df, key, label="📋 Copy table…", control=None):
    """Render a Styler HTML table with a dropdown beside it that copies it to the
    clipboard in the chosen format: rich HTML (pastes as a real table into Excel /
    Word / Sheets), Markdown, or tab-separated text. Falls back to plain text if
    the rich-clipboard API is unavailable (e.g. a non-secure context).

    The control sits to the right of the table rather than under it: the tables are
    narrower than the page, so the space is there, and a caption or the next
    heading then follows the table directly."""
    table_html = styler.to_html()
    if control is not None:
        # A narrow column has no room beside the table; the caller hands us a
        # container (a heading row, say) and the control goes there instead.
        _row = control
        st.markdown(table_html, unsafe_allow_html=True)
    else:
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
    for dp, dirs, fs in os.walk("data"):
        # The catalogue describes the published corpus — the manuscripts the
        # article stands on, with their editions and eBL links. Texts the reader
        # imported are theirs, not the catalogue's, so _custom is walked past.
        dirs[:] = [d for d in dirs if os.path.join(dp, d) != CUSTOM_DIR]
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
    restorations counted. Covers the corpus plus the supplementary, comparanda
    and held-out sets; a text in no set (never tokenized) is simply absent.

    Cached in session state against the token count, so an import or a reset
    recomputes it; the Sources tab's ↻ Refresh drops it explicitly."""
    sets = (st.session_state.get('annotations', []),
            st.session_state.get('supplementary', []),
            st.session_state.get('comparanda', []),
            st.session_state.get('heldout', []))
    # The cache check runs on every rerun, so it must not pay for concatenating
    # ~100k token dicts just to take a length: sum the lengths, and build the
    # combined list only on a miss.
    n_anns = sum(len(s) for s in sets)
    cached = st.session_state.get('_cat_ldi')
    if cached and cached[0] == n_anns:
        return cached[1]
    anns = [a for s in sets for a in s]

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
    st.session_state['_cat_ldi'] = (n_anns, out)
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

# Where imported texts are filed. The leading underscore is what keeps them out
# of the published corpus: load_local_data skips "_"-prefixed folders when it
# walks data/, exactly as it does for _comparanda. So an import is permanent on
# disk and travels with the app, but never silently joins the counts the article
# reports — it is loaded as its own set and the reader chooses the scope.
CUSTOM_DIR = os.path.join("data", "_custom")

# Broad period → data/ subfolder, for saving edited/imported texts back to disk.
PERIOD_FOLDER = {
    "Old Babylonian": "old",
    "Middle Babylonian/Assyrian": "middle",
    "Neo-Babylonian/Assyrian + Late Babylonian": "new",
}
def data_path_for(period, genre, filename, subfolder=None, root="data"):
    """Where a text with this (raw) period/genre should live under data/.

    `subfolder` is the optional path below the discipline — "liver/martu",
    "EAE20" — which is how the corpus nests, and which the loader reads back as
    topic and feature. Segments are sanitised and any .. is dropped, so a text
    can never be written outside data/.

    `root` is the tree it is filed into: "data" for the published corpus,
    CUSTOM_DIR for texts the reader imports (see the Upload dialog)."""
    broad = PERIOD_MAPPING.get(period, period)
    # A text whose period is missing or unrecognised is filed under
    # `unspecified/`, NOT under `new/`: the loader reads a text's period off its
    # folder when the frontmatter is silent, so the old fallback quietly dated
    # every undated import to the first millennium. `unspecified` reads back as a
    # period no chart can place, which is what puts it in front of the reader.
    pf = PERIOD_FOLDER.get(broad, "unspecified")
    gf = re.sub(r"[^a-z0-9]+", "-", str(genre).lower()).strip("-") or "unspecified"
    parts = list(os.path.normpath(root).split(os.sep)) + [pf, gf]
    for seg in str(subfolder or "").replace("\\", "/").split("/"):
        seg = re.sub(r"[^A-Za-z0-9._-]+", "-", seg.strip()).strip("-.")
        if seg and seg not in (".", ".."):
            parts.append(seg)
    parts.append(filename)
    return os.path.join(*parts)

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

# Illegible signs and editorial annotations are not writing: 'x'/'X' tokens in any
# editorial wrapper, the printed editions' '(leer)'/'(Rasur)' notes, and the
# empty-slot mark 'ø' are typed 'other' and never counted. Mirrors
# compute_ratios._is_nontext exactly — the two must not drift.
NONTEXT_EDITORIAL = {'(leer)', '(rasur)', '(o)', '(blank)', '(blank?)', '(lacuna)', 'ø'}
_NONTEXT_STRIP = str.maketrans('', '', "()<>⸢⸣˹˺⌈⌉'\"?!.…—–-")

def _is_nontext(token):
    t = str(token)
    if 'x' not in t and 'ø' not in t and '(' not in t:
        return False                      # hot path: cannot match anything below
    if t.lower() in NONTEXT_EDITORIAL:
        return True
    core = t.translate(_NONTEXT_STRIP)
    # lowercase 'x' only: uppercase X is a Roman-numeral logogram (XXX = 30 =
    # Sîn, XX = Šamaš in the "Hand of DN" formulas), never an illegible sign
    return core != '' and set(core) == {'x'}


def get_token_type(token):
    # Illegible / editorial tokens: never counted (word level and sign level).
    if _is_nontext(token):
        return "other"
    # Rule 1: Logograms (All caps OR specific particles)
    if token in LOGOGRAM_PARTICLES:
        return "logogram"
    if token.rstrip('?!') in NUMBER_LOGOGRAMS:  # 15/150/30 (right/left/Sîn)
        return "logogram"
    if any(c.isupper() for c in token):
        return "logogram"
    # Rule 2: Phonetic (Contains lowercase), e.g. "i-na-at", "šum-ma"
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
        # Skip line numbers e.g. "1.", "1'.", the eBL relative form "a+34.", or
        # the paren style "1)" of the KUB 37 / Boğazköy files — a line label,
        # not a word to display or score.
        if re.match(r"^(?:[a-zA-Z]{1,2}\+)?\d+'?[.)]$", raw_token):
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
                                content = re.sub(r'^\d+\'?[.)]\s*', '', content)
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
                            id_match = re.match(r'^(\d+\'?)[.)]', line)
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
                            clean_regex = r'^(?:(?:[a-zA-Z]{1,2}\+)?\d+\'?[.)]\s*)?\s*(?:%\w+\s+)?' + re.escape(delimiter) + r'(?![0-9\u2080-\u2089a-zA-Z\-])'
                            
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
                            id_match = re.match(r'^(\d+\'?)[.)]', line)
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

def _reload_custom():
    """Re-read the reader's own corpus (data/_custom) after writing to it."""
    src = {}
    if os.path.isdir(CUSTOM_DIR):
        st.session_state['custom'] = load_local_data(
            CUSTOM_DIR, include_excluded=True, sources=src, preserved_only=False)
        st.session_state['custom_pres'] = load_local_data(
            CUSTOM_DIR, include_excluded=True, preserved_only=True)
    else:
        st.session_state['custom'] = []
        st.session_state['custom_pres'] = []
    st.session_state.setdefault('text_sources', {}).update(src)

def _front_pg(content):
    """Read period/genre from a text's YAML frontmatter (to choose its data/ path)."""
    period, genre, folder = "Unspecified", "Unspecified", ""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                period = fm.get('period', period)
                genre = fm.get('discipline', fm.get('genre', genre))
                folder = fm.get('folder', fm.get('subfolder', folder))
            except Exception:
                pass
    return period, genre, folder

def _persist_text(filename, content, period=None, genre=None, subfolder=None, root="data"):
    """Write a text into data/ at its period/genre-derived path; return the path."""
    _p, _g, _sub = _front_pg(content)
    period = _p if period is None else period
    genre = _g if genre is None else genre
    path = data_path_for(period, genre, filename,
                         _sub if subfolder is None else subfolder, root=root)
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

def open_in_editor(filename):
    """Open a corpus text as an Editor buffer and switch to the Editor tab.

    A buffer already open under this name is only activated, so unsaved work is
    never clobbered; otherwise the text is read from its session source, the same
    store the Editor's own Open dialog reads."""
    bufs = st.session_state.setdefault('ed_bufs', {})
    if filename not in bufs:
        src = st.session_state.get('text_sources', {}).get(filename, {})
        if not src.get('content'):
            return False
        bufs[filename] = {"text": src['content'],
                          "saved": src['content'] if src.get('path') else None,
                          "path": src.get('path'), "scored": None, "stale": True}
    st.session_state['ed_active'] = filename
    st.session_state['goto_nav'] = "Editor"
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
NAV = ["LDI", "Sources", "Bibliography", "Editor"]
_PAGES = ["Introduction"] + NAV
# The four LDI analyses used to be top-level tabs; they now live as sub-views
# inside the single "LDI" tab, switched by a lazy selector (only the chosen one
# renders). "Overview" is the former "Global" page.
# --- Per-discipline topic labelling ---------------------------------------------
# Every label function takes a row of that text's metadata, because each
# series records its sub-chapter somewhere else: the folder path for
# extispicy, `topic` for astrology, `series` for Sakikkû,
# `canonical_tablet` for izbu, the `publication` line for Šumma Ālu.
TOPIC_FIELDS = ('topic', 'feature', 'series', 'canonical_tablet',
                 'publication', 'note', 'source_note', 'recension', 'subpath')

def topic_blob(row, *fields):
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
    s = topic_blob(row, 'series', 'recension', 'subpath')
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
    s = topic_blob(row, 'canonical_tablet', 'topic', 'source_note')
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
    s = topic_blob(row, 'topic', 'publication', 'note', 'source_note', 'series')
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

def topic_labels(frame, genre):
    """Sub-chapter label per text in `frame`, mapped onto its rows.

    The metadata is file-level, so the label is computed once per text
    rather than once per token. Returns [] when the discipline has no
    sub-chapter scheme."""
    fn, _order = TOPIC_GENRES.get(genre, (None, []))
    if fn is None or frame.empty:
        return []
    have = [f for f in TOPIC_FIELDS if f in frame.columns]
    per_text = frame.groupby("filename")[have].first().to_dict("index")
    lab = {k: fn(rec) for k, rec in per_text.items()}
    return frame["filename"].map(lab).tolist()

LDI_SUBPAGES = ["Overview", "Discipline", "Region", "Topics", "Compare", "Text"]
_LEGACY_SUB = {"Global": "Overview", "Genre": "Discipline", "Text": "Text",     # old ?nav= targets → LDI subpage
               "Region": "Region", "Topics": "Topics"}
_LEGACY_PAGE = {"Tools": "Editor"}          # the Tools tab became the Editor

# In-app links (e.g. "?nav=Introduction" inside markdown/tables) navigate here.
# A "&ref=<bibkey>" (from a linkified citation) opens the Bibliography on that entry.
_qp_nav = st.query_params.get("nav")
_qp_ref = st.query_params.get("ref")
if _qp_nav in _LEGACY_PAGE:
    st.session_state['page'] = _LEGACY_PAGE[_qp_nav]
elif _qp_nav in _PAGES:
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
if st.session_state.get('goto_file'):
    # Early feedback for the jump: the Text page takes a moment to build, and
    # without this the click looks like it did nothing.
    st.toast(f"Opening **{st.session_state['goto_file'].rsplit('.txt', 1)[0]}** "
             "in the Text view…", icon="📖")
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

# Imported texts (data/_custom) — the reader's own corpus. Loaded as its own set,
# never folded into the published corpus; the scope switch on the LDI page decides
# whether the analyses read the published corpus, these, or both.
if 'custom' not in st.session_state:
    # Absent until the reader imports something, so the load is guarded:
    # load_local_data reports a missing directory as an error banner.
    _custsrc = {}
    if os.path.isdir(CUSTOM_DIR):
        st.session_state['custom'] = load_local_data(
            CUSTOM_DIR, include_excluded=True, sources=_custsrc, preserved_only=False)
        st.session_state['custom_pres'] = load_local_data(
            CUSTOM_DIR, include_excluded=True, preserved_only=True)
    else:
        st.session_state['custom'] = []
        st.session_state['custom_pres'] = []
    st.session_state.setdefault('text_sources', {}).update(_custsrc)

# Supplementary witnesses (data/kal5) — held out of the LDI counts but browsable
# in the Text tab alongside the corpus and comparanda.
if 'supplementary' not in st.session_state:
    st.session_state['supplementary'] = load_local_data(
        "data/kal5", include_excluded=True, preserved_only=False)
    st.session_state['supplementary_pres'] = load_local_data(
        "data/kal5", include_excluded=True, preserved_only=True)

# Held-out corpus texts — files in the period folders (old/middle/new) that carry
# `exclude: true` (too fragmentary, or duplicates of counted tablets). Out of every
# count, but loadable here for individual inspection, as the article promises
# (CBS 3831, Emar 700, the EAE 20 recension witnesses, ...). Copied to a temp tree
# so only these eight-odd files are tokenized, not the whole corpus again.
if 'heldout' not in st.session_state:
    import tempfile as _tf, shutil as _sh
    _hx = []
    for _dp, _, _fs in os.walk("data"):
        _parts = os.path.relpath(_dp, "data").split(os.sep)
        if _parts and _parts[0] in ("old", "middle", "new"):
            for _f in _fs:
                if _f.endswith(".txt"):
                    _p = os.path.join(_dp, _f)
                    if re.search(r"^\s*exclude:\s*true",
                                 open(_p, encoding="utf-8").read(), re.M):
                        _hx.append((_p, os.path.relpath(_p, "data")))
    st.session_state['heldout'] = []
    st.session_state['heldout_pres'] = []
    if _hx:
        with _tf.TemporaryDirectory() as _td:
            for _p, _rel in _hx:
                _dst = os.path.join(_td, _rel)
                os.makedirs(os.path.dirname(_dst), exist_ok=True)
                _sh.copy(_p, _dst)
            st.session_state['heldout'] = load_local_data(
                _td, include_excluded=True, preserved_only=False)
            st.session_state['heldout_pres'] = load_local_data(
                _td, include_excluded=True, preserved_only=True)

# --- UI: Main Layout ---

if page == "Introduction":
    # Landing / index — a companion-to-the-article introduction.
    st.markdown("### A Digital Tool for Analyzing Logographic Density in Cuneiform Omen Texts")
    st.markdown(
        "This application is the companion to **_The Logographic Shift: Tracking the "
        "“Sumerianizing” Process in Cuneiform Divination_** *(L. Sáenz, "
        "[volume citation to fill in])*. It carries the article's complete dataset — "
        "**6,978 omens in 196 texts**, Old Babylonian to Late Babylonian, plus the KAL 5 "
        "supplement, the comparanda, and the held-out witnesses — as plain transliteration "
        "files with YAML metadata (period, discipline, provenance, counting mode). Every "
        "figure and table in the article can be recomputed here from those files, for any "
        "slice: omen, tablet, topic, region, or period.\n\n"
        "Transliterations follow eBL-ATF conventions: uppercase = Sumerogram, lowercase = "
        "syllabic, `{braces}` = determinative, `[brackets]` = editorial restoration, `%sux` = "
        "a Sumerian line. Scoring uses one fixed convention — determinatives excluded, the "
        "omen-opening particle and the number-logograms 15/150/30 counted, Sumerian lines held "
        "out, restorations counted — and is token-for-token identical to the batch pipeline "
        "(`compute_ratios.py`) that produced the article's published figures."
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
        "| Word | Signs | logographic signs | bin (word) | macro (word fraction) | micro (signs) |\n"
        "|------|-------|:-----------------:|:----------:|:---------------------:|:-------------:|\n"
        "| `DIŠ` | DIŠ | 1 / 1 | logographic = 1 | 1.00 | 1 log / 1 |\n"
        "| `LUGAL-um` | LUGAL · um | 1 / 2 | logographic = 1 | 0.50 | 1 log / 2 |\n"
        "| `i-na-aḫ` | i · na · aḫ | 0 / 3 | syllabic = 0 | 0.00 | 0 log / 3 |"
    )
    st.markdown(
        "- **bin** = 2 logographic words ÷ 3 words = **0.67**\n"
        "- **macro** = mean(1.00, 0.50, 0.00) = **0.50**\n"
        "- **micro** = 2 logographic signs ÷ 6 signs total = **0.33**\n\n"
        "Same text, three numbers, and only one ordering is guaranteed: **bin ≥ macro** always, "
        "since a word containing a logogram scores 1 in bin and at most 1 in macro. **macro and "
        "micro are not ordered** — macro weighs every word alike, micro weighs each by its number "
        "of signs, so which is greater depends on whether a text's long words are its logographic "
        "ones. Across this corpus micro is the greater in 7 of the 196 texts and in 10.5 % of "
        "omens, and in four texts it exceeds even bin. Comparing the three is a quick read on "
        "*how* a text is logographic — whole-word substitution versus dense sign-by-sign writing."
    )

    st.markdown(
        "Four counting decisions sit underneath all three measures. Each is taken in advance "
        "and held throughout, and each is reported as its own column beside the baseline, so "
        "what it is worth to a given slice can be read off directly:"
    )

    st.markdown("##### The ina / ana monogram")
    st.markdown(
        "The prepositions **ina** and **ana** are routinely written with a single sign each — "
        "**monograms**: one sign for a whole word, on the border between syllabic and "
        "logographic. The baseline counts them as syllabic (they are lowercase in "
        "transliteration); the **ina/ana** column re-reads them as logograms. Because they "
        "recur constantly, this is the convention that moves scores furthest: pooled bin "
        "0.682 → 0.739, and a heavily *ina*-laden tablet like BM 121034 from 0.744 to 0.857."
    )

    st.markdown("##### Restorations")
    st.markdown(
        "Editors supply lost text from parallel manuscripts, marked `[…]` in the "
        "transliteration. The baseline counts a restored sign like a preserved one — the "
        "restoration is the editor's judgement of what stood on the tablet. The **restor.** "
        "column scores the preserved signs alone. The decision is not neutral: what can be "
        "restored is the formulaic, and the formulaic writings are the logographic ones, so "
        "dropping restorations usually lowers a broken tablet's score — pooled bin "
        "0.682 → 0.661, and the 62 %-restored BM 121034 falls from 0.744 to 0.634. A large "
        "gap between the two columns flags a heavily reconstructed text."
    )

    st.markdown("##### The opening particle")
    st.markdown(
        "Nearly every omen opens with the conjunction *šumma* “if”, written logographically "
        "(DIŠ, BE, BAD, UD, AŠ) — one guaranteed logogram per omen, arguably structural "
        "markup rather than text. The baseline counts it; the **no particle** column drops "
        "it: pooled bin 0.682 → 0.651. The effect is mechanical but not uniform — the "
        "shorter the omens, the more one word weighs, so the diagnostic corpus moves most."
    )

    st.markdown("##### Word composition")
    st.markdown(
        "Every scored word is one of three kinds: a **pure logogram** (`LUGAL`), a **mixed** "
        "writing — logogram plus phonetic complement (`LUGAL-um`) — or a fully **syllabic** "
        "spelling (*šar-rum*). The **pure % / mixed % / syll %** columns give this breakdown, "
        "which the three measures summarise but cannot replace: bin counts `LUGAL` and "
        "`LUGAL-um` alike, so two rows can agree in bin and still differ threefold in mixed "
        "writing. Diachronically the mixed class is the fast riser — 2.5 % of words in the "
        "Old period against 18.2 % in the Neo."
    )

    st.divider()
    st.markdown("#### How to use it")
    st.markdown(
        "The **LDI** tab holds six views:\n\n"
        "- **Overview** — the diachronic trend: pooled LDI per period, then per discipline.\n"
        "- **Discipline** — one node per text; click a node to open that tablet in the Text view.\n"
        "- **Region** — the same by find-spot, and discipline against region.\n"
        "- **Topics** — by sub-chapter: liver regions and lung, celestial body and phenomenon.\n"
        "- **Compare** — any series side by side: periods, disciplines, regions, topics, "
        "single texts, and the held-out sets.\n"
        "- **Text** — a single tablet, colour-coded sign by sign, with per-line and whole-text "
        "LDI. The **Text set** switch beside the views opens the comparanda, the KAL 5 "
        "supplement, and the held-out corpus texts, all outside the corpus counts.\n\n"
        "Every chart has a **bin / macro / micro** switch directly above it. The counting "
        "conventions are not switches: each report table prints them as columns beside the "
        "baseline, so you can see what each decision is worth instead of toggling it and "
        "reading the chart twice. The columns of every report table:\n\n"
        "- **texts**, **omens** — how many manuscripts and omen entries the row rests on.\n"
        "- **bin**, **macro**, **micro** — the three measures (above), at the baseline "
        "convention.\n"
        "- **ina/ana** — bin with the two monograms read as logograms.\n"
        "- **restor.** — bin on the preserved signs alone.\n"
        "- **no particle** — bin without the omen-opening particle.\n"
        "- **pure %**, **mixed %**, **syll %** — the word composition.\n\n"
        "Each of these is defined in its own section above.\n\n"
        "**Example** — the report row and per-omen curve of one tablet, VAT 10418 "
        "(Middle Assyrian lung omens, KAL 5 no. 63), exactly as the Text view shows them:\n\n"
        "| | texts | omens | bin | macro | micro | ina/ana | restor. | no particle "
        "| pure % | mixed % | syll % |\n"
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        "| VAT 10418 | 1 | 50 | 0.77 | 0.67 | 0.57 | 0.81 | 0.76 | 0.76 "
        "| 55.9 | 21.5 | 22.6 |\n\n"
        "Read against the definitions above: reading *ina*/*ana* as logograms lifts bin to "
        "0.81, dropping the restorations or the particle costs about 0.01 each — a "
        "well-preserved, genuinely logographic tablet — and a fifth of its words are "
        "mixed writings."
    )
    _fig = os.path.join(_APP_DIR, "assets", "trend-vat-10418-bin.png")
    if os.path.exists(_fig):     # not staged in every build; the text stands alone
        st.image(_fig,
                 caption="VAT 10418, bin LDI per omen — the same chart the Text view draws: "
                         "one node per omen in text order, the dashed line marking where the "
                         "obverse ends and the reverse begins.")

elif page == "Editor":
    # --- The editor: sources on the left, buffer in the middle, report on the right.
    # Nothing is scored while typing; Run scores the active buffer, Save writes it
    # to data/ and re-reads the corpus.
    _BUFS = st.session_state.setdefault('ed_bufs', {})

    _SCRATCH = ("---\nperiod: \ndiscipline: \nfolder: \ncounting: line\n---\n\n")

    def _ensure_open():
        """The editor is never empty: with nothing else open a scratch buffer
        stands ready, so a pasted line can be scored without opening a file
        first."""
        if not _BUFS:
            _BUFS["untitled.txt"] = {"text": _SCRATCH, "saved": None, "path": None,
                                     "scored": None, "stale": True}
            st.session_state['ed_active'] = "untitled.txt"

    def _open_buffer(name, text, path=None):
        _BUFS[name] = {"text": text, "saved": text if path else None,
                       "path": path, "scored": None, "stale": True}
        st.session_state['ed_active'] = name

    @st.dialog("Open", width="large")
    def _dlg_open():
        """Read a text that is already in the corpus into the editor."""
        _src = st.session_state.get('text_sources', {})
        _names = sorted(_src)
        if not _names:
            st.info("No corpus texts are loaded in this session.")
            return
        _pick = st.selectbox("Text", _names, key="ed_open_pick")
        if st.button("Open", type="primary", key="ed_open_go"):
            _open_buffer(_pick, _src[_pick].get('content', ""), _src[_pick].get('path'))
            st.rerun()

    @st.dialog("New text", width="large")
    def _dlg_new():
        """Start blank, or pull the text from eBL.

        Either way the result is a buffer: nothing reaches data/ until it is saved."""
        _kind = st.radio("Start from", ["Blank document", "eBL fragment",
                                        "eBL corpus chapter"],
                         key="ed_new_kind", horizontal=True)

        if _kind == "Blank document":
            st.caption("An empty buffer with a frontmatter stub. Fill in period, "
                       "discipline and the counting mark, then paste the transliteration.")
            if st.button("Create", type="primary", key="ed_new_go"):
                _n, _i = "untitled.txt", 1
                while _n in _BUFS:
                    _i += 1
                    _n = f"untitled-{_i}.txt"
                _open_buffer(_n, _SCRATCH)
                st.rerun()

        elif _kind == "eBL fragment":
            st.caption("A fragmentarium number (`K.4031`, `BM.33793`) or its eBL URL. "
                       "Discipline and period are read from the eBL record.")
            _id = st.text_input("eBL number / URL", key="ed_ebl_id", placeholder="K.4031")
            _mk = st.selectbox("Counting mark", COUNTING_MARKS, index=0, key="ed_ebl_mark")
            if st.button("Fetch", type="primary", key="ed_ebl_go") and _id.strip():
                _m = re.search(r"/(?:library|fragmentarium|fragments)/([^/?#]+)", _id.strip())
                _fid = _m.group(1) if _m else _id.strip()
                try:
                    _body, _meta = fetch_ebl_fragment(_fid)
                except Exception as _e:
                    st.error(f"Could not fetch “{_fid}” from eBL: {_e}")
                    return
                if not _body or not _body.strip() or _meta["n_lines"] == 0:
                    st.warning(f"“{_fid}” has no transliterated lines in eBL.")
                    return
                _pub = f"eBL fragment {_fid}"
                if _meta["publication"]:
                    _pub += f"; {_meta['publication']}"
                _open_buffer(f"{_fid}.txt",
                             f"---\ndiscipline: {_meta['genre']}\nperiod: {_meta['period']}\n"
                             f"counting: {_mk}\npublication: {_pub}\n---\n@text\n{_body}\n")
                st.rerun()

        else:
            st.caption("A corpus chapter URL (`https://www.ebl.lmu.de/corpus/D/1/4/SB/57`) "
                       "or its `genre/category/index/stage/name` path. The composite text "
                       "is pulled, which can take a few seconds.")
            _cp = st.text_input("Corpus URL / path", key="ed_ebl_corpus",
                                placeholder="D/1/4/SB/57")
            _cmk = st.selectbox("Counting mark", COUNTING_MARKS, index=1, key="ed_ebl_cmark")
            if st.button("Fetch", type="primary", key="ed_ebl_cgo") and _cp.strip():
                _parsed = parse_corpus_path(_cp.strip())
                if not _parsed:
                    st.error("Expected genre/category/index/stage/name, e.g. `D/1/4/SB/57`.")
                    return
                _g, _c, _i, _stg, _nm = _parsed
                try:
                    _cbody, _cmeta = fetch_ebl_corpus(_g, _c, _i, _stg, _nm)
                except Exception as _e:
                    st.error(f"Could not fetch corpus chapter {_cp}: {_e}")
                    return
                if not _cbody or _cmeta["n_lines"] == 0:
                    st.warning("That corpus chapter returned no composite lines.")
                    return
                _open_buffer(f"eBL-corpus-{_g}{_c}{_i}-{_stg}{_nm}.txt",
                             f"---\ndiscipline: {_cmeta['genre']}\nperiod: {_cmeta['period']}\n"
                             f"counting: {_cmk}\n"
                             f"publication: eBL corpus {_cmeta['path']} "
                             f"({_cmeta['manuscripts']} mss)\n"
                             f"edition: fetched from /api/texts/{_cmeta['path']}\n---\n"
                             f"@text\n{_cbody}\n")
                st.rerun()

    @st.dialog("Upload", width="large")
    def _dlg_upload():
        """One text or a batch, filed into data/ by each text's own frontmatter."""
        st.caption("One file, several at once, or a whole folder as a .zip. Imported "
                   "texts are kept as **your own corpus** under `data/_custom/` — "
                   "permanent on disk, and never folded into the published corpus. "
                   "Each text is filed by its own frontmatter: the period folds into "
                   "`old` / `middle` / `new`, the discipline becomes the folder under "
                   "it. A text without them lands under `new/unspecified/`. The scope "
                   "switch on the LDI page reads the published corpus, yours, or both.")
        _files = st.file_uploader("eBL-ATF .txt file(s)", type=["txt"],
                                  accept_multiple_files=True, key="ed_up")
        _zip = st.file_uploader("…or a .zip of a data folder", type=["zip"], key="ed_upzip")
        _folder = st.text_input("…or a folder on this machine", key="ed_uppath",
                                placeholder="C:/…/my-texts")
        _dest = st.text_input(
            "Sub-folder below the discipline (optional)", key="ed_updest",
            placeholder="liver/martu",
            help="Applied to every uploaded text that does not name a `folder:` of "
                 "its own. Leave empty to file each text directly under its "
                 "discipline.")
        _also = st.checkbox("Open them in the editor as well", key="ed_upopen")

        if st.button("Upload", type="primary", key="ed_upgo"):
            _items = []
            for _f in (_files or []):
                _items.append((os.path.basename(_f.name),
                               _f.getvalue().decode("utf-8", "replace")))
            if _zip:
                try:
                    with zipfile.ZipFile(io.BytesIO(_zip.getvalue())) as _z:
                        for _n in _z.namelist():
                            if _n.endswith(".txt") and not _n.endswith("/"):
                                _items.append((os.path.basename(_n),
                                               _z.read(_n).decode("utf-8", "replace")))
                except zipfile.BadZipFile:
                    st.error("That file is not a valid .zip archive.")
            if _folder.strip():
                if os.path.isdir(_folder.strip()):
                    for _root, _d, _fs in os.walk(_folder.strip()):
                        for _fn in _fs:
                            if _fn.endswith(".txt"):
                                with open(os.path.join(_root, _fn), encoding="utf-8") as _fh:
                                    _items.append((_fn, _fh.read()))
                else:
                    st.error(f"Folder not found: {_folder}")
            if not _items:
                st.warning("Nothing to upload — add a file, a .zip or a folder above.")
                return
            _paths = [_persist_text(_fn, _txt,
                                    subfolder=(_front_pg(_txt)[2] or _dest.strip() or None),
                                    root=CUSTOM_DIR)
                      for _fn, _txt in _items]
            _reload_custom()
            # Texts the charts cannot place — no `period:`, or a label the
            # mapping does not know. They are never silently dated: they open in
            # the editor with the frontmatter waiting, and a banner says so.
            _needs = []
            for (_fn, _txt), _pt in zip(_items, _paths):
                _raw = _front_pg(_txt)[0]
                if not period_is_plottable(PERIOD_MAPPING.get(_raw, _raw)):
                    _needs.append(_fn)
                    _open_buffer(_fn, _txt, _pt)
                elif _also:
                    _open_buffer(_fn, _txt, _pt)
            st.session_state['needs_period'] = _needs
            st.success(f"Filed {len(_paths)} text(s) into your corpus "
                       f"(`{CUSTOM_DIR}`). Pick the scope on the LDI page to analyse them.")
            if _needs:
                st.warning(
                    f"**{len(_needs)} text(s) carry no period the charts can place.** "
                    "Their omens are counted in the pooled totals but sit at no point "
                    "on the diachronic axis. They are open in the Editor — add a "
                    "`period:` line to the frontmatter and save.\n\n"
                    + "\n".join(f"- `{_n}`" for _n in _needs))
            for _pt in _paths[:8]:
                st.caption(f"`{_pt}`")
            if len(_paths) > 8:
                st.caption(f"… and {len(_paths) - 8} more.")

        st.divider()
        _n_cust = len({_a['filename'] for _a in st.session_state.get('custom') or []})
        if _n_cust:
            st.caption(f"Your corpus holds **{_n_cust} text(s)** under `{CUSTOM_DIR}`. "
                       "Discarding deletes those files from disk; the published corpus "
                       "is untouched.")
            if st.button(f"🗑 Discard my corpus ({_n_cust} text(s))", key="ed_dropcustom"):
                shutil.rmtree(CUSTOM_DIR, ignore_errors=True)
                _reload_custom()
                st.session_state['corpus_scope'] = "Published"
                st.success("Removed your imported texts; the published corpus is unchanged.")
        else:
            st.caption("Nothing imported yet. Uploaded texts are kept as your own corpus, "
                       "separate from the published one.")

        st.caption("Read the published corpus from disk again.")
        if st.button("Reload the published corpus", key="ed_reset"):
            _reload_corpus()
            st.success("Reloaded the published corpus.")

    _ensure_open()


    _act = st.session_state.get('ed_active')
    if _act not in _BUFS:
        _act = next(iter(_BUFS), None)
        st.session_state['ed_active'] = _act

    def _is_dirty(name):
        _b = _BUFS.get(name)
        return bool(_b) and _b["text"] != (_b["saved"] or "")

    _PLACEHOLDER = re.compile(r"^(scratch|untitled(-\d+)?)\.txt$")

    @st.dialog("Name this text")
    def _dlg_name(name):
        """Saving under `scratch.txt` would file the tablet under that name, so the
        name is asked for once, at the moment it starts to matter."""
        _b = _BUFS[name]
        st.caption("The file name is the tablet's name: it labels the text in every "
                   "table and chart, and Save writes it under this name.")
        _sug = (frontmatter_get(_b["text"], "publication") or "").split(";")[0].strip()
        _nm = st.text_input("File name", value="", placeholder=_sug or "K.2385.txt",
                            key=f"ed_nm_{name}")

        # Where it will land, and the chance to say otherwise. The corpus nests
        # below the discipline (extispicy/liver/martu), and the loader reads topic
        # and feature back out of those folders.
        _p, _g, _fold = _front_pg(_b["text"])
        _opts = ["(directly under the discipline)"] + corpus_subfolders(_p, _g) + ["new folder…"]
        _cur = _fold if _fold in _opts else ("new folder…" if _fold else _opts[0])
        _pick = st.selectbox("Sub-folder", _opts, index=_opts.index(_cur),
                             key=f"ed_dest_{name}")
        if _pick == "new folder…":
            _pick = st.text_input("Folder path below the discipline", value=_fold or "",
                                  placeholder="liver/martu", key=f"ed_destnew_{name}")
        elif _pick == _opts[0]:
            _pick = ""
        st.caption(f"Destination: `"
                   f"{os.path.dirname(data_path_for(_p, _g, 'x.txt', _pick))}`")

        _c1, _c2 = st.columns(2)
        if _c1.button("Save", type="primary", key=f"ed_nmok_{name}"):
            _nn = (_nm or "").strip()
            if not _nn:
                st.warning("Give the text a name first.")
                return
            _nn = _nn if _nn.endswith(".txt") else f"{_nn}.txt"
            if (_pick or "") != (_fold or ""):
                _b["text"] = (frontmatter_set(_b["text"], "folder", _pick) if _pick
                              else _b["text"])
            _bb = _BUFS.pop(name)
            _bb["path"], _bb["saved"] = None, None
            _BUFS[_nn] = _bb
            st.session_state['ed_active'] = _nn
            _path, _note = save_buffer(_nn, _bb["text"])
            if _path:
                _bb["saved"] = _bb["text"]
            st.rerun()
        if _c2.button("Cancel", key=f"ed_nmno_{name}"):
            st.rerun()

    @st.dialog("Unsaved changes")
    def _dlg_close(name):
        st.write(f"**{name}** has changes that were never saved.")
        _c1, _c2, _c3 = st.columns(3)
        if _c1.button("Save & close", type="primary", key=f"ed_sc_{name}"):
            if save_buffer(name, _BUFS[name]["text"])[0]:
                _BUFS.pop(name, None)
                st.session_state['ed_active'] = next(iter(_BUFS), None)
                _ensure_open()
                st.rerun()
        if _c2.button("Discard", key=f"ed_dc_{name}"):
            _BUFS.pop(name, None)
            st.session_state['ed_active'] = next(iter(_BUFS), None)
            _ensure_open()
            st.rerun()
        if _c3.button("Cancel", key=f"ed_cc_{name}"):
            st.rerun()

    # Leaving the page with unsaved work is the one exit Streamlit cannot see;
    # a beforeunload handler on the parent window covers it.
    if any(_is_dirty(_n) for _n in _BUFS):
        components.html(
            """<script>
                 const w = window.parent;
                 w.onbeforeunload = function (e) { e.preventDefault(); return ''; };
               </script>""", height=0)
    else:
        components.html(
            """<script> window.parent.onbeforeunload = null; </script>""", height=0)

    @st.fragment
    def _editor_pane(_act):
        """The buffer and its report, isolated: a keystroke redraws this pane
        and nothing else, and the corpus frames are never touched. Run is what
        scores; Save is what writes."""
        _pane, _rep = st.columns([5.0, 5.0], gap="large")
        with _pane:
            # A horizontal container, not a third column: the toolbar belongs to
            # the editor, and this keeps them inside one bordered pane.
            with st.container(horizontal=True, gap="small", key="edpane"):
                _edit = st.container()
                _tool = st.container(key="edtool")
        with _edit:
            if not _act:
                with st.container(key="emptystate_editor"):
                    st.info("Open a text from the corpus, upload one, paste one, or start "
                            "a new one. Nothing is scored until you press Run.")
            else:
                _buf = _BUFS[_act]
                _cur_mark = frontmatter_get(_buf["text"], "counting") or "line"
                _marks = COUNTING_MARKS + ([_cur_mark] if _cur_mark not in COUNTING_MARKS else [])
                with _tool:
                    # Icons only: the tooltips carry the words, and the column stays
                    # narrow enough to leave the buffer its width.
                    _close = st.button("✕", key=f"ed_x_{_act}", use_container_width=True,
                                       help="Close this buffer")
                    _save = st.button("💾", key=f"ed_save_{_act}", use_container_width=True,
                                      help="Save to data/ and re-read the corpus")
                    st.markdown('<div class="edtoolsep"></div>', unsafe_allow_html=True)
                    _run = st.button("▶", key=f"ed_run_{_act}", type="primary",
                                     use_container_width=True, help="Score this buffer")
                    # The file name is the tablet's name everywhere in the app, and
                    # it decides what Save writes; renaming detaches the buffer from
                    # its old file, so Save files it afresh from the frontmatter.
                    with st.popover("✎", use_container_width=True,
                                    help=f"Name: {_act}"):
                        st.caption("The file name is the tablet's name: it labels the "
                                   "text in every table and chart, and Save writes it "
                                   "under this name.")
                        _nm = st.text_input("File name", value=_act,
                                            key=f"ed_name_{_act}",
                                            label_visibility="collapsed")
                        if st.button("Rename", key=f"ed_ren_{_act}"):
                            _nn = (_nm or "").strip()
                            _nn = _nn if _nn.endswith(".txt") else f"{_nn}.txt"
                            if _nn and _nn != _act and _nn != ".txt":
                                _b = _BUFS.pop(_act)
                                _b["path"], _b["saved"] = None, None
                                _BUFS[_nn] = _b
                                st.session_state['ed_active'] = _nn
                                st.rerun()

                    # The mark is a word, not a glyph, so it lives inside a popover
                    # and the column stays one icon wide.
                    with st.popover("§", use_container_width=True,
                                    help=f"Counting mark: {_cur_mark}"):
                        st.caption("What divides the text into omens. `line` counts line "
                                   "by line; any other value is the sign that opens an "
                                   "omen. Written into the frontmatter.")
                        _mark = st.selectbox(
                            "Counting mark", _marks, index=_marks.index(_cur_mark),
                            key=f"ed_mark_{_act}", label_visibility="collapsed")

                if _HAS_ACE:
                    # auto_update=True so the buffer reaches Python as it is typed; the
                    # cost is one fragment rerun, not a page rebuild, and nothing is
                    # scored until Run.
                    _new = st_ace(value=_buf["text"], language="yaml", theme="github",
                                  wrap=True, show_gutter=True, auto_update=True,
                                  font_size=16, height=780, key=f"ed_ace_{_act}")
                else:
                    st.caption("Install `streamlit-ace` for the richer editor.")
                    _new = st.text_area("ATF", value=_buf["text"], height=780,
                                        key=f"ed_ta_{_act}", label_visibility="collapsed")
                if _new is not None and _new != _buf["text"]:
                    _buf["text"], _buf["stale"] = _new, True

                if _mark != _cur_mark:
                    _buf["text"] = frontmatter_set(_buf["text"], "counting", _mark)
                    _buf["stale"] = True
                    st.rerun(scope="fragment")

                if _close:
                    if _is_dirty(_act):
                        _dlg_close(_act)
                    else:
                        _BUFS.pop(_act, None)
                        st.session_state['ed_active'] = next(iter(_BUFS), None)
                        _ensure_open()
                        st.rerun()
                if _run:
                    _buf["scored"] = score_text(_act, _buf["text"])
                    _buf["stale"] = False
                if _save and _PLACEHOLDER.match(_act):
                    _dlg_name(_act)
                elif _save:
                    _path, _note = save_buffer(_act, _buf["text"])
                    if _path:
                        _buf["saved"] = _buf["text"]
                        st.success(f"Saved to `{_path}` and re-read the corpus.")
                        if _note:
                            st.warning(_note)

        with _rep:
            _rh1, _rh2 = st.columns([1.6, 1.4], vertical_alignment="bottom")
            _rh1.markdown('<div class="setlabel">Report</div>', unsafe_allow_html=True)
            _buf = _BUFS.get(_act) if _act else None
            if not _buf or _buf["scored"] is None:
                with st.container(key="emptystate_report"):
                    st.info("Press ▶ Run to score this buffer.")
            else:
                if _buf["stale"]:
                    st.warning("The text has changed since this was computed.", icon="⚠️")
                _sc = _buf["scored"]
                _tab = standard_table([(_act, _sc['full'], _sc['pres'], _sc['uo'])], "Text")
                if _tab is not None:
                    render_table_with_copy(report_style(_tab), _tab, "ed_report",
                                           control=_rh2)
                _uo = _sc['uo']
                if _uo is not None and not _uo.empty:
                    # Same shape the Text view builds, so both panes can go through
                    # per_omen_figure: keep content-less omens (NaN -> a gap in the
                    # curve, bridged by the grey dotted line) and carry the section
                    # so obverse/reverse boundaries are marked here too.
                    _pts = []
                    for _oid, _g in _sc['full'].groupby('omen_id', sort=False):
                        _b3 = trio(_g, False)
                        _pts.append({"omen": str(_oid), "bin": _b3[0],
                                     "macro": _b3[1], "micro": _b3[2],
                                     "section": (_g['section'].iloc[0]
                                                 if 'section' in _g.columns else "")})
                    if _pts:
                        _pdf = pd.DataFrame(_pts)
                        _pdf['seq'] = range(len(_pdf))
                        st.markdown('<div class="charttitle">LDI per omen</div>',
                                    unsafe_allow_html=True)
                        # A plain radio, not metric_control: that helper splits its
                        # row into columns, which stack into three lines in a column
                        # this narrow. (metric_block is out either way: fragments
                        # cannot nest, and this pane is one.)
                        _emetric = st.radio("metric", ["bin", "macro", "micro"],
                                            horizontal=True, key="ed_curve_metric",
                                            label_visibility="collapsed")
                        # Same engine as the Text view (per_omen_figure): gaps for
                        # content-less omens, obverse/reverse boundary, thinned line
                        # labels. Shorter and with smaller dots, because this pane is
                        # a narrow column; the Editor keeps its own red.
                        _whole = trio(_sc['full'], False)[
                            {"bin": 0, "macro": 1, "micro": 2}[_emetric]]
                        _fig_ed = per_omen_figure(_pdf, _emetric, "#D32F2F",
                                                  whole=_whole, height=300,
                                                  marker_size=7)
                        _fig_ed.update_layout(margin=dict(t=14, r=6, l=6, b=30))
                        st.plotly_chart(_fig_ed, use_container_width=True, key="ed_curve")
                        _scored = int(_pdf[_emetric].notna().sum())
                        st.caption(f"{_scored} scored omens"
                                   + (f", {len(_pdf) - _scored} without scorable content"
                                      if _scored != len(_pdf) else "") + ".")

    @st.fragment
    def _project_pane():
        """The working set as a whole: what is open, where it would be filed, and
        the pooled report once the buffers have been scored."""
        st.markdown('<div class="setlabel">Project</div>', unsafe_allow_html=True)
        if not _BUFS:
            with st.container(key="emptystate_project"):
                st.info("Nothing is open yet. Use the buttons on the left to start "
                        "a text, open one from the corpus, or fetch one from eBL.")
            return

        _c1, _c2, _sp = st.columns([1.1, 1.1, 6.0])
        if _c1.button("▶ Run all", type="primary", use_container_width=True, key="ed_run_all"):
            for _n, _b in _BUFS.items():
                _b["scored"] = score_text(_n, _b["text"])
                _b["stale"] = False
            # no rerun: the tree and the pooled report below are drawn from the
            # buffers we just scored, in this same pass
        if _c2.button("💾 Save all", use_container_width=True, key="ed_save_all"):
            _ok, _notes = 0, []
            for _n, _b in list(_BUFS.items()):
                if not _is_dirty(_n):
                    continue
                _p, _nt = save_buffer(_n, _b["text"])
                if _p:
                    _b["saved"] = _b["text"]
                    _ok += 1
                if _nt:
                    _notes.append(f"**{_n}**: {_nt}")
            st.success(f"Saved {_ok} text(s) into data/ and re-read the corpus.")
            for _nt in _notes:
                st.warning(_nt)

        # The tree: period → discipline → file, read from each buffer's frontmatter,
        # which is what decides where Save files it.
        _tree = {}
        for _n, _b in _BUFS.items():
            _p = frontmatter_get(_b["text"], "period") or "(no period)"
            _g = (frontmatter_get(_b["text"], "discipline")
                  or frontmatter_get(_b["text"], "genre") or "(no discipline)")
            _tree.setdefault(_p, {}).setdefault(_g, []).append(_n)
        _rows = []
        for _p in sorted(_tree):
            st.markdown(f'<div class="projnode">{_esc_html(_p)}</div>', unsafe_allow_html=True)
            for _g in sorted(_tree[_p]):
                st.markdown(f'<div class="projnode projsub">{_esc_html(_g)}</div>',
                            unsafe_allow_html=True)
                for _n in sorted(_tree[_p][_g]):
                    _b = _BUFS[_n]
                    _state = ("unsaved" if _is_dirty(_n)
                              else ("saved" if _b["saved"] is not None else "new"))
                    _mk = frontmatter_get(_b["text"], "counting") or "line"
                    _val = "–"
                    if _b["scored"]:
                        _v = trio(_b["scored"]['full'], False)[0]
                        _val = f"{_v:.3f}" if pd.notna(_v) else "–"
                    st.markdown(
                        f'<div class="projfile"><span class="projname">{_esc_html(_n)}</span>'
                        f'<span class="projmeta">counting {_esc_html(_mk)} · bin {_val} · '
                        f'<span class="proj-{_state}">{_state}</span></span></div>',
                        unsafe_allow_html=True)
                    if _b["scored"]:
                        _sc = _b["scored"]
                        _rows.append((_n, _sc['full'], _sc['pres'], _sc['uo']))

        if _rows and len(_rows) > 1:
            _all_full = pd.concat([r[1] for r in _rows], ignore_index=True)
            _all_pres = [r[2] for r in _rows if r[2] is not None]
            _rows.append(("All open", _all_full,
                          pd.concat(_all_pres, ignore_index=True) if _all_pres else None,
                          _all_full.drop_duplicates(subset=['filename', 'omen_id'])
                          if 'omen_id' in _all_full.columns else None))
            _ptab = standard_table(_rows, "Text")
            if _ptab is not None:
                st.markdown('<div class="charttitle">Pooled report</div>', unsafe_allow_html=True)
                render_table_with_copy(report_style(_ptab), _ptab, "ed_project_report")
        elif _rows:
            _ptab = standard_table(_rows, "Text")
            if _ptab is not None:
                st.markdown('<div class="charttitle">Report</div>', unsafe_allow_html=True)
                render_table_with_copy(report_style(_ptab), _ptab, "ed_project_report")
        else:
            st.caption("Press ▶ Run all to score the open texts.")

    # Tabs on the left, the three sources on the right of the same row.
    _tabs_col, _src_col = st.columns([6.6, 3.4], vertical_alignment="bottom")
    with _src_col:
        with st.container(horizontal=True, horizontal_alignment="right",
                          gap="small", key="edsources"):
            if st.button("New text", key="ed_new"):
                _dlg_new()
            if st.button("Open", key="ed_open"):
                _dlg_open()
            if st.button("Upload", key="ed_upload"):
                _dlg_upload()

    with _tabs_col:
        # Buffers as tabs, with the project beside them. The dot marks unsaved work.
        _tabs = ["◆ Project"] + [("● " if _is_dirty(_n) else "") + _n for _n in _BUFS]
        _keyed = {("◆ Project"): None}
        for _n in _BUFS:
            _keyed[("● " if _is_dirty(_n) else "") + _n] = _n
        _cur_label = ("● " if _is_dirty(_act) else "") + _act if _act else "◆ Project"
        # Opening a buffer from the dialogs, or from the Text view's "Open in
        # Editor", moves ed_active without touching this widget. Its stored label
        # is still a valid option, so it would win the round below and snap the
        # editor back to the previous buffer — leaving Run to score that one
        # instead. Pull the widget across whenever the active buffer changed.
        if st.session_state.get('ed_tab_sync') != _act:
            st.session_state['ed_tab_label'] = _cur_label
            st.session_state['ed_tab_sync'] = _act
        if st.session_state.get('ed_tab_label') not in _tabs:
            st.session_state['ed_tab_label'] = _cur_label if _act else "◆ Project"
        _picked = st.segmented_control("Buffers", _tabs, key="ed_tab_label",
                                       label_visibility="collapsed") or "◆ Project"
        # Two bits of chrome Streamlit cannot express: a double-click on the open
        # tab opens the rename popover, and the editor's drop shadow is removed
        # inside the component's own document.
        components.html(
            """<script>
              const doc = window.parent.document;
              function wire() {
                doc.querySelectorAll('.st-key-ed_tab_label button').forEach(b => {
                  if (b.dataset.dblwired) return;
                  b.dataset.dblwired = '1';
                  b.addEventListener('dblclick', () => {
                    const pen = [...doc.querySelectorAll('button')]
                      .find(x => x.innerText.trim() === '\u270E');
                    if (pen) pen.click();
                  });
                });
                doc.querySelectorAll('iframe').forEach(f => {
                  try {
                    const d = f.contentDocument;
                    if (!d || !d.querySelector('.ace_editor') || d.getElementById('noshadow')) return;
                    const s = d.createElement('style');
                    s.id = 'noshadow';
                    s.textContent =
                      'body{margin:0 !important;}' +
                      '.MuiPaper-elevation1,.MuiPaper-root{box-shadow:none !important;}';
                    d.head.appendChild(s);
                  } catch (e) {}
                });
              }
              wire();
              setTimeout(wire, 400);
              setTimeout(wire, 1200);
            </script>""", height=0)
    # the panes below are page-width, not part of the tab column
    _target = _keyed.get(_picked)
    if _target and _target != _act:
        st.session_state['ed_active'] = _target
        st.rerun()

    if _picked == "◆ Project" or not _act:
        _project_pane()
    else:
        _editor_pane(_act)


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
        "Select a row for the full record, its citations and its eBL link; "
        "**click a museum number** to open that tablet in the Text view "
        "(it takes a moment to load — ← Back to Sources returns here).")

    @st.fragment
    def _catalogue_pane():
        """Controls, table and the selected record. A fragment, so committing a
        search redraws the catalogue and not the page."""
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
                                 on_select="rerun",
                                 selection_mode=["single-row", "single-cell"])

            picked = (event.selection.rows or [None])[0] if hasattr(event, "selection") else None

            # Click-to-open: the grid exposes no double-click, so the museum number
            # itself is the open gesture — clicking it jumps straight to that tablet
            # in the Text view (analysed texts only; the others have no Text page).
            # A click on any other cell selects the row for the record below, just
            # like the row selector does.
            _cells = (list(getattr(event.selection, "cells", []) or [])
                      if hasattr(event, "selection") else [])
            if picked is None and _cells:
                _cr, _cc = _cells[0]
                picked = _cr
                if _cc == "Museum no.":
                    _crow0 = view.iloc[_cr]
                    if _crow0["Status"] == "Analysed":
                        st.session_state['text_back'] = "Sources"
                        st.session_state['goto_nav'] = "LDI"
                        st.session_state['goto_sub'] = "Text"
                        st.session_state['goto_file'] = _crow0["File"]
                        st.rerun()

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
                    st.session_state['text_back'] = "Sources"
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
        _cat_md = os.path.join(_APP_DIR, "docs", "catalogue-of-sources.md")
        _kal5_csv = os.path.join(_APP_DIR, "docs", "kal5-ldi-by-tradition.csv")
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

    _catalogue_pane()

    # st.text_input only commits on Enter or blur, so typing is turned into a
    # debounced Enter: the search feels live, and the fragment keeps the redraw
    # to the table.
    components.html(
        """<script>
          const doc = window.parent.document;
          function wire() {
            const box = doc.querySelector('.st-key-cat_q input');
            if (!box || box.dataset.livewired) return;
            box.dataset.livewired = '1';
            let t = null;
            box.addEventListener('input', () => {
              clearTimeout(t);
              t = setTimeout(() => {
                // keydown alone is ignored; the widget commits on the full
                // key sequence
                for (const type of ['keydown', 'keypress', 'keyup'])
                  box.dispatchEvent(new KeyboardEvent(type, {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                    bubbles: true, cancelable: true}));
              }, 400);
            });
          }
          wire();
          setTimeout(wire, 500);
          setTimeout(wire, 1500);
        </script>""", height=0)

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
            "Parsed live from `references.bib`. Citations of the form *Author YEAR* in "
            "the Sources tab link here; each entry lists the corpus sources that cite it.")
        st.markdown(f'<div class="bibcount">{len(entries)} references</div>',
                    unsafe_allow_html=True)

        if active and any(e["key"] == active for e in entries):
            st.success(f"Jumped to **{active}** (from a citation link). It is highlighted below.")

        # The filter runs in the browser: st.text_input only fires on Enter or
        # blur, and this list is short enough to send whole and hide client-side.
        components.html(
            """
            <style>
              body { margin: 0; font-family: 'Source Sans 3', system-ui, sans-serif; }
              .bibsearch { display: flex; align-items: center; gap: 0.5rem; }
              .bibsearch label { font-size: 0.95rem; color: #3B3B3B; font-weight: 600; }
              .bibsearch input {
                  width: 320px; padding: 0.32rem 0.6rem;
                  font: 0.95rem/1.3 'Source Sans 3', system-ui, sans-serif;
                  color: #1a1a1a; background: #fff;
                  border: 1px solid #d9d4cc; border-radius: 7px; outline: none;
              }
              .bibsearch input:focus { border-color: #D32F2F; box-shadow: 0 0 0 2px rgba(211,47,47,.12); }
            </style>
            <div class="bibsearch">
              <label for="bq">Search:</label>
              <input id="bq" type="search" autocomplete="off"
                     placeholder="author · title · year · key">
            </div>
            <script>
              const box = document.getElementById('bq');
              const doc = window.parent.document;
              function filter() {
                  const q = box.value.trim().toLowerCase();
                  const rows = doc.querySelectorAll('.bibtable tbody tr');
                  let hits = 0;
                  rows.forEach(r => {
                      const on = !q || (r.dataset.blob || '').indexOf(q) !== -1;
                      r.style.display = on ? '' : 'none';
                      if (on) hits++;
                  });
                  const tag = doc.querySelector('.bibcount');
                  if (tag) tag.textContent = q
                      ? hits + ' of ' + rows.length + ' references match'
                      : rows.length + ' references';
              }
              box.addEventListener('input', filter);
              box.addEventListener('search', filter);
            </script>
            """,
            height=46)
        q = ""

        def _sortkey(e):
            sns = _bib_surnames(e["fields"])
            return ((sns[0].lower() if sns else "zzz"), _bib_year(e["fields"]), e["key"])

        def _esc(s):
            return (str(s or "").replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;"))

        shown, rows = 0, []
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
            shown += 1

            # One row, built as HTML: the entry carries italics and a link, and the
            # citing sources are a comma-separated list rather than a block.
            head = f"{_esc(authors) or '&mdash;'}"
            if year:
                head += f" ({_esc(year)})"
            head += f". <em>{_esc(title)}</em>." if title else "."
            if series:
                head += f" {_esc(series)}."
            if imprint:
                head += f" {_esc(imprint)}."
            if link:
                head += f' <a href="{_esc(link)}" target="_blank" rel="noopener">link</a>'
            elif doi:
                head += f' <a href="https://doi.org/{_esc(doi)}" target="_blank" rel="noopener">doi</a>'

            cb = cited_by.get(e["key"]) or []
            cited = ", ".join(f'<a href="?nav=Sources">{_esc(s)}</a>' for s in cb)
            rows.append((e["key"], head, _esc(note), cited,
                         "bibrow bibhit" if e["key"] == active else "bibrow",
                         _esc(blob)))

        if rows:
            _out = ['<table class="bibtable">',
                    '<colgroup><col style="width:9rem"><col><col style="width:22%">',
                    '<col style="width:16%"></colgroup>',
                    '<thead><tr><th>ID</th><th>Entry</th><th>Comment</th>'
                    '<th>Cited by</th></tr></thead><tbody>']
            for _k, _head, _note, _cited, _cls, _blob in rows:
                _out.append(
                    f'<tr class="{_cls}" data-blob="{_blob}">'
                    f'<td class="bibkey" id="ref-{_k}">{_k}</td>'
                    f'<td class="bibentry">{_head}</td>'
                    f'<td class="bibnote">{_note}</td>'
                    f'<td class="bibcited">{_cited}</td></tr>')
            _out.append('</tbody></table>')
            st.markdown("\n".join(_out), unsafe_allow_html=True)

elif st.session_state['annotations']:



    # --- Corpus scope: whose texts the analyses read -------------------------
    # Imports live in their own set (data/_custom), so the published corpus keeps
    # reporting the article's figures whatever the reader adds. This switch says
    # which set the LDI pages score: the published corpus, the reader's own, or
    # the two pooled. It only appears once something has been imported.
    CORPUS_SCOPES = ["Published", "My texts", "Both"]
    _has_custom = bool(st.session_state.get('custom'))
    _scope = st.session_state.get('corpus_scope', "Published")
    if not _has_custom or _scope not in CORPUS_SCOPES:
        _scope = "Published"      # nothing imported: only one set to read

    def scoped_anns(preserved):
        """The token list the analyses run on, for one display mode.

        A set whose preserved-only pass came back empty falls back to its full
        text, as the frames did before the scope existed: build_frames needs a
        non-empty frame to derive its columns from."""
        def _one(full_key, pres_key):
            if not preserved:
                return list(st.session_state.get(full_key) or ())
            return list(st.session_state.get(pres_key)
                        or st.session_state.get(full_key) or ())
        base = _one('annotations', 'annotations_pres')
        mine = _one('custom', 'custom_pres')
        if _scope == "My texts":
            return mine
        if _scope == "Both":
            return base + mine
        return base

    def build_frames(anns, comps, supps=None, helds=None, custs=None):
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
                'comp': _held(comps), 'supp': _held(supps), 'held': _held(helds),
                'cust': _held(custs)}

    # Both display modes, so the report's "restor." column can be filled from the
    # preserved-only slice without reloading.
    # Built once per loaded corpus, not once per rerun. Every interaction — opening
    # a folder in the tree, switching a toggle, changing tab — reruns this script,
    # and build_frames maps the sign tokenizer over ~90k rows and derives the region
    # per row, twice (full text and preserved-only). Rebuilding that on a click cost
    # ~20 s a view; the annotations only change on load/import, so key the cache on
    # their size and reuse the frames until they do.
    # The scope is part of the signature: switching it rebuilds the frames and
    # drops the slice memo and the per-view caches with them.
    _frames_sig = (len(st.session_state['annotations']),
                   len(st.session_state.get('annotations_pres') or ()),
                   len(st.session_state.get('comparanda') or ()),
                   len(st.session_state.get('comparanda_pres') or ()),
                   len(st.session_state.get('supplementary') or ()),
                   len(st.session_state.get('supplementary_pres') or ()),
                   len(st.session_state.get('heldout') or ()),
                   len(st.session_state.get('heldout_pres') or ()),
                   len(st.session_state.get('custom') or ()),
                   len(st.session_state.get('custom_pres') or ()),
                   _scope)
    if st.session_state.get('_frames_sig') != _frames_sig:
        st.session_state['_frames'] = {
            False: build_frames(scoped_anns(False),
                                st.session_state.get('comparanda', []),
                                st.session_state.get('supplementary', []),
                                st.session_state.get('heldout', []),
                                st.session_state.get('custom', [])),
            True:  build_frames(scoped_anns(True),
                                st.session_state.get('comparanda_pres', st.session_state.get('comparanda', [])),
                                st.session_state.get('supplementary_pres', st.session_state.get('supplementary', [])),
                                st.session_state.get('heldout_pres', st.session_state.get('heldout', [])),
                                st.session_state.get('custom_pres', st.session_state.get('custom', []))),
        }
        # Stamp the memo namespace trio()/comp() key on (see _slice_key): df/uo/
        # bframe/gframe are row-subsets of one parent and share a namespace; the
        # comparanda/supplementary/held-out frames have their own row numbering,
        # so each gets its own. Rides through slicing via DataFrame.attrs.
        for _mode, _fset in st.session_state['_frames'].items():
            for _fname, _fval in _fset.items():
                if isinstance(_fval, pd.DataFrame):
                    _ns = 'corpus' if _fname in ('df', 'uo', 'bframe', 'gframe') else _fname
                    _fval.attrs['_memo_ns'] = (_ns, _mode, _frames_sig)
        st.session_state['_slice_memo'] = {}
        st.session_state['_frames_sig'] = _frames_sig
    FRAMES = st.session_state['_frames']

    def pick(preserved):
        """Frame-set (df, uo, bframe, gframe, comp) for a chart's restorations choice."""
        return FRAMES[bool(preserved)]

    def view_cache(key, builder):
        """One view's computed tables and chart frames, kept until the corpus changes.

        The slices and groupbys behind a report table or trend frame come out
        identical on every rerun of a view — only a corpus load/import changes
        them — so each view parks its finished artifacts here, keyed like
        _frames above, and a tab switch stops paying for pandas passes it
        already made."""
        store = st.session_state.setdefault('_view_cache', {})
        if store.get('_sig') != _frames_sig:
            store.clear()
            store['_sig'] = _frames_sig
        if key not in store:
            store[key] = builder()
        return store[key]

    # Defaults = full text; each page/chart rebinds these to its own mode via pick().
    _F = FRAMES[False]
    df, unique_omens_df = _F['df'], _F['uo']
    bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']






    def corpus_report_row():
        """The whole-corpus row, computed once per loaded corpus.

        It is identical for every text and every rerun, but costs five passes over
        ~90k rows — enough to make opening a folder in the tree feel slow."""
        if st.session_state.get('_corpus_row_sig') != _frames_sig:
            st.session_state['_corpus_row'] = report_row(
                FRAMES[False]['df'], FRAMES[True]['df'], FRAMES[False]['uo'])
            st.session_state['_corpus_row_sig'] = _frames_sig
        return st.session_state['_corpus_row']


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
                          "bin": b, "macro": ma, "micro": mi,
                          # which side of the tablet this omen stands on, so the
                          # chart can mark where obverse ends and reverse begins
                          "section": (omen_tokens['section'].iloc[0]
                                      if 'section' in omen_tokens.columns else "")})

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
            def _chart(metric, chart_df=chart_df, period=period, text_df=text_df,
                       key_prefix=key_prefix):
                whole = trio(text_df, mono, nopart)[
                    {"bin": 0, "macro": 1, "micro": 2}[metric]]
                fig_text = per_omen_figure(chart_df, metric,
                                           color_map.get(period, '#1f77b4'),
                                           whole=whole)
                st.plotly_chart(fig_text, use_container_width=True,
                                key=f"{key_prefix}_omen_ldi")
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
        "Compare": "Series Comparison",
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

        # Scope switch — only once the reader has a corpus of their own to
        # choose between. Changing it re-signs the frames, so every table and
        # chart below is rebuilt against the chosen set.
        if _has_custom:
            _n_mine = len({_a['filename'] for _a in st.session_state['custom']})
            _n_pub = len({_a['filename'] for _a in st.session_state['annotations']})
            with st.container(key="scopepick"):
                _sc_kw = ({} if 'corpus_scope' in st.session_state
                          else {'default': "Published"})
                st.segmented_control(
                    "Corpus scope", CORPUS_SCOPES, key='corpus_scope',
                    label_visibility="collapsed", **_sc_kw)
                _scope_says = {
                    "Published": f"the published corpus ({_n_pub} texts)",
                    "My texts": f"your {_n_mine} imported text(s)",
                    "Both": f"the published corpus and yours pooled "
                            f"({_n_pub + _n_mine} texts)",
                }[_scope]
                st.caption(f"Scoring **{_scope_says}**. Imports are kept under "
                           f"`{CUSTOM_DIR}` and never change the published figures.")

        # Texts in the scored set that no chart can place. Read off the frames,
        # so the banner reflects what is loaded now, not what was last imported:
        # fix a text's frontmatter and the banner goes on the next rerun.
        _uo_all = FRAMES[False]['uo']
        _stray = sorted(
            _uo_all[~_uo_all['period'].map(period_is_plottable)]['filename'].unique())
        if _stray:
            _shown = ", ".join(f"`{_s}`" for _s in _stray[:6])
            _more = f" … and {len(_stray) - 6} more" if len(_stray) > 6 else ""
            _b1, _b2 = st.columns([5, 1], vertical_alignment="center")
            _b1.warning(
                f"**{len(_stray)} text(s) have no period the charts can place.** "
                "Their omens count towards the pooled totals but appear in no "
                f"period row, so the columns will not add up: {_shown}{_more}. "
                "Add a `period:` line to the frontmatter.")
            if _b2.button("Open in Editor", key="fix_periods"):
                _opened = [_s for _s in _stray if open_in_editor(_s)]
                st.session_state['needs_period'] = _opened
                st.rerun()

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

        def _build_period_report():
            rows, idx, chart_pts = [], [], []
            # Undated / unmapped texts get a row of their own before the Total, so
            # the period column still sums to it. They have no place on the trend
            # chart, which is exactly what the banner above the table warns about.
            _unplot = [p for p in unique_omens_df['period'].dropna().unique()
                       if not period_is_plottable(p)]
            for period in PERIOD_ORDER + (["Undated"] if _unplot else []) + ["Total"]:
                if period == "Undated":
                    uo = unique_omens_df[unique_omens_df['period'].isin(_unplot)]
                    full = _FULL[_FULL['period'].isin(_unplot)]
                    prs = _PRES[_PRES['period'].isin(_unplot)]
                else:
                    uo = unique_omens_df if period == "Total" else unique_omens_df[unique_omens_df['period'] == period]
                    full = _FULL if period == "Total" else _FULL[_FULL['period'] == period]
                    prs = _PRES if period == "Total" else _PRES[_PRES['period'] == period]
                if uo.empty:
                    continue
                rows.append(report_row(full, prs, uo))
                idx.append("Undated" if period == "Undated" else period_disp(period))
                # the trend chart plots the datable periods only
                if period in PERIOD_ORDER:
                    dd = df[df['period'] == period]
                    b, ma, mi = trio(dd, mono, nopart)   # canonical: the table prices the rest
                    chart_pts.append({'period': period_disp(period), 'bin': b, 'macro': ma, 'micro': mi})
            return rows, idx, chart_pts
        rows, idx, chart_pts = view_cache('overview_period', _build_period_report)

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
                    line=dict(width=3, color=mcol),
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

        def _build_discipline_report():
            _dsl = []
            for _g in sorted(_DFULL['genre'].dropna().unique(),
                             key=lambda x: -len(_DFULL[_DFULL['genre'] == x])):
                _dsl.append((str(_g), _DFULL[_DFULL['genre'] == _g],
                             _DPRES[_DPRES['genre'] == _g], _DUO[_DUO['genre'] == _g]))
            _dsl.append(("Total", _DFULL, _DPRES, _DUO))
            return standard_table(_dsl, "Discipline")
        _dtab = view_cache('overview_discipline', _build_discipline_report)
        if _dtab is not None:
            st.caption(STANDARD_CAPTION + " **Total** pools across disciplines.")
            render_table_with_copy(report_style(_dtab), _dtab, "discipline_ldi")

        if not bframe.empty:
            st.markdown('<div class="charttitle">Pooled LDI per discipline, '
                        'across periods</div>', unsafe_allow_html=True)
            # One pooled trend line per genre, across periods (Old -> Middle -> Neo).
            def _build_genre_trend():
                bf, gf = with_active(bframe, mono), with_active(gframe, mono)
                gpk = ['genre', 'period']
                t_bin = bf.groupby(gpk)['_islog'].mean().rename('bin')
                t_agg = gf.groupby(gpk).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                t_agg['micro'] = t_agg['_nl'] / (t_agg['_nl'] + t_agg['_np']).where((t_agg['_nl'] + t_agg['_np']) > 0)
                t_n = unique_omens_df.groupby(gpk).size().rename('n')
                trend = pd.concat([t_bin, t_agg[['macro', 'micro']], t_n], axis=1).reset_index()
                trend = trend.dropna(subset=['genre', 'period'])
                trend['period'] = pd.Categorical(trend['period'], categories=PERIOD_ORDER, ordered=True)
                return trend.sort_values(['genre', 'period'])
            trend = view_cache('overview_genre_trend', _build_genre_trend)

            def _chart(metric, trend=trend):
                fig_trend = px.line(
                    trend, x='period', y=metric, color='genre', markers=True,
                    category_orders={'period': PERIOD_ORDER},
                    custom_data=['genre', 'n'], line_shape='linear',
                    template="simple_white"
                )
                fig_trend.update_traces(
                    line=dict(width=3), marker=dict(size=11),
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

        def _build_region_report():
            _rsl = []
            for region in REGION_ORDER + ["Total"]:
                uo = unique_omens_df if region == "Total" else unique_omens_df[unique_omens_df['region'] == region]
                if uo.empty:
                    continue
                _rsl.append((region,
                             _RFULL if region == "Total" else _RFULL[_RFULL['region'] == region],
                             _RPRES if region == "Total" else _RPRES[_RPRES['region'] == region],
                             uo))
            return standard_table(_rsl, "Region")
        rtdf = view_cache('region_report', _build_region_report)
        if rtdf is not None:
            rsty = report_style(rtdf)
            render_table_with_copy(rsty, rtdf, "region_ldi")

        st.divider()

        # Region trend — one line per region across periods (does the gap widen over time?).
        st.subheader("Logographic Shift by Region (diachronic trend)")

        if not bframe.empty:
            st.markdown('<div class="charttitle">Pooled LDI per region, '
                        'across periods</div>', unsafe_allow_html=True)
            def _build_region_trend():
                bf, gf = with_active(bframe, mono), with_active(gframe, mono)
                rpk = ['region', 'period']
                r_bin = bf.groupby(rpk)['_islog'].mean().rename('bin')
                r_agg = gf.groupby(rpk).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                r_agg['micro'] = r_agg['_nl'] / (r_agg['_nl'] + r_agg['_np']).where((r_agg['_nl'] + r_agg['_np']) > 0)
                r_n = unique_omens_df.groupby(rpk).size().rename('n')
                rtrend = pd.concat([r_bin, r_agg[['macro', 'micro']], r_n], axis=1).reset_index()
                rtrend = rtrend.dropna(subset=['region', 'period'])
                rtrend['period'] = pd.Categorical(rtrend['period'], categories=PERIOD_ORDER, ordered=True)
                return rtrend.sort_values(['region', 'period'])
            rtrend = view_cache('region_trend', _build_region_trend)

            def _chart(metric, rtrend=rtrend):
                fig_region = px.line(
                    rtrend, x='period', y=metric, color='region', markers=True,
                    category_orders={'period': PERIOD_ORDER, 'region': REGION_ORDER},
                    custom_data=['region', 'n'], line_shape='linear',
                    template="simple_white"
                )
                fig_region.update_traces(
                    line=dict(width=3), marker=dict(size=11),
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

        # The cells carry all three measures, so the matrix cache holds whatever
        # the metric switch above asks for without recomputing.
        def _build_region_matrix_cells():
            cells = []
            for g in genres_present:
                for r in regions_present:
                    sub = df[(df['genre'] == g) & (df['region'] == r)]
                    if sub.empty:
                        continue
                    b, ma, mi = trio(sub, mono, nopart)
                    n = unique_omens_df[(unique_omens_df['genre'] == g)
                                        & (unique_omens_df['region'] == r)].shape[0]
                    cells.append({'genre': GENRE_DISPLAY.get(g, str(g).title()),
                                  'region': r, 'bin': b, 'macro': ma, 'micro': mi, 'n': n})
            return cells
        grx = [{'genre': c['genre'], 'region': c['region'], 'ldi': c[metric], 'n': c['n']}
               for c in view_cache('region_matrix_cells', _build_region_matrix_cells)]
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
            def _build_genre_region_trend():
                bf, gf = with_active(bframe, mono), with_active(gframe, mono)
                grp = ['genre', 'region', 'period']
                gtb = bf.groupby(grp)['_islog'].mean().rename('bin')
                gta = gf.groupby(grp).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                gta['micro'] = gta['_nl'] / (gta['_nl'] + gta['_np']).where((gta['_nl'] + gta['_np']) > 0)
                gtn = unique_omens_df.groupby(grp).size().rename('n')
                gtr = pd.concat([gtb, gta[['macro', 'micro']], gtn], axis=1).reset_index()
                gtr = gtr.dropna(subset=['genre', 'region', 'period'])
                gtr['period'] = pd.Categorical(gtr['period'], categories=PERIOD_ORDER, ordered=True)
                return gtr
            gtr = view_cache('region_genre_trend', _build_genre_region_trend)

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
                        custom_data=['region', 'n'], line_shape='linear',
                        template="simple_white"
                    )
                    fig_g.update_traces(
                        line=dict(width=3), marker=dict(size=11),
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

        avail_genres = [g for g in TOPIC_GENRES if not df[df['genre'] == g].empty]
        if not avail_genres:
            st.info("No texts of a discipline with sub-chapters in the current corpus.")
            EXT = None
        else:
            EXT = st.radio("Discipline", avail_genres, horizontal=True, key="topic_genre")
        _label_fn, TOPIC_ORDER = TOPIC_GENRES.get(EXT, (None, []))

        def _label_col(frame):
            return topic_labels(frame, EXT)

        # Texts flagged `pooled_exclude` (orthographic outliers, e.g. a syllabic Babylonian
        # copy filed under a Neo cell) are dropped from the pooled LDI / counts but still
        # shown independently on the chart.
        def _excl(frame):
            if 'pooled_exclude' in frame.columns:
                return frame['pooled_exclude'].fillna(False).astype(bool)
            return pd.Series(False, index=frame.index)

        def _build_topic_frames():
            ext_df = df[df['genre'] == EXT].copy() if EXT else df.iloc[0:0].copy()
            if ext_df.empty:
                return None
            ext_df['topic_label'] = _label_col(ext_df)
            ext_uo = unique_omens_df[unique_omens_df['genre'] == EXT].copy()
            ext_uo['topic_label'] = _label_col(ext_uo)
            ext_lp = ext_df[ext_df['type'].isin(['logogram', 'phonetic'])]
            return {'ext_df': ext_df, 'ext_uo': ext_uo, 'ext_lp': ext_lp,
                    'ext_uo_pool': ext_uo[~_excl(ext_uo)],
                    'ext_df_pool': ext_df[~_excl(ext_df)],
                    'ext_lp_pool': ext_lp[~_excl(ext_lp)],
                    'ext_lp_excl': ext_lp[_excl(ext_lp)],
                    'periods_present': [p for p in PERIOD_ORDER
                                        if not ext_df[ext_df['period'] == p].empty]}
        _TF = view_cache(('topics_frames', EXT), _build_topic_frames)
        if _TF is None:
            if EXT:
                st.info(f"No {EXT} texts in the current corpus.")
        else:
            ext_df, ext_uo, ext_lp = _TF['ext_df'], _TF['ext_uo'], _TF['ext_lp']
            ext_uo_pool, ext_df_pool = _TF['ext_uo_pool'], _TF['ext_df_pool']
            ext_lp_pool, ext_lp_excl = _TF['ext_lp_pool'], _TF['ext_lp_excl']
            periods_present = _TF['periods_present']
            labels = list(ext_uo['topic_label'].dropna().unique())
            topics_present = sorted(
                labels,
                key=lambda l: (TOPIC_ORDER.index(l) if l in TOPIC_ORDER else len(TOPIC_ORDER), l))

            # Coverage table — omens (texts) per topic × period.
            def _build_topic_coverage():
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
                out = pd.DataFrame(cov_rows, index=topics_present + ["Total"],
                                   columns=[_short(p) for p in periods_present] + ["Total"])
                out.index.name = "Topic"
                return out
            cov_df = view_cache(('topics_cov', EXT), _build_topic_coverage)
            st.caption("**omens (texts)** per topic × period.")
            render_table_with_copy(_section_table_style(cov_df.style), cov_df, "topic_cov")

            st.divider()

            # One chart per topic — each OMEN is a node, in chronological (period) order,
            # coloured by period (mirrors the Genre chart, but at omen level).
            for ti, tlab in enumerate(topics_present):
                def _build_topic_stats(tlab=tlab):
                    tb = with_active(ext_lp_pool[ext_lp_pool['topic_label'] == tlab], mono)
                    if tb.empty:
                        return None
                    okeys = ['period', 'filename', 'omen_id']
                    o_bin = tb.groupby(okeys)['_islog'].mean().rename('bin')
                    o_agg = tb.groupby(okeys).agg(_nl=('_anl', 'sum'), _np=('_anph', 'sum'), macro=('_deg', 'mean'))
                    o_agg['micro'] = o_agg['_nl'] / (o_agg['_nl'] + o_agg['_np']).where((o_agg['_nl'] + o_agg['_np']) > 0)
                    ostats = pd.concat([o_bin, o_agg[['macro', 'micro']]], axis=1).reset_index()
                    ostats[['bin', 'macro', 'micro']] = ostats[['bin', 'macro', 'micro']].fillna(0.0)
                    ostats['period'] = pd.Categorical(ostats['period'], categories=PERIOD_ORDER, ordered=True)
                    ostats = ostats.sort_values(['period', 'filename', 'omen_id'])
                    if ostats.empty:
                        return None
                    ostats['seq_index'] = range(len(ostats))

                    # Three LDI measures for this topic, by period — shown before the chart.
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
                    return {'tb': tb, 'ostats': ostats,
                            'ltdf': standard_table(_tsl, "Period")}
                _TS = view_cache(('topics_stats', EXT, tlab), _build_topic_stats)
                if _TS is None:
                    continue
                tb, ostats, ltdf = _TS['tb'], _TS['ostats'], _TS['ltdf']
                okeys = ['period', 'filename', 'omen_id']
                st.markdown(f"#### {tlab}")
                if ltdf is not None:
                    lsty = report_style(ltdf)
                    render_table_with_copy(lsty, ltdf, f"topic_ldi_{ti}")

                # This topic's own switch, under its title and over its charts.
                st.markdown(f'<div class="charttitle">{tlab} — LDI per omen '
                            f'({len(ostats)} omens)</div>', unsafe_allow_html=True)

                def _chart(metric, ostats=ostats, tlab=tlab, ti=ti, tb=tb):
                    fig = go.Figure()
                    # One line per period segment (its own colour), bridged so there are no gaps.
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
                            line=dict(width=2, color=color_map.get(period, '#444')),
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
                                line=dict(width=2.5, color=color_map.get(period, '#444')),
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

                def _build_genre_stats(genre=genre, g_uo=g_uo):
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
                    if not gstats.empty:
                        gstats['seq_index'] = range(len(gstats))
                    return {'gtdf': gtdf, 'gstats': gstats}
                _GS = view_cache(('discipline', genre), _build_genre_stats)
                gtdf, gstats = _GS['gtdf'], _GS['gstats']
                if gtdf is not None:
                    gtsty = report_style(gtdf)
                    render_table_with_copy(gtsty, gtdf, f"genre_period_{gi}")

                st.markdown(f'<div class="charttitle">{genre} — LDI per text '
                            f'(Old → Neo)</div>', unsafe_allow_html=True)

                if gstats.empty:
                    continue

                def _chart(metric, gstats=gstats, genre=genre):
                    fig_genre = go.Figure()
                    # One connected line, but each period's segment takes that period's colour.
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
                            line=dict(width=2.5, color=color_map.get(period, '#444')),
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

    # --- LDI ▸ Compare (several series, one chart) ---
    if page == "LDI" and ldi_view == "Compare":
        st.caption("Put several series on one chart. A discipline, a sub-chapter, a "
                   "region or a single tablet can be mixed freely, including the "
                   "held-out comparanda and KAL 5 witnesses. A series attested in more "
                   "than one period is drawn as a line; a single tablet is one marker "
                   "at its own period, so a text can be read against the curve it "
                   "belongs to.")

        mono, pres, nopart = False, False, False   # canonical: the report prices the variants
        _F = pick(pres)
        cdf = _F['df']

        # The catalogue of selectable series: label -> (kind, key). Built once per
        # loaded corpus, since labelling every discipline's sub-chapters means a
        # groupby apiece.
        _sig = st.session_state.get('_frames_sig')
        _cached = st.session_state.get('_cmp_cat')
        if not _cached or _cached[0] != _sig:
            _opts = {}
            for _g in sorted(cdf['genre'].dropna().unique()):
                _opts[f"Discipline · {_g}"] = ('genre', _g)
            for _r in REGION_ORDER:
                if (cdf['region'] == _r).any():
                    _opts[f"Region · {_r}"] = ('region', _r)
            for _g in TOPIC_GENRES:
                _gd = cdf[cdf['genre'] == _g]
                for _lab in sorted(set(topic_labels(_gd, _g))):
                    _opts[f"Topic · {_g}: {_lab}"] = ('topic', (_g, _lab))
            for _fn in sorted(cdf['filename'].dropna().unique()):
                _opts[f"Text · {_fn.rsplit('.txt', 1)[0]}"] = ('file', _fn)
            for _lbl, _k in (("Comparandum", 'comp'), ("KAL 5", 'supp'),
                             ("Held out", 'held'), ("My text", 'cust')):
                _h = FRAMES[False].get(_k)
                if _h is not None and not _h.empty:
                    for _fn in sorted(_h['filename'].dropna().unique()):
                        _opts[f"{_lbl} · {_fn.rsplit('.txt', 1)[0]}"] = ('held', (_k, _fn))
            _cached = (_sig, _opts)
            st.session_state['_cmp_cat'] = _cached
        CMP_CAT = _cached[1]

        def _cmp_slice(spec, preserved=False):
            """The token rows behind one catalogue entry."""
            _kind, _key = spec
            _base = FRAMES[True] if preserved else FRAMES[False]
            _d = _base['df']
            if _kind == 'genre':
                return _d[_d['genre'] == _key]
            if _kind == 'region':
                return _d[_d['region'] == _key]
            if _kind == 'topic':
                _g, _lab = _key
                _gd = _d[_d['genre'] == _g]
                if _gd.empty:
                    return _gd
                _labs = pd.Series(topic_labels(_gd, _g), index=_gd.index)
                return _gd[_labs == _lab]
            if _kind == 'file':
                return _d[_d['filename'] == _key]
            if _kind == 'held':
                _k, _fn = _key
                _h = _base.get(_k)
                if _h is None or _h.empty:
                    return _d.iloc[0:0]
                return _h[_h['filename'] == _fn]
            return _d.iloc[0:0]

        # Same width as the tree column in the Text view, so the two pickers in
        # this tab sit on the same measure.
        _psel, _prest = st.columns([2.6, 7.4])
        with _psel:
            picks = st.multiselect(
                "Series", list(CMP_CAT), key="cmp_series",
                help="Start typing to filter: 'lung', 'Extispicy', 'K 2858' …")

        if not picks:
            with st.container(key="emptystate_cmp"):
                st.info("Pick two or more series to build a chart. For example "
                        "*Topic · Extispicy: Lung (ḫašû)* together with the three "
                        "KAL 5 lung models and orientation tablets.")
        else:
            # Sliced once, outside the fragment: the slices do not depend on the
            # measure, so switching bin/macro/micro only redraws.
            _series = [(_n, _cmp_slice(CMP_CAT[_n])) for _n in picks]

            def _build_compare_report():
                _rows = []
                for _n, _full in _series:
                    if _full.empty:
                        continue
                    _rows.append((_n, _full, _cmp_slice(CMP_CAT[_n], preserved=True),
                                  _full.drop_duplicates(subset=['filename', 'omen_id'])))
                return standard_table(_rows, "Series")
            _ctab = view_cache(('compare', tuple(picks)), _build_compare_report)
            if _ctab is not None:
                st.caption(STANDARD_CAPTION)
                render_table_with_copy(report_style(_ctab), _ctab, "compare_report")

            st.markdown('<div class="charttitle">Selected series across the periods</div>',
                        unsafe_allow_html=True)

            def _chart(metric, series=_series):
                _mi = {"bin": 0, "macro": 1, "micro": 2}[metric]
                fig_cmp = go.Figure()
                for _name, _full in series:
                    xs, ys, ns = [], [], []
                    for _p in PERIOD_ORDER:
                        _sl = _full[_full['period'] == _p]
                        if _sl.empty:
                            continue
                        _v = trio(_sl, mono, nopart)[_mi]
                        if pd.isna(_v):
                            continue
                        xs.append(period_disp(_p))
                        ys.append(_v)
                        ns.append(_sl.drop_duplicates(subset=['filename', 'omen_id']).shape[0])
                    if not xs:
                        continue
                    # one period = one tablet or a single-period series: a marker,
                    # since a line through one point says nothing
                    fig_cmp.add_trace(go.Scatter(
                        x=xs, y=ys, customdata=ns, name=_name,
                        mode="lines+markers" if len(xs) > 1 else "markers",
                        line=dict(width=3),
                        marker=dict(size=11, line=dict(width=1, color="white")),
                        hovertemplate=f"<b>{_name}</b><br>%{{x}}<br>"
                                      + metric + " = %{y:.3f}<br>omens = %{customdata}"
                                      "<extra></extra>"))
                fig_cmp.update_layout(
                    margin=dict(t=14),
                    template="simple_white", font_family="Arial",
                    xaxis_title="Period", yaxis_title=f"LDI — {metric}",
                    yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                    xaxis=dict(categoryorder="array",
                               categoryarray=[period_disp(p) for p in PERIOD_ORDER]),
                    height=520, hovermode="closest", legend_title_text="Series")
                st.plotly_chart(fig_cmp, use_container_width=True, key="cmp_chart")

            metric_block("compare", _chart)
            st.caption("Each series is scored at the canonical convention; the report "
                       "above gives what the other conventions are worth to it.")

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
                     "KAL 5": "Supplementary (KAL 5)", "Held out": "Held out"}
        # The reader's own texts get a tab of their own, once there are any.
        if _has_custom:
            _SET_TABS["My texts"] = "My texts"
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

            # The way back to the catalogue, for readers who arrived from there
            # (a museum-number click or the "Open in Text view" button).
            if st.session_state.get('text_back') == "Sources":
                if st.button("← Back to Sources", key="text_back_btn"):
                    st.session_state.pop('text_back', None)
                    st.session_state['goto_nav'] = "Sources"
                    st.rerun()

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
                    with st.container(key="emptystate_text"):
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

                    # The text as a buffer in the Editor tab — editing, running
                    # and saving all live there.
                    if st.button("📝 Open in Editor", key="text_to_editor"):
                        if open_in_editor(selected_file):
                            st.rerun()
                        st.warning("No editable source is loaded for this "
                                   "text in this session.")

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
            elif text_set == "My texts":
                pool, pkey = FRAMES[False]['cust'], 'cust'
                _cap = ("Texts you imported. They are kept under "
                        f"`{CUSTOM_DIR}`, separate from the published corpus, and are "
                        "scored only when the scope switch above the LDI views is set "
                        "to *My texts* or *Both*.")
                empty_msg = "Nothing imported yet — use Upload in the Editor."
            elif text_set == "Held out":
                pool, pkey = FRAMES[False]['held'], 'held'
                _cap = ("Corpus texts held **out** of every count (`exclude: true` — too "
                        "fragmentary to score, or duplicates of counted tablets), loadable here "
                        "for individual inspection. Their LDI is usually dominated by what happens "
                        "to survive — read the per-text note before citing a figure.")
                empty_msg = "No held-out texts found under data/old, data/middle, data/new."
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
                        with st.container(key="emptystate_held"):
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
