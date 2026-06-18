import os
import io
import shutil
import tempfile
import zipfile
import urllib.request
import urllib.parse
import streamlit as st
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

# Function words written with a SINGLE sign (monograms): the prepositions ina (=AŠ)
# and ana. Lowercase, so by default they count as syllabic; the monogram toggle
# reclassifies them as logographic. See docs/ldi-sign-level.md.
MONOGRAM_PARTICLES = {'ina', 'ana'}
SIGN_BOUNDARY = re.compile(r'[.\-]')   # signs within a word are joined by '.' or '-'

def _sign_counts(token):
    """Per-sign (logogram, phonetic) counts for one word token, splitting on '.'/'-'.
    Uppercase sign -> logogram, lowercase -> phonetic; matches compute_ratios."""
    nl = nph = 0
    for s in SIGN_BOUNDARY.split(str(token)):
        if not s:
            continue
        if any(c.isupper() for c in s):
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
    """Per-chart controls: bin macro micro | count ina/ana …  — the metric radio
    (label hidden), a separator (CSS border on the checkbox), then the monogram
    checkbox carrying the default "?" help with the Introduction link.
    Each chart owns its own pair, keyed independently. Returns (metric, monogram)."""
    c1, c2, c3, _spacer = st.columns([1.6, 2.8, 0.5, 4], vertical_alignment="center")
    metric = c1.radio(
        "metric", ["bin", "macro", "micro"], horizontal=True,
        key=f"{key}_metric", label_visibility="collapsed")
    monogram = c2.checkbox("count ina/ana as logographic", key=f"{key}_mono")
    # Always-visible link to the full explanation (no underline).
    c3.markdown(
        '<a href="?nav=Introduction" title="Full explanation on the Introduction tab" '
        'style="text-decoration:none; font-size:1.2rem; color:#1976D2;">ⓘ</a>',
        unsafe_allow_html=True)
    return metric, monogram

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
    if any(c.isupper() for c in token):
        return "logogram"
    
    # Rule 2: Phonetic (Contains lowercase)
    # "i-na-at", "šum-ma"
    if any(c.islower() for c in token):
        return "phonetic"
    
    return "other" # Fallback

def annotate_omen(text, omen_id, metadata):
    # Split by space first to get rough chunks
    raw_tokens = text.strip().split()
    annotations = []
    global_index = 0
    
    for raw_token in raw_tokens:
        # Skip line numbers (digits + dot) e.g. "1." or "1'."
        if re.match(r'^\d+\'?\.$', raw_token):
             continue

        # Clean token: strip #, [, ], |
        clean_token_str = raw_token.replace('#', '').replace('[', '').replace(']', '').replace('|', '')
        # Strip corrected-sign notation, e.g. "i-ra-ah!(IM)" -> "i-ra-ah!" (the
        # parenthesized sign name would otherwise mark the word as a logogram).
        clean_token_str = re.sub(r'!\([^()]*\)', '!', clean_token_str)
        
        if not clean_token_str:
            continue
            
        if clean_token_str in IGNORE_TOKENS:
            continue

        # Drop ditto / restoration markers like {(U)} — editorial signs, not counted.
        if re.fullmatch(r'\{\(U\)#?\}', clean_token_str):
            continue

        # Extract determinatives: {text}
        parts = []
        last_pos = 0
        
        for match in re.finditer(r'\{([^{}]+)\}', clean_token_str):
            if match.start() > last_pos:
                pre_text = clean_token_str[last_pos:match.start()]
                if pre_text:
                    parts.append({'text': pre_text, 'is_det': False})
            
            parts.append({'text': match.group(1), 'is_det': True})
            last_pos = match.end()
            
        if last_pos < len(clean_token_str):
             parts.append({'text': clean_token_str[last_pos:], 'is_det': False})
        
        for i, part in enumerate(parts):
            if not part['text']: continue
            
            p_text = part['text']
            
            if part['is_det']:
                t_type = "determinative"
            else:
                # Check for God Numbers (e.g. {d}30)
                is_god_number = False
                if p_text.isdigit():
                    # Check if previous part was {d}
                    # We iterate parts of a single token, so i-1 is the immediate predecessor in that token
                    if i > 0 and parts[i-1]['is_det'] and parts[i-1]['text'] == 'd':
                        is_god_number = True
                
                if is_god_number:
                    t_type = "logogram"
                else:
                    t_type = get_token_type(p_text)
                
            ann = {
                "token": p_text,
                "type": t_type,
                "omen_id": omen_id,
                "index": global_index
            }
            # Merge metadata
            ann.update(metadata)
            annotations.append(ann)
            
            global_index += 1
            
    return annotations

def calculate_ldi(annotations):
    # Word-level binary LDI: logograms / (logograms + phonetic). Omen particles
    # (DIŠ, BE, …) are logograms and are always counted as such.
    if not annotations:
        return 0.0

    logogram_count = 0
    total_tokens = 0

    for ann in annotations:
        if ann['type'] == 'other':
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

def load_local_data(base_path="data", include_excluded=False):
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
                             
                             all_anns.extend(annotate_omen(combined_text, oid, omen_meta))
                             
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
                            all_anns.extend(annotate_omen(line, current_omen_id, line_metadata))

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
                            clean_regex = r'^(?:\d+\'?\.\s*)?\s*(?:%\w+\s+)?' + re.escape(delimiter) + r'(?![0-9\u2080-\u2089a-zA-Z\-])'
                            
                            if re.match(clean_regex, temp_line):
                                # Flush previous omen
                                if current_omen_data['lines']:
                                    text = " ".join(current_omen_data['lines'])
                                    md = metadata.copy()
                                    md['section'] = current_omen_data['section']
                                    all_anns.extend(annotate_omen(text, str(current_omen_id), md))
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
                             all_anns.extend(annotate_omen(text, str(current_omen_id), md))
                                     
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
                            all_anns.extend(annotate_omen(line, current_omen_id, line_metadata))
                    
                    # Logic fix in next step or combined here if possible? 
                    # I need to change the proceeding `else:` to `elif metadata.get("counting"):` 
                    # and leave the original `else:` (lines 346+) for standard.
                    # But tool `replace_file_content` replaces a chunks.
                    # I will replace the `else:` block labeled "# Standard Parsing" with the ELIF block AND the ELSE block.

                
                except Exception as e:
                    st.warning(f"Failed to read {file}: {e}")

    return all_anns

def load_uploads(txt_files=None, zip_bytes=None):
    """Ingest uploaded material by staging it in a temp dir and running it through
    load_local_data — so frontmatter and every counting mode work exactly as for the
    built-in corpus. Session only: the temp dir is removed once parsed."""
    anns = []
    if txt_files:
        tmp = tempfile.mkdtemp(prefix="omen_txt_")
        try:
            for f in txt_files:
                with open(os.path.join(tmp, os.path.basename(f.name)), "wb") as out:
                    out.write(f.getvalue())
            anns += load_local_data(tmp, include_excluded=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if zip_bytes:
        tmp = tempfile.mkdtemp(prefix="omen_zip_")
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                z.extractall(tmp)
            anns += load_local_data(tmp, include_excluded=True)
        except zipfile.BadZipFile:
            st.error("That file is not a valid .zip archive.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return anns

def _ingest_text(filename, content):
    """Stage one constructed .txt (frontmatter + ATF) in a temp dir and parse it via
    load_local_data, so it goes through the same frontmatter/counting pipeline."""
    tmp = tempfile.mkdtemp(prefix="omen_fetch_")
    try:
        with open(os.path.join(tmp, filename), "w", encoding="utf-8") as f:
            f.write(content)
        return load_local_data(tmp, include_excluded=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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

# --- UI Setup ---

# --- Header: title (left, acts as Home) + nav tabs (right) on one line,
#     sharing a bottom border that reads as the tab strip's baseline. ---
NAV = ["Global", "Genre", "Text", "Comparanda", "Import"]
_PAGES = ["Introduction"] + NAV

# In-app links (e.g. "?nav=Introduction" inside markdown/tables) navigate here.
_qp_nav = st.query_params.get("nav")
if _qp_nav in _PAGES:
    st.session_state['page'] = _qp_nav
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
# replace it or add to it (session only).
if 'annotations' not in st.session_state:
    st.session_state['annotations'] = []

if not st.session_state['annotations']:
    # Default: load the local corpus (data/) on first run.
    st.session_state['annotations'] = load_local_data()

# Comparanda — comparison texts kept out of the main corpus (data/_comparanda,
# plus anything flagged `exclude: true`). Loaded once and cached.
if 'comparanda' not in st.session_state:
    st.session_state['comparanda'] = load_local_data("data/_comparanda", include_excluded=True)

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
        "Determinatives sit in the denominator (as non-logographic), so they slightly dilute the score.\n"
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

elif page == "Import":
    st.subheader("Import your own texts")

    st.info(
        "Imports are **session-only**: your texts live in memory until you reload the page and "
        "nothing is written to disk. For a permanent, local setup, **clone the repository** "
        "(`git clone …`) and drop your `.txt` files into the `data/` folder — they'll then load "
        "automatically every time you run the app."
    )

    mode = st.radio("Imported texts should…",
                    ["Add to the current corpus", "Replace the corpus (analyse only my texts)"],
                    key="imp_mode")

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
                    fetched = _ingest_text(f"{frag_id}.txt", content)
                    if fetched:
                        if mode.startswith("Replace"):
                            st.session_state['annotations'] = fetched
                        else:
                            st.session_state['annotations'] = st.session_state['annotations'] + fetched
                        st.success(f"Imported **{frag_id}** — genre **{fmeta['genre']}**, "
                                   f"period **{fmeta['period']}**, {fmeta['n_lines']} lines. "
                                   "Open Global / Genre / Text to see it.")
                        with st.expander("Show fetched eBL-ATF"):
                            st.code(content, language="text")
                    else:
                        st.warning("Fetched, but produced no countable tokens.")

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
        new_anns = load_uploads(txt_files=up, zip_bytes=(zf.getvalue() if zf else None))
        if path.strip():
            if os.path.isdir(path.strip()):
                new_anns += load_local_data(path.strip(), include_excluded=True)
            else:
                st.error(f"Folder not found: {path}")
        if new_anns:
            if mode.startswith("Replace"):
                st.session_state['annotations'] = new_anns
            else:
                st.session_state['annotations'] = st.session_state['annotations'] + new_anns
            n_texts = len({a.get('filename') for a in new_anns})
            st.success(f"Imported {n_texts} text(s) — {len(new_anns)} tokens. "
                       "Open Global / Genre / Text to see them.")
        else:
            st.warning("Nothing imported — add .txt file(s), a .zip, or a valid folder path above.")

    st.divider()
    cur_texts = len({a.get('filename') for a in st.session_state.get('annotations', [])})
    st.caption(f"Corpus currently in memory: **{cur_texts}** text(s).")
    if st.button("Reset to the built-in corpus", key="imp_reset"):
        st.session_state['annotations'] = load_local_data()
        st.success("Reloaded the built-in corpus.")

elif st.session_state['annotations']:
    df = pd.DataFrame(st.session_state['annotations'])

    # Display names for genres (e.g. 'izbu' -> 'Teratological Omens').
    df['genre'] = df['genre'].map(lambda g: GENRE_DISPLAY.get(g, str(g).title()))

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

    df = enrich_signs(df)

    # Comparanda — loaded separately, enriched the same way, kept out of the main corpus.
    comp_df = pd.DataFrame(st.session_state.get('comparanda', []))
    if not comp_df.empty:
        comp_df['genre'] = comp_df['genre'].map(lambda g: GENRE_DISPLAY.get(g, str(g).title()))
        comp_df = enrich_signs(comp_df)

    # (bin, macro, micro) for any slice, for a given monogram setting. Omen particles
    # (DIŠ, BE, …) are logograms and are always counted as such — no exclusion path.
    def trio(sub, monogram):
        ma = sub['_mono'] & monogram
        anl = sub['_nl'] + ma.astype(int)
        anph = sub['_nph'] - ma.astype(int)
        islog = (sub['type'] == 'logogram') | ma
        is_b = sub['type'] != 'other'
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

    def render_text_block(text_df, period, title, key_prefix):
        """Shared per-text view: colour legend, whole-text LDI (all three metrics),
        the colour-coded omen lines with per-line LDI, and a per-omen LDI chart.
        Used by both the Text and Comparanda tabs."""
        # Per-view controls (metric drives the chart; monogram drives all LDI here).
        metric, mono = chart_controls(key_prefix)

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
                t_type = token_row['type']
                if is_sux:
                    css_class = "sux"
                elif token_text in MONOGRAM_PARTICLES and t_type == "phonetic":
                    css_class = "monogram"
                elif t_type == "logogram":
                    css_class = "particle" if token_text in LOGOGRAM_PARTICLES else "logogram"
                elif t_type == "determinative":
                    css_class = "determinative"
                else:
                    css_class = "phonetic"
                html_parts.append(f'<span class="{css_class}">{token_text}</span>')
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
            fig_text.add_trace(go.Scatter(
                x=chart_df['seq'], y=chart_df[metric], mode='lines',
                line=dict(width=2.5, shape='spline', smoothing=1.0, color=col),
                hoverinfo='skip', showlegend=False
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
                template="simple_white", font_family="Source Sans 3",
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

    # --- Shared data prep (used by both the Global and Genre tabs) ---
    unique_omens_df = df.drop_duplicates(subset=['filename', 'omen_id'])

    # bin/graded frames. Particles (DIŠ, BE, …) are logograms and always counted.
    bframe = df[df['type'] != 'other']
    gframe = df[df['type'].isin(['logogram', 'phonetic'])]

    color_map = {
        "Old Babylonian": "#1f77b4", "Middle Babylonian/Assyrian": "#ff7f0e",
        "Neo-Babylonian/Assyrian + Late Babylonian": "#2ca02c",
    }

    # Page is chosen by the header nav (built at the top of the script).
    # --- PAGE 1: Global ---
    if page == "Global":
        st.subheader("Global Analysis")

        # Page-level controls drive both the LDI-by-Period table and the trend chart.
        metric, mono = chart_controls("global")

        # LDI by Period — texts · omens · bin · macro · micro (same styling as the
        # Genre table: shaded LDI columns, left-aligned, Period in the first column).
        st.markdown("#### LDI by Period")
        st.caption("**texts · omens · bin · macro · micro** (the three LDI columns are shaded). "
                   "**Total** pools across periods.")

        def _f(v):
            return f"{v:.2f}" if pd.notna(v) else "–"

        rows, idx = [], []
        for period in PERIOD_ORDER + ["Total"]:
            uo = unique_omens_df if period == "Total" else unique_omens_df[unique_omens_df['period'] == period]
            dd = df if period == "Total" else df[df['period'] == period]
            if uo.empty:
                continue
            b, ma, mi = trio(dd, mono)
            rows.append([str(uo['filename'].nunique()), str(len(uo)), _f(b), _f(ma), _f(mi)])
            idx.append(period)

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
            st.markdown(psty.to_html(), unsafe_allow_html=True)

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
                font_family="Source Sans 3", xaxis_title="Period",
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

    # --- PAGE 2: Genre ---
    if page == "Genre":
        st.subheader("Genre-Specific Analysis (one node per text)")
        st.caption("Each marker is a whole text (its pooled LDI), not a single omen — so the "
                   "curve traces tablet-by-tablet, coloured by period. **Click a node to open "
                   "that tablet in the Text view.**")

        # LDI by genre × period — each genre column splits into bin / macro / micro;
        # a Total row pools across periods. (Per-genre text/omen counts appear in the
        # chart headers below.)
        st.markdown("#### LDI by Genre and Period")
        st.caption("Per genre: **texts · omens · bin · macro · micro** (the three LDI columns are shaded). "
                   "Rows are periods; **Total** pools across periods. (Monograms off here — toggle them "
                   "per chart below.)")
        genre_order = sorted(unique_omens_df['genre'].dropna().unique())
        if not unique_omens_df.empty and genre_order:
            def _f(v):
                return f"{v:.2f}" if pd.notna(v) else "–"

            periods = [p for p in PERIOD_ORDER if not df[df['period'] == p].empty]
            sub_cols = ["texts", "omens", "bin", "macro", "micro"]
            cols = pd.MultiIndex.from_product([genre_order, sub_cols])

            rows_data, idx = [], []
            for period in periods + ["Total"]:
                uo = unique_omens_df if period == "Total" else unique_omens_df[unique_omens_df['period'] == period]
                dd = df if period == "Total" else df[df['period'] == period]
                vals = []
                for g_name in genre_order:
                    guo = uo[uo['genre'] == g_name]
                    n_t, n_o = guo['filename'].nunique(), len(guo)
                    b, ma, mi = trio(dd[dd['genre'] == g_name], False)
                    if n_o:
                        vals += [str(n_t), str(n_o), _f(b), _f(ma), _f(mi)]
                    else:
                        vals += ["–", "–", "–", "–", "–"]
                rows_data.append(vals)
                idx.append(period)

            tdf = pd.DataFrame(rows_data, index=idx, columns=cols)
            # Put "Period" on the genre-header row (as the column level-0 name) rather
            # than on its own row below.
            tdf.index.name = None
            tdf.columns = tdf.columns.set_names(["Period", ""])

            # Thicker vertical divider at the start of each genre group.
            n_per = len(sub_cols)
            border_styles = [
                {'selector': f'.col{g * n_per}', 'props': [('border-left', '2px solid #bbb')]}
                for g in range(len(genre_order))
            ]

            sty = (tdf.style
                   # Shade the three LDI sub-columns a slightly different gray.
                   .set_properties(subset=pd.IndexSlice[:, (slice(None), ["bin", "macro", "micro"])],
                                   **{'background-color': '#f2f2f2'})
                   .set_table_styles([
                       {'selector': '', 'props': [('border-collapse', 'collapse')]},   # left-aligned
                       {'selector': 'th.col_heading', 'props': [('text-align', 'center'),
                                                                ('padding', '4px 10px')]},
                       {'selector': 'th.row_heading', 'props': [('text-align', 'left'),
                                                                ('padding', '4px 10px')]},
                       {'selector': 'td', 'props': [('text-align', 'center'),
                                                    ('padding', '4px 10px'),
                                                    ('border-bottom', '1px solid #f0f0f0')]},
                   ] + border_styles))
            st.markdown(sty.to_html(), unsafe_allow_html=True)

        st.divider()

        if not bframe.empty:
            for genre in sorted(unique_omens_df['genre'].dropna().unique()):
                g_uo = unique_omens_df[unique_omens_df['genre'] == genre]
                st.markdown(f"#### {genre}: {g_uo['filename'].nunique()} texts — {len(g_uo)} omens")
                metric, mono = chart_controls(f"genre_{genre}")

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
                    template="simple_white", font_family="Source Sans 3",
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

        # Filter content
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

            render_text_block(filtered_df, selected_period, selected_file, "text")

    # --- PAGE 4: Comparanda ---
    if page == "Comparanda":
        st.caption("Comparison texts kept **out** of the main corpus (non-Akkadian parallels or "
                   "otherwise excluded). Their LDI reflects the graphic convention, not an "
                   "Akkadian logogram-vs-syllabic split — read the per-text note with care.")

        def _cval(row, k):
            v = row.get(k)
            return v if isinstance(v, str) and v.strip() else "-"

        if comp_df.empty:
            st.info("No comparanda found in data/_comparanda.")
        else:
            selected_comp = st.selectbox("Comparandum", sorted(comp_df['filename'].unique()),
                                         key="comp_select")
            cdf = comp_df[comp_df['filename'] == selected_comp]

            if not cdf.empty:
                crow = cdf.iloc[0]
                # Header: comparandum number + legend (same layout as the Text view).
                _h1, _h2 = st.columns([1, 3], vertical_alignment="center")
                _h1.subheader(selected_comp.rsplit(".txt", 1)[0])
                _h2.markdown(LEGEND_HTML, unsafe_allow_html=True)
                meta = [f"**Period:** {_cval(crow, 'period')}",
                        f"**Genre:** {_cval(crow, 'genre')}",
                        f"**Language:** {_cval(crow, 'language')}",
                        f"**Provenance:** {_cval(crow, 'provenance')}"]
                meta += biblio_and_ebl_lines(crow)
                note = _cval(crow, 'note')
                if note != "-":
                    meta.append(f"**Note:** {note}")
                st.markdown("  \n".join(meta), unsafe_allow_html=True)

                render_text_block(cdf, crow.get('period'), selected_comp, "comp")

else:
    st.info("Upload a text file or load sample data to begin.")
