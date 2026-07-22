import os
import io
import sys
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
st.set_page_config(
    page_title="Mesopotamian Omen Analyzer",
    page_icon="🏺",
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
        /* "|" separator between the metric radio and the monogram checkbox. */
        div[class*="st-key-"][class*="_mono"] {
            border-left: 2px solid #ddd;
            padding-left: 0.9rem;
        }

        /* --- App header: title + nav tabs on one line, with a shared bottom border --- */
        .st-key-appheader {
            border-bottom: 2px solid #d0d0d0;
            margin-bottom: 1.4rem;
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
            font-size: 0.9rem !important;
            padding: 0.3rem 0.1rem !important;
            margin-bottom: -2px !important;       /* sit on the 2px border */
        }
        [class*="st-key-nav_"] button:hover { color: #111 !important; }
        /* Active tab (rendered as type="primary") */
        [class*="st-key-nav_"] button[kind="primary"],
        [class*="st-key-nav_"] button[data-testid="stBaseButton-primary"] {
            color: #D32F2F !important;
            border-bottom: 3px solid #D32F2F !important;
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
# and ana. Lowercase, so by default they count as syllabic; the monogram toggle
# reclassifies them as logographic. See docs/ldi-sign-level.md.
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
    """Drop content-less omens (see _omen_has_signal) before pooling an LDI."""
    if 'omen_id' not in sub.columns or sub.empty:
        return sub
    return sub[_omen_has_signal(sub)]

def _sign_counts(token):
    """Per-sign (logogram, phonetic) counts for one word token, splitting on '.'/'-'.
    Uppercase sign -> logogram, lowercase -> phonetic; matches compute_ratios."""
    nl = nph = 0
    for s in SIGN_BOUNDARY.split(str(token)):
        if not s:
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
}

# Display names for the (normalized) genre keys, shown in the UI/charts.
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

def chart_controls(key):
    """Per-chart controls: bin macro micro | count ina/ana … | drop restorations —
    the metric radio (label hidden), the monogram checkbox, and the preserved-only
    checkbox, each keyed independently so every chart owns its own choice.
    Returns (metric, monogram, preserved)."""
    c1, c2, c4, c3, _spacer = st.columns([1.5, 2.6, 2.3, 0.4, 3], vertical_alignment="center")
    metric = c1.radio(
        "metric", ["bin", "macro", "micro"], horizontal=True,
        key=f"{key}_metric", label_visibility="collapsed")
    monogram = c2.checkbox("count ina/ana as logographic", key=f"{key}_mono")
    preserved = c4.checkbox(
        "drop restorations [ … ]", key=f"{key}_pres",
        help="Score only signs physically on the tablet — drop the editor's [ … ] "
             "reconstructions. Off = count them (the full edited text).")
    # Always-visible link to the full explanation (no underline).
    c3.markdown(
        '<a href="?nav=Introduction" title="Full explanation on the Introduction tab" '
        'style="text-decoration:none; font-size:1.2rem; color:#1976D2;">ⓘ</a>',
        unsafe_allow_html=True)
    return metric, monogram, preserved

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
    """Render a Styler HTML table, then a dropdown that copies it to the clipboard
    in the chosen format: rich HTML (pastes as a real table into Excel / Word /
    Sheets), Markdown, or tab-separated text. Falls back to plain text if the
    rich-clipboard API is unavailable (e.g. a non-secure context)."""
    table_html = styler.to_html()
    st.markdown(table_html, unsafe_allow_html=True)

    payload_html = json.dumps(table_html)
    payload_tsv = json.dumps(source_df.to_csv(sep='\t'))
    payload_md = json.dumps(_table_to_markdown(source_df))
    label_js = json.dumps(label)
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

def biblio_and_ebl_lines(row):
    """Markdown lines for the bibliography (publication / edition) and an eBL link.
    The link type is inferred: a corpus chapter (its `/api/texts/.../chapters/...` path
    appears in the frontmatter, e.g. EAE 55/57) → a Corpus URL; otherwise the text is a
    fragment → a Library URL from the museum number (the filename). Generated links carry
    a (?) warning since they may not resolve if the text isn't in eBL.
    Returned as a list of lines so the caller can render the whole block at once."""
    lines = []
    bib = [str(row[k]).strip() for k in ("publication", "edition")
           if isinstance(row.get(k), str) and str(row[k]).strip()]
    if bib:
        lines.append("**Bibliography:** " + " · ".join(bib))

    blob = " ".join(str(row.get(k, "")) for k in
                    ("edition", "note", "source_note", "recension", "series", "publication"))
    warn = ('<span title="Auto-generated from the text/museum number using eBL&#39;s standard '
            'URL pattern — it may not resolve if the text is not in eBL." '
            'style="cursor:help; color:#888;">(?)</span>')

    # A real eBL URL written in the frontmatter wins (no warning).
    m_url = re.search(r"https?://(?:www\.)?ebl\.lmu\.de/\S+", blob)
    # A corpus chapter: /api/texts/<genre/cat/idx>/chapters/<stage/name>
    m_corpus = re.search(r"/api/texts/([A-Za-z0-9/]+?)/chapters/([A-Za-z0-9/]+)", blob)
    # An explicit eBL museum number named in the bibliography, e.g. "eBL IM.64183",
    # "eBL fragment BM.33793" — more reliable than the filename, so use it next.
    m_num = re.search(r"\beBL\s+(?:fragment\s+)?([A-Za-z]+\.[0-9][\w.\-]*)", blob)
    stem = str(row.get("filename", "")).rsplit(".txt", 1)[0]

    if m_url:
        lines.append(f"**eBL:** [View on eBL]({m_url.group(0).rstrip('.,;)')})")
    elif m_corpus:
        path = f"{m_corpus.group(1)}/{m_corpus.group(2)}"
        lines.append(f"**eBL:** [Corpus]({EBL_BASE}/corpus/{path}) {warn}")
    elif m_num:
        lines.append(f"**eBL:** [Library]({EBL_BASE}/library/{m_num.group(1)})")
    elif stem:
        lines.append(f"**eBL:** [Library]({EBL_BASE}/library/{stem}) {warn}")
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
    """(folded-surname, year) -> bibkey, for linking free-text 'Author YEAR' cites."""
    idx = {}
    for e in parse_bibtex():
        yr = _bib_year(e["fields"])
        if not yr:
            continue
        raw_sns = _bib_surnames(e["fields"])
        sns = [x for x in (_fold(s) for s in raw_sns) if x]
        forms = set()
        if sns:
            forms.add(sns[0])
            forms.add("".join(sns))
            if len(sns) >= 2:
                forms.add(sns[0] + sns[1])
        # Hyphenated first surname (e.g. "Rochberg-Halton") is often cited by one
        # part only ("Rochberg 1988"); index each component.
        if raw_sns:
            for part in re.split(r"[-–]", raw_sns[0]):
                p = _fold(part)
                if p:
                    forms.add(p)
        for fm in forms:
            idx.setdefault((fm, yr), e["key"])
    return idx

# "Surname YEAR" (allowing up to two extra capitalised words, e.g. "De Zorzi",
# "Wiseman–Black"), used both to linkify citations and to build "Cited by".
_CITE_RE = re.compile(
    r"([A-ZÀ-Þ][A-Za-zÀ-ÿ.'’]+(?:[ –-][A-ZÀ-Þ][A-Za-zÀ-ÿ.'’]+){0,2})\s+(1[5-9]\d\d|20\d\d)")

def _cite_key_for(name, year, idx):
    toks = [t for t in re.split(r"[ –-]+", name) if t]
    cands = []
    if toks:
        cands = [_fold(toks[-1]), _fold("".join(toks)), _fold(toks[0])]
        if len(toks) >= 2:
            cands.append(_fold(toks[0] + toks[1]))
    for c in cands:
        if (c, year) in idx:
            return idx[(c, year)]
    return None

def linkify_citations(text):
    """Wrap 'Author YEAR' citations in the text with in-app links to their entry."""
    if not text:
        return text
    idx = _citation_index()
    def repl(m):
        key = _cite_key_for(m.group(1), m.group(2), idx)
        if not key:
            return m.group(0)
        return (f'<a href="?nav=Bibliography&ref={key}" '
                f'title="{key} — see Bibliography">{m.group(0)}</a>')
    return _CITE_RE.sub(repl, text)

@st.cache_data
def _bib_cited_by():
    """bibkey -> sorted list of source sigla that cite it (from the catalogue)."""
    idx = _citation_index()
    rev = {}
    for r in catalogue_rows():
        sig = r.get("_sig") or r.get("filename", "")
        blob = " ".join(str(r.get(k, "")) for k in
                        ("publication", "edition", "source", "source_note",
                         "recension", "note", "_reason"))
        seen = set()
        for m in _CITE_RE.finditer(blob):
            key = _cite_key_for(m.group(1), m.group(2), idx)
            if key and key not in seen:
                seen.add(key)
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
    "prayer":             "Other genres (comparanda)",
    "incantation":        "Other genres (comparanda)",
}
CAT_DISCIPLINE_ORDER = [
    "Celestial / Astrological (Enūma Anu Enlil)", "Terrestrial (Šumma Ālu)",
    "Teratological (Šumma Izbu)", "Extispicy (bārûtu)", "Diagnostic / Medical (Sakikkû)",
    "Extispicy models & orientation texts", "Other genres (comparanda)", "Unspecified",
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
            except yaml.YAMLError:
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
            rows.append(fm)
    return rows

def _cat_cell(s):
    return (str(s) if s is not None else "").replace("|", "/").replace("\n", " ").strip() or "—"

def _cat_ebl_cell(row):
    """Just the eBL link markdown for a catalogue row (drops the '(?)' warn span)."""
    for ln in biblio_and_ebl_lines(row):
        if ln.startswith("**eBL:**"):
            link = ln[len("**eBL:**"):].strip()
            return re.sub(r'\s*<span[^>]*>.*?</span>', '', link) or "—"
    return "—"

def _cat_pub(row):
    for k in ("publication", "edition", "source"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

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

# Two-line display labels for charts (the long Neo label is otherwise clipped).
PERIOD_DISPLAY = {
    "Neo-Babylonian/Assyrian + Late Babylonian": "Neo-Babylonian/Assyrian +<br>Late Babylonian",
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

def line_ldi(text, monogram=False, preserved=False):
    """Measure one input line/omen. Returns (bin, macro, micro, html, words, nl, nph).

    Same rules as the corpus: determinatives excluded, omen particles (DIŠ/…) and
    number-logograms (15/150/30) counted, ina/ana optionally logographic, and
    restorations '[ … ]' optionally dropped. `html` is the colour-coded line."""
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
    def is_mono(a):
        return monogram and a['token'] in MONOGRAM_PARTICLES and a['type'] == 'phonetic'
    binvals = [1 if (a['type'] == 'logogram' or is_mono(a)) else 0 for a in lp]
    binv = sum(binvals) / len(binvals) if binvals else float('nan')
    nl = nph = 0
    degs = []
    for a in lp:
        x, y = _sign_counts(a['token'])
        if is_mono(a):
            x += 1; y -= 1
        nl += x; nph += y
        if x + y > 0:
            degs.append(x / (x + y))
    micro = nl / (nl + nph) if (nl + nph) > 0 else float('nan')
    macro = sum(degs) / len(degs) if degs else float('nan')
    return binv, macro, micro, html, len(lp), nl, nph

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

                    # Skip documented comparanda / excluded texts (mirror compute_ratios),
                    # unless the caller explicitly wants them (comparanda tab).
                    if metadata.get("exclude") and not include_excluded:
                        continue

                    # Parse Body
                    current_section = "Unspecified"
                    current_omen_id = "Unknown"
                    
                    lines = body.splitlines()
                    
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
                period, genre = fm.get('period', period), fm.get('genre', genre)
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
NAV = ["Global", "Genre", "Region", "Topics", "Text", "Sources", "Bibliography", "Tools"]
_PAGES = ["Introduction"] + NAV

# In-app links (e.g. "?nav=Introduction" inside markdown/tables) navigate here.
# A "&ref=<bibkey>" (from a linkified citation) opens the Bibliography on that entry.
_qp_nav = st.query_params.get("nav")
_qp_ref = st.query_params.get("ref")
if _qp_nav in _PAGES:
    st.session_state['page'] = _qp_nav
if _qp_ref:
    st.session_state['bib_ref'] = _qp_ref
    if _qp_nav not in _PAGES:
        st.session_state['page'] = "Bibliography"
if _qp_nav is not None or _qp_ref is not None:
    st.query_params.clear()

# A Genre-node click parks a navigation request here; apply it before the nav renders.
if 'goto_nav' in st.session_state:
    st.session_state['page'] = st.session_state.pop('goto_nav')
st.session_state.setdefault('page', "Introduction")

def _nav_to(p):
    st.session_state['page'] = p

with st.container(key="appheader"):
    h_title, h_nav = st.columns([7, 5], vertical_alignment="bottom")
    with h_title:
        st.button("Mesopotamian Omen Diachronic Analyzer", key="home_btn",
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
        "It measures the **Logographic Density Index (LDI)** of cuneiform omen texts — the "
        "proportion of each omen written with logograms rather than syllabically — and tracks "
        "how it shifts across the Old, Middle, and Neo periods.\n\n"
        "**How to use it**\n\n"
        "- **Global** — the diachronic trend: pooled LDI per genre across the three periods.\n"
        "- **Genre** — one node per text; click a node to open that tablet in the Text view.\n"
        "- **Text** — a single tablet, colour-coded sign by sign, with per-line and whole-text LDI.\n"
        "- **Comparanda** — non-Akkadian parallels kept out of the main corpus.\n\n"
        "Each chart has its own **bin / macro / micro** switch; omen particles (DIŠ, BE, …) are "
        "always counted as logograms."
    )

    st.divider()
    st.markdown("#### The three LDI measures")
    st.markdown(
        "The same text can be scored three ways, from the most generous to the strictest. "
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
        "Same text, three numbers: **bin ≥ macro ≥ micro** here because bin rewards the mixed word "
        "`LUGAL-um` in full, macro splits it in half, and micro counts each of its signs separately. "
        "Comparing the three is a quick read on *how* a text is logographic — whole-word substitution "
        "versus dense sign-by-sign writing."
    )

    st.divider()
    st.markdown("#### The ina / ana monogram toggle")
    st.markdown(
        "Two very common function words sit on the border between syllabic and logographic writing: "
        "the prepositions **ina** “in/on” and **ana** “to/for”. *ina* is routinely written with the "
        "single sign **AŠ**, and *ana* likewise as a one-sign unit — a **monogram**: one sign standing "
        "for a whole word. They look syllabic (lowercase in transliteration), so **by default the "
        "analyzer counts them as syllabic**.\n\n"
        "Because they recur constantly, they can noticeably move a score. Each chart therefore has a "
        "**“count ina/ana as logographic”** toggle: turn it on to treat these monograms as logograms "
        "instead. It is offered as an explicit variant rather than baked in, so you can see how much of "
        "a text's logographic density rests on these two high-frequency monograms. (In the corpus the "
        "effect is real but modest — e.g. a heavily *ina*-laden Middle-Assyrian eclipse tablet rises "
        "from bin ≈ 0.71 to ≈ 0.82 when the toggle is on.)"
    )

elif page == "Tools":
    # --- Measure a single line/omen ---
    st.subheader("Measure a line")
    st.caption("Paste one transliterated line or omen (eBL-ATF: logograms UPPERCASE, "
               "syllabic lowercase, `{det}` determinatives, `[ … ]` restorations). Its LDI "
               "is computed live with the same tokenizer as the corpus.")
    mc1, mc2, _ = st.columns([2.4, 2.4, 4], vertical_alignment="center")
    m_mono = mc1.checkbox("count ina/ana as logographic", key="measure_mono")
    m_pres = mc2.checkbox("drop restorations [ … ]", key="measure_pres")
    line_in = st.text_area("Line / omen", key="measure_line", height=80,
                           label_visibility="collapsed",
                           placeholder="DIŠ ina {iti}BÁR AN.MI GAR-ma DINGIR ina KAN₅-šú …")
    if line_in.strip():
        b, ma, mi, html, nwords, nl, nph = line_ldi(line_in, m_mono, m_pres)
        st.markdown(LEGEND_HTML, unsafe_allow_html=True)
        st.markdown(f'<div class="omen-line">{html}</div>', unsafe_allow_html=True)
        _f = lambda v: f"{v:.3f}" if pd.notna(v) else "–"
        d1, d2, d3 = st.columns(3)
        d1.metric("bin", _f(b)); d2.metric("macro", _f(ma)); d3.metric("micro", _f(mi))
        st.caption(f"**{nwords}** scored words · **{nl}** logographic signs · **{nph}** syllabic "
                   "signs (determinatives excluded). bin = logographic words ÷ words; "
                   "micro = logographic signs ÷ signs; macro = mean per-word fraction.")
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

    # --- Online import from eBL (needs network) ---
    if _OFFLINE:
        st.markdown("#### Fetch from eBL")
        st.info("Online import from the eBL API isn't available in the offline desktop "
                "build. Paste or upload your eBL-ATF transliteration below instead.")
    else:
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
        "genre: extispicy          # astrology | diagnostic | extispicy | izbu | terrestrial\n"
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
    # --- Catalogue of Sources: live, from every text's YAML frontmatter ---
    rows = catalogue_rows()
    used = [r for r in rows if not r["_excluded"]]
    supp = [r for r in rows if r["_supplementary"]]
    excl = [r for r in rows if r["_excluded"] and not r["_supplementary"]]

    st.subheader("Catalogue of Sources")
    st.caption(f"Every manuscript in the corpus ({len(rows)}: {len(used)} analysed, "
               f"{len(supp)} supplementary, {len(excl)} excluded), grouped by discipline and period, "
               "straight from the "
               "text frontmatter. The Publication / edition column reproduces the recorded "
               "publication and excavation numbers; the eBL column links to the online edition "
               "where one is recorded or can be inferred from the museum number.")

    c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
    q = c1.text_input("Search (siglum · publication · provenance)", key="cat_q").strip().lower()
    show_excl = c2.checkbox("Include excluded sources", value=True, key="cat_excl")
    if c3.button("↻ Refresh", key="cat_refresh", help="Re-read the corpus from disk"):
        catalogue_rows.clear()
        st.rerun()

    def _match(r):
        if not q:
            return True
        blob = " ".join(str(r.get(k, "")) for k in
                        ("_sig", "publication", "edition", "source", "provenance", "genre")).lower()
        return q in blob

    pkey = lambda r: (CAT_PERIOD_ORDER.index(r["_period"]) if r["_period"] in CAT_PERIOD_ORDER
                      else 99, r["_sig"].lower())
    dkey = lambda d: CAT_DISCIPLINE_ORDER.index(d) if d in CAT_DISCIPLINE_ORDER else 99

    def _section(title, data, with_reason=False):
        data = [r for r in data if _match(r)]
        st.markdown(f"### {title} ({len(data)})")
        if not data:
            st.caption("No sources match the current search.")
            return
        byd = {}
        for r in data:
            byd.setdefault(r["_discipline"], []).append(r)
        for d in sorted(byd, key=dkey):
            st.markdown(f"#### {d}")
            byp = {}
            for r in byd[d]:
                byp.setdefault(r["_period"], []).append(r)
            for per in sorted(byp, key=lambda x: CAT_PERIOD_ORDER.index(x)
                              if x in CAT_PERIOD_ORDER else 99):
                if with_reason:
                    head = ("| Museum no. / siglum | Period | Publication / edition | eBL "
                            "| Reason for exclusion |\n|---|---|---|---|---|")
                    body = "\n".join(
                        f"| {_cat_cell(r['_sig'])} | {_cat_cell(r['_period'])} "
                        f"| {linkify_citations(_cat_cell(_cat_pub(r)))} | {_cat_ebl_cell(r)} "
                        f"| {linkify_citations(_cat_cell(r['_reason']))} |"
                        for r in sorted(byp[per], key=pkey))
                else:
                    st.markdown(f"**{per}**  ({len(byp[per])})")
                    head = ("| Museum no. / siglum | Publication / edition | Provenance | eBL "
                            "|\n|---|---|---|---|")
                    body = "\n".join(
                        f"| {_cat_cell(r['_sig'])} | {linkify_citations(_cat_cell(_cat_pub(r)))} "
                        f"| {_cat_cell(r.get('provenance'))} | {_cat_ebl_cell(r)} |"
                        for r in sorted(byp[per], key=pkey))
                st.markdown(head + "\n" + body, unsafe_allow_html=True)

    _section("Part 1 — Sources analysed", used)
    if supp:
        st.divider()
        st.caption("Supplementary sources are held out of the main LDI but digitized and browsable "
                   "here — e.g. the further KAL 5 extispicy witnesses (Heeßel 2012).")
        _section("Part 2 — Supplementary sources", supp)
    if show_excl:
        st.divider()
        _section("Part 3 — Excluded sources", excl, with_reason=True)

    # --- Supplementary data (downloads) ---
    _cat_md = os.path.join("docs", "catalogue-of-sources.md")
    _kal5_csv = os.path.join("docs", "kal5-ldi-by-tradition.csv")
    if os.path.exists(_cat_md) or os.path.exists(_kal5_csv):
        st.divider()
        st.markdown("#### Supplementary data")
        d1, d2 = st.columns(2)
        if os.path.exists(_cat_md):
            d1.download_button("⬇ Catalogue of Sources (Markdown)",
                               data=open(_cat_md, encoding="utf-8").read(),
                               file_name="catalogue-of-sources.md", mime="text/markdown",
                               key="cat_dl", use_container_width=True)
        if os.path.exists(_kal5_csv):
            d2.download_button("⬇ KAL 5 per-tablet LDI (CSV)",
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
        return frame

    def with_active(frame, monogram):
        """Add the monogram-dependent active columns (_anl/_anph/_islog/_deg) for the
        given toggle, so each chart can recompute them with its own monogram choice."""
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

    # Both display modes, so each chart's "drop restorations" toggle switches
    # independently between them without reloading.
    FRAMES = {
        False: build_frames(st.session_state['annotations'],
                            st.session_state.get('comparanda', []),
                            st.session_state.get('supplementary', [])),
        True:  build_frames(st.session_state.get('annotations_pres', st.session_state['annotations']),
                            st.session_state.get('comparanda_pres', st.session_state.get('comparanda', [])),
                            st.session_state.get('supplementary_pres', st.session_state.get('supplementary', []))),
    }

    def pick(preserved):
        """Frame-set (df, uo, bframe, gframe, comp) for a chart's restorations choice."""
        return FRAMES[bool(preserved)]

    # Defaults = full text; each page/chart rebinds these to its own mode via pick().
    _F = FRAMES[False]
    df, unique_omens_df = _F['df'], _F['uo']
    bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

    # (bin, macro, micro) for any slice, for a given monogram setting. Omen particles
    # (DIŠ, BE, …) are logograms and are always counted as such — no exclusion path.
    def trio(sub, monogram):
        sub = _drop_contentless(sub)   # lone-DIŠ / all-broken omens carry no signal
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

    def _fmt(v):
        return f"{v:.3f}" if pd.notna(v) else "–"

    def render_text_block(text_df, text_df_pres, period, title, key_prefix):
        """Shared per-text view: colour legend, whole-text LDI (all three metrics),
        the colour-coded omen lines with per-line LDI, and a per-omen LDI chart.
        Used by both the Text and Comparanda tabs. Pass the full and preserved-only
        slices of the same text; the chart's 'drop restorations' toggle picks one."""
        # Per-view controls (metric drives the chart; monogram + restorations drive LDI).
        metric, mono, pres = chart_controls(key_prefix)
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
            b, ma, mi = trio(omen_tokens, mono)
            omens.append({"omen": str(oid), "html": " ".join(html_parts),
                          "bin": b, "macro": ma, "micro": mi})

        # 1) Graphic first — per-omen LDI chart (Genre-tab spline+marker style).
        if omens:
            st.divider()
            st.markdown("#### LDI per omen")
            chart_df = pd.DataFrame(omens)
            chart_df['seq'] = range(len(chart_df))
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
            whole = trio(text_df, mono)[{"bin": 0, "macro": 1, "micro": 2}[metric]]
            fig_text.add_annotation(
                x=(chart_df['seq'].min() + chart_df['seq'].max()) / 2, y=1.02,
                xref='x', yref='y',
                text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                showarrow=False, yanchor='bottom', align='center', font=dict(size=11, color=col),
            )
            show_ticks = len(chart_df) <= 40
            fig_text.update_layout(
                title=f"{title} — {metric} LDI per omen",
                template="simple_white", font_family="Arial",
                xaxis_title="Omen (in text order)", yaxis_title=f"LDI — {metric}",
                yaxis=dict(range=[-0.05, 1.30], tickmode='array',
                           tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
                xaxis=dict(tickmode='array', tickvals=chart_df['seq'], ticktext=chart_df['omen'])
                      if show_ticks else dict(showticklabels=False),
                height=480, hovermode="closest"
            )
            st.plotly_chart(fig_text, use_container_width=True, key=f"{key_prefix}_omen_ldi")

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
    # --- PAGE 1: Global ---
    if page == "Global":
        st.subheader("Global Analysis")

        # Page-level controls drive both the LDI-by-Period table and the trend chart.
        metric, mono, pres = chart_controls("global")
        _F = pick(pres)
        df, unique_omens_df = _F['df'], _F['uo']
        bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

        # LDI by Period — texts · omens · bin · macro · micro (same styling as the
        # Genre table: shaded LDI columns, left-aligned, Period in the first column).
        st.markdown("#### LDI by Period")
        st.caption("**texts · omens · bin · macro · micro** (the three LDI columns are shaded). "
                   "**Total** pools across periods.")

        def _f(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        rows, idx, chart_pts = [], [], []
        for period in PERIOD_ORDER + ["Total"]:
            uo = unique_omens_df if period == "Total" else unique_omens_df[unique_omens_df['period'] == period]
            dd = df if period == "Total" else df[df['period'] == period]
            if uo.empty:
                continue
            b, ma, mi = trio(dd, mono)
            rows.append([str(uo['filename'].nunique()), str(len(uo)), _f(b), _f(ma), _f(mi)])
            idx.append(period)
            if period != "Total":   # the trend chart plots periods only, not the pooled Total
                chart_pts.append({'period': period, 'bin': b, 'macro': ma, 'micro': mi})

        if rows:
            ptdf = pd.DataFrame(rows, index=idx,
                                columns=["texts", "omens", "bin", "macro", "micro"])
            ptdf.index.name = "Period"
            psty = (ptdf.style
                    .set_properties(subset=["bin", "macro", "micro"],
                                    **{'background-color': '#f2f2f2'})
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
            render_table_with_copy(psty, ptdf, "period_ldi")

        # All three LDI measures on one chart, across the broad periods (Total excluded).
        if chart_pts:
            cdf = pd.DataFrame(chart_pts)
            st.markdown("#### Diachronic LDI — bin · macro · micro")
            st.caption("All three measures on one chart across periods (the pooled **Total** "
                       "is omitted). The monogram toggle above applies.")
            fig_period = go.Figure()
            for m_name, mcol in [("bin", "#1f77b4"), ("macro", "#ff7f0e"), ("micro", "#2ca02c")]:
                fig_period.add_trace(go.Scatter(
                    x=cdf['period'], y=cdf[m_name], mode="lines+markers", name=m_name,
                    line=dict(width=3, color=mcol, shape="spline", smoothing=1.3),
                    marker=dict(size=10),
                    hovertemplate=f"<b>{m_name}</b><br>%{{x}}<br>LDI = %{{y:.2f}}<extra></extra>"))
            fig_period.update_layout(
                template="simple_white", font_family="Arial",
                xaxis_title="Period", yaxis_title="LDI",
                yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                height=460, hovermode="x unified", legend_title_text="Measure")
            st.plotly_chart(fig_period, use_container_width=True, key="period_trio")

        st.divider()

        # Global Chart — one trend line per genre across periods
        st.subheader("Logographic Shift by Genre (diachronic trend)")

        if not bframe.empty:
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

            fig_trend = px.line(
                trend, x='period', y=metric, color='genre', markers=True,
                category_orders={'period': PERIOD_ORDER},
                custom_data=['genre', 'n'], line_shape='spline',
                title=f"Logographic Shift by Genre — pooled {metric} LDI across periods",
                template="simple_white"
            )
            fig_trend.update_traces(
                line=dict(width=3, shape='spline', smoothing=1.0), marker=dict(size=11),
                hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>"
                              + metric + " = %{y:.3f}<br>omens = %{customdata[1]}<extra></extra>"
            )
            fig_trend.update_layout(
                font_family="Arial", xaxis_title="Period",
                yaxis_title=f"LDI — {metric}",
                yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                height=780,
                legend_title_text="Genre", hovermode="closest"
            )
            # Two-line tick labels so the long Neo period isn't clipped.
            fig_trend.update_xaxes(tickmode='array', tickvals=PERIOD_ORDER,
                                   ticktext=[period_disp(p) for p in PERIOD_ORDER])
            st.plotly_chart(fig_trend, use_container_width=True, key="genre_trend")
            st.caption(f"Each line = one genre; y = pooled **{metric}** LDI per period "
                       "(hover for omen counts). Switch the metric or monogram handling with the controls above.")

    # --- PAGE: Region (find-spot: Babylonia / Assyria / Periphery) ---
    if page == "Region":
        st.subheader("Regional Analysis (by find-spot)")
        st.caption("Texts grouped by where the manuscript was excavated — **Babylonia** "
                   "(southern heartland), **Assyria** (northern heartland), **Periphery** "
                   "(outside Mesopotamia: Ḫattuša, Emar, Susa). **Unassigned** = unknown "
                   "provenance or multi-site canonical composites, which belong to no single "
                   "city. This isolates how much of the logographic shift is *regional* rather "
                   "than diachronic — i.e. whether the LDI holds across Babylonia, Assyria and "
                   "the periphery, or splits between them.")

        metric, mono, pres = chart_controls("region")
        _F = pick(pres)
        df, unique_omens_df = _F['df'], _F['uo']
        bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

        # LDI by Region — texts · omens · bin · macro · micro (pooled across periods).
        st.markdown("#### LDI by Region")
        st.caption("**texts · omens · bin · macro · micro** (the three LDI columns are shaded). "
                   "**Total** pools across regions.")

        def _fr(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        rrows, ridx = [], []
        for region in REGION_ORDER + ["Total"]:
            uo = unique_omens_df if region == "Total" else unique_omens_df[unique_omens_df['region'] == region]
            dd = df if region == "Total" else df[df['region'] == region]
            if uo.empty:
                continue
            b, ma, mi = trio(dd, mono)
            rrows.append([str(uo['filename'].nunique()), str(len(uo)), _fr(b), _fr(ma), _fr(mi)])
            ridx.append(region)

        if rrows:
            rtdf = pd.DataFrame(rrows, index=ridx,
                                columns=["texts", "omens", "bin", "macro", "micro"])
            rtdf.index.name = "Region"
            rsty = (rtdf.style
                    .set_properties(subset=["bin", "macro", "micro"],
                                    **{'background-color': '#f2f2f2'})
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
            render_table_with_copy(rsty, rtdf, "region_ldi")

        st.divider()

        # Region trend — one line per region across periods (does the gap widen over time?).
        st.subheader("Logographic Shift by Region (diachronic trend)")

        if not bframe.empty:
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

            fig_region = px.line(
                rtrend, x='period', y=metric, color='region', markers=True,
                category_orders={'period': PERIOD_ORDER, 'region': REGION_ORDER},
                custom_data=['region', 'n'], line_shape='spline',
                title=f"Logographic Shift by Region — pooled {metric} LDI across periods",
                template="simple_white"
            )
            fig_region.update_traces(
                line=dict(width=3, shape='spline', smoothing=1.0), marker=dict(size=11),
                hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>"
                              + metric + " = %{y:.3f}<br>omens = %{customdata[1]}<extra></extra>"
            )
            fig_region.update_layout(
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

        st.divider()

        # Genre × Region — controls for genre mix: does each region's LDI hold within a
        # genre, or is the regional gap just an artefact of which genres each region has?
        st.subheader("LDI by Genre × Region")
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
                b, ma, mi = trio(sub, mono)
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
            ptbl.index.name = "Genre"
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
                fig_g = px.line(
                    sub, x='period', y=metric, color='region', markers=True,
                    category_orders={'period': PERIOD_ORDER, 'region': regions_present},
                    custom_data=['region', 'n'], line_shape='spline',
                    title=f"{disp} — {metric} LDI by region across periods",
                    template="simple_white"
                )
                fig_g.update_traces(
                    line=dict(width=3, shape='spline', smoothing=1.0), marker=dict(size=11),
                    hovertemplate="<b>%{customdata[0]}</b><br>%{x}<br>"
                                  + metric + " = %{y:.3f}<br>omens = %{customdata[1]}<extra></extra>")
                fig_g.update_layout(
                    font_family="Arial", xaxis_title="Period",
                    yaxis_title=f"LDI — {metric}",
                    yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                    height=420, legend_title_text="Region", hovermode="closest")
                fig_g.update_xaxes(tickmode='array', tickvals=PERIOD_ORDER,
                                   ticktext=[period_disp(p) for p in PERIOD_ORDER])
                st.plotly_chart(fig_g, use_container_width=True, key=f"region_genre_{g}")

    # --- PAGE: Topics (intra-genre sub-chapters) ---
    if page == "Topics":
        st.subheader("Topic Analysis")
        st.caption("Omens split by **sub-chapter / subject** within a genre — extispicy by liver "
                   "region & lung (bārûtu chapters), astrology by celestial body & phenomenon "
                   "(lunar eclipse, lunar other, solar, stellar/planetary). Pick a genre below; "
                   "one chart per topic, each omen a node across the periods.")

        metric, mono, pres = chart_controls("topics")
        _F = pick(pres)
        df, unique_omens_df = _F['df'], _F['uo']
        bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

        SHORT_PERIOD = {
            "Old Babylonian": "Old Bab.",
            "Middle Babylonian/Assyrian": "Middle Bab./Assyrian",
            "Neo-Babylonian/Assyrian + Late Babylonian": "Neo-Bab./Assyrian + LB",
        }
        def _short(p):
            return SHORT_PERIOD.get(p, p)

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

        # --- Per-genre topic labelling -------------------------------------------------
        # Extispicy: topic/feature come from the folder path (extispicy/<topic>/<feature>).
        EXT_FEATURE = {
            "bab ekallim": "bāb ekallim", "martu": "martu", "naplastu": "naplastu",
            "padanu": "padānu", "pu": "pû", "qerbu": "qerbu",
        }
        def _ext_label(topic, feature):
            t = topic.strip().lower() if isinstance(topic, str) else ""
            f = feature.strip().lower() if isinstance(feature, str) else ""
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
        def _astro_label(topic, feature):
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

        TOPIC_GENRES = {
            "Extispicy": (_ext_label, EXT_ORDER),
            "Astrological Omens": (_astro_label, ASTRO_ORDER),
        }
        avail_genres = [g for g in TOPIC_GENRES if not df[df['genre'] == g].empty]
        if not avail_genres:
            st.info("No extispicy or astrology texts in the current corpus.")
            EXT = None
        else:
            EXT = st.radio("Genre", avail_genres, horizontal=True, key="topic_genre")
        _label_fn, TOPIC_ORDER = TOPIC_GENRES.get(EXT, (None, []))

        def _label_col(frame):
            tcol = frame['topic'] if 'topic' in frame.columns else pd.Series(index=frame.index, dtype=object)
            fcol = frame['feature'] if 'feature' in frame.columns else pd.Series(index=frame.index, dtype=object)
            return [_label_fn(a, b) for a, b in zip(tcol, fcol)]

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
                lr_rows, lr_idx = [], []
                for p in PERIOD_ORDER + ["Total"]:
                    tuo = ext_uo_pool[ext_uo_pool['topic_label'] == tlab]
                    tuo = tuo if p == "Total" else tuo[tuo['period'] == p]
                    if tuo.empty:
                        continue
                    tdd = ext_df_pool[ext_df_pool['topic_label'] == tlab]
                    tdd = tdd if p == "Total" else tdd[tdd['period'] == p]
                    b3, ma3, mi3 = trio(tdd, mono)
                    lr_rows.append([str(tuo['filename'].nunique()), str(len(tuo)),
                                    _f(b3), _f(ma3), _f(mi3)])
                    lr_idx.append(p)
                # Excluded texts get their own independent row (own LDI; not in the pooled rows).
                ex_tu_all = ext_uo[ext_uo['topic_label'] == tlab]
                ex_tu_all = ex_tu_all[_excl(ex_tu_all)]
                for fn in sorted(ex_tu_all['filename'].unique()):
                    ftu = ex_tu_all[ex_tu_all['filename'] == fn]
                    ftd = ext_df[(ext_df['topic_label'] == tlab) & (ext_df['filename'] == fn)]
                    b3, ma3, mi3 = trio(ftd, mono)
                    lr_rows.append(["1", str(len(ftu)), _f(b3), _f(ma3), _f(mi3)])
                    lr_idx.append(f"{fn} (excl.)")
                if lr_rows:
                    ltdf = pd.DataFrame(lr_rows, index=lr_idx,
                                        columns=["texts", "omens", "bin", "macro", "micro"])
                    ltdf.index.name = "Period"
                    lsty = (ltdf.style
                            .set_properties(subset=["bin", "macro", "micro"],
                                            **{'background-color': '#f2f2f2'})
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
                    render_table_with_copy(lsty, ltdf, f"topic_ldi_{ti}")

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
                        hovertemplate="<b>omen %{customdata[0]}</b> · %{customdata[1]}<br>" + period + "<br>"
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
                    whole = trio(ext_df_pool[(ext_df_pool['topic_label'] == tlab) & (ext_df_pool['period'] == period)], mono)[midx]
                    fig.add_annotation(
                        x=(x0 + x1) / 2, y=1.02, xref='x', yref='y',
                        text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                        showarrow=False, yanchor='bottom', align='center', font=dict(size=10, color=col))

                fig.update_layout(
                    title=f"{tlab} — {metric} LDI per omen ({len(ostats)} omens)",
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
                            hovertemplate="<b>%{customdata[0]}</b><br>" + period + "<br>"
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
                        whole = trio(ext_df_pool[(ext_df_pool['topic_label'] == tlab) & (ext_df_pool['period'] == period)], mono)[midx]
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
                    st.plotly_chart(figt, use_container_width=True, key=f"topic_text_chart_{ti}")

    # --- PAGE 2: Genre ---
    if page == "Genre":
        st.subheader("Genre-Specific Analysis (one node per text)")
        st.caption("Each marker is a whole text (its pooled LDI), not a single omen — so the "
                   "curve traces tablet-by-tablet, coloured by period. **Click a node to open "
                   "that tablet in the Text view.**")

        def _f(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        if not bframe.empty:
            for gi, genre in enumerate(sorted(unique_omens_df['genre'].dropna().unique())):
                g_uo = unique_omens_df[unique_omens_df['genre'] == genre]
                st.markdown(f"#### {genre}: {g_uo['filename'].nunique()} texts — {len(g_uo)} omens")
                metric, mono, pres = chart_controls(f"genre_{genre}")
                _F = pick(pres)
                df, unique_omens_df = _F['df'], _F['uo']
                bframe, gframe, comp_df = _F['bframe'], _F['gframe'], _F['comp']

                # LDI by Period for this genre — texts · omens · bin · macro · micro.
                # Reflects this section's monogram toggle; Total pools across periods.
                pr_rows, pr_idx = [], []
                for period in PERIOD_ORDER + ["Total"]:
                    puo = g_uo if period == "Total" else g_uo[g_uo['period'] == period]
                    if puo.empty:
                        continue
                    pdd = (df[df['genre'] == genre] if period == "Total"
                           else df[(df['genre'] == genre) & (df['period'] == period)])
                    b0, ma0, mi0 = trio(pdd, mono)
                    pr_rows.append([str(puo['filename'].nunique()), str(len(puo)),
                                    _f(b0), _f(ma0), _f(mi0)])
                    pr_idx.append(period)
                if pr_rows:
                    gtdf = pd.DataFrame(pr_rows, index=pr_idx,
                                        columns=["texts", "omens", "bin", "macro", "micro"])
                    gtdf.index.name = "Period"
                    gtsty = (gtdf.style
                             .set_properties(subset=["bin", "macro", "micro"],
                                             **{'background-color': '#f2f2f2'})
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
                    render_table_with_copy(gtsty, gtdf, f"genre_period_{gi}")

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
                        hovertemplate="<b>%{customdata[0]}</b><br>" + period + "<br>"
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
                    whole = trio(df[(df['genre'] == genre) & (df['period'] == period)], mono)[midx]
                    fig_genre.add_annotation(
                        x=(x0 + x1) / 2, y=1.02, xref='x', yref='y',
                        text=f"highest {ys.max():.2f}<br>whole {whole:.2f}<br>lowest {ys.min():.2f}",
                        showarrow=False, yanchor='bottom', align='center',
                        font=dict(size=11, color=col),
                    )

                fig_genre.update_layout(
                    title=f"{genre} — {metric} LDI per text (Old → Neo)",
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
                    st.session_state['goto_nav'] = "Text"
                    st.session_state['goto_file'] = clicked
                    st.rerun()

    # --- PAGE 3: Text ---
    if page == "Text":
        def _cval(row, k):
            v = row.get(k)
            return v if isinstance(v, str) and v.strip() else "-"

        # A Genre-node click jumps straight to a corpus text: force the Corpus set.
        if st.session_state.get('goto_file'):
            st.session_state['text_set'] = "Corpus"

        # One tab for every text: the main corpus, the comparanda, and the KAL 5
        # supplement (the last two are held out of the LDI counts but browsable here).
        text_set = st.radio("Text set", ["Corpus", "Comparanda", "Supplementary (KAL 5)"],
                            horizontal=True, key="text_set")

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

            # In-tab selection: Period → Genre → Text. Keyed + guarded so dependent
            # option lists never carry a stale value into a selectbox (which would error).
            sel_cols = st.columns(3)

            available_periods = sorted(df['period'].unique(),
                                       key=lambda x: PERIOD_ORDER.index(x) if x in PERIOD_ORDER else 99)
            if st.session_state.get('text_period') not in available_periods:
                st.session_state['text_period'] = available_periods[0]
            selected_period = sel_cols[0].selectbox("Period", available_periods, key='text_period')

            period_df = df[df['period'] == selected_period]
            available_genres = sorted(period_df['genre'].dropna().unique())
            if st.session_state.get('text_genre') not in available_genres:
                st.session_state['text_genre'] = available_genres[0] if available_genres else None
            selected_genre = sel_cols[1].selectbox("Genre", available_genres, key='text_genre')

            genre_df = period_df[period_df['genre'] == selected_genre]
            period_files = sorted(genre_df['filename'].unique())
            if st.session_state.get('text_file') not in period_files:
                st.session_state['text_file'] = period_files[0] if period_files else None
            selected_file = sel_cols[2].selectbox("Text", period_files, key='text_file')

            filtered_df = genre_df[genre_df['filename'] == selected_file]
            if not filtered_df.empty:
                first_row = filtered_df.iloc[0]
                _h1, _h2 = st.columns([1, 3], vertical_alignment="center")
                _h1.subheader(selected_file.rsplit(".txt", 1)[0])   # the text/tablet number
                _h2.markdown(LEGEND_HTML, unsafe_allow_html=True)
                meta = [f"**Period:** {first_row.get('period', '-')}",
                        f"**Genre:** {first_row.get('genre', '-')}",
                        f"**Provenance:** {first_row.get('provenance', '-')}"]
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
                st.caption("Comparison texts kept **out** of the main corpus (non-Akkadian parallels "
                           "or otherwise excluded). Their LDI reflects the graphic convention, not an "
                           "Akkadian logogram-vs-syllabic split — read the per-text note with care.")
                empty_msg = "No comparanda found in data/_comparanda."
            else:
                pool, pkey = FRAMES[False]['supp'], 'supp'
                st.caption("Supplementary witnesses held **out** of the main LDI counts — the further "
                           "KAL 5 extispicy tablets (Heeßel 2012), auto-extracted from the printed "
                           "edition and glyph-remapped, not hand-collated.")
                empty_msg = "No supplementary texts found in data/kal5."

            if pool.empty:
                st.info(empty_msg)
            else:
                sel = st.selectbox("Text", sorted(pool['filename'].unique()), key=f"heldout_{pkey}")
                hdf = pool[pool['filename'] == sel]
                if not hdf.empty:
                    hrow = hdf.iloc[0]
                    _h1, _h2 = st.columns([1, 3], vertical_alignment="center")
                    _h1.subheader(sel.rsplit(".txt", 1)[0])
                    _h2.markdown(LEGEND_HTML, unsafe_allow_html=True)
                    meta = [f"**Period:** {_cval(hrow, 'period')}",
                            f"**Genre:** {_cval(hrow, 'genre')}",
                            f"**Language:** {_cval(hrow, 'language')}",
                            f"**Provenance:** {_cval(hrow, 'provenance')}"]
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
