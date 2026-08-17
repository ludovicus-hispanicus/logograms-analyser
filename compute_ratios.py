"""Standalone LDI computation — mirrors app.py logic without Streamlit."""
import os
import re
import warnings
import yaml
import pandas as pd

LOGOGRAM_PARTICLES = {'DIŠ', 'BAD', 'BE', 'UD', 'AŠ'}
IGNORE_TOKENS = {'x', '($___$)', '.', '..', '...'}

# Number-logograms: bare numerals that ARE logographic writings of a word —
# 15 = ZAG "right", 150 = GUB₃ "left", 30 = Sîn (the moon-god). Written as plain
# digits they otherwise fall through to "other" and get dropped; here they are
# counted as logograms (cf. the {d}30 god-number already handled in annotate).
NUMBER_LOGOGRAMS = {'15', '150', '30'}

# Function words written with a SINGLE sign (a monogram), not a phonetic spelling:
# the preposition ina (sign AŠ) and ana (sign ana). They are transliterated in
# lowercase, so by default they count as phonetic/syllabic — but as one-sign,
# non-decomposed writings of a whole lexeme they pattern with logograms (a quasi-
# logographic abbreviation, cf. i-na / a-na spelled out). The optional
# monogram_as_log flag reclassifies them as logograms. See docs/ldi-sign-level.md.
MONOGRAM_PARTICLES = {'ina', 'ana'}

# Fully-restored span "[ ... ]" (non-nesting). Used to compute a preserved-only
# variant of the LDI, in which the editor's reconstructions are dropped while
# damaged-but-legible signs (marked '#') are kept. See strip_restored().
RESTORED_SPAN = re.compile(r'\[[^\[\]]*\]')

# eBL-ATF "discourse" sections that are paratext, not omen text: a colophon's
# scribe/date lines (often ending in a Sumerian year-name) or a catchline (the
# incipit of the NEXT tablet) must not enter any count.
NON_TEXT_SECTIONS = {'colophon', 'catchline', 'date', 'signature', 'signatures',
                     'summary', 'witnesses'}

# eBL-ATF commentary protocols: '!cm' (commentary), '!qt' (quotation) and '!zz'
# (uncertain) open a span that is not base text; '!bs' returns to base text.
# A protocol stands at the start of a line (after the line number) and stays in
# force until replaced, following the eBL-ATF specification.
PROTOCOL_RE = re.compile(r"^((?:[a-zA-Z]{1,2}\+)?\d+'?\.\s*)?!(bs|cm|qt|zz)\b\s*(.*)$")


def strip_paratext(lines):
    """Drop paratext before omen segmentation (both loaders call this).

    Removes the content lines of NON_TEXT_SECTIONS (the '@' marker itself is
    kept, so segmenters still see the section change) and every line inside a
    !cm/!qt/!zz commentary span until a !bs resumes the base text."""
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
                out.append(rest)   # '!bs' line: keep its content, drop the marker
            continue
        if in_commentary:
            continue
        out.append(line)
    return out


def strip_restored(text):
    """Replace fully-restored '[ ... ]' spans with '...' (an ignored token).

    Half-broken words keep their preserved part: 'KU[Š₅-túm]' -> 'KU ...'.
    Damaged-but-legible signs ('#') are untouched, since they are on the tablet.
    """
    prev = None
    out = text
    while prev != out:                       # collapse nested/adjacent spans
        prev = out
        out = RESTORED_SPAN.sub(' ... ', out)
    return out.replace('[', ' ... ').replace(']', '')  # drop dangling brackets

PERIOD_MAPPING = {
    "Old Babylonian": "Old Period", "Old Assyrian": "Old Period",
    "Early Old Babylonian": "Old Period",
    "Late Old Babylonian": "Old Period",
    "Middle Babylonian": "Middle Period", "Middle Assyrian": "Middle Period",
    "Early Middle Babylonian": "Middle Period",
    "Late Middle Babylonian": "Middle Period",
    "Neo-Assyrian": "Neo Period", "Neo Babylonian": "Neo Period",
    "Neo-Babylonian": "Neo Period",
    "Late Babylonian": "Neo Period",
    "Late-Babylonian": "Neo Period",
    "Neo-Assyrian / Late Babylonian": "Neo Period",
}
PERIOD_ORDER = ["Old Period", "Middle Period", "Neo Period"]


def get_token_type(token):
    if token in LOGOGRAM_PARTICLES: return "logogram"
    if token.rstrip('?!') in NUMBER_LOGOGRAMS: return "logogram"  # 15/150/30 (right/left/Sîn)
    if any(c.isupper() for c in token): return "logogram"
    if any(c.islower() for c in token): return "phonetic"
    return "other"


def annotate_omen(text, omen_id, metadata, preserved_only=False):
    if preserved_only:
        text = strip_restored(text)
    raw_tokens = text.strip().split()
    annotations = []
    gi = 0
    language = "akkadian"
    for raw_token in raw_tokens:
        if re.match(r'^\d+\'?\.$', raw_token): continue
        # ATF language-shift markers (%sux, %akk, %es, ...): set the language for
        # the following tokens and drop the marker itself (it is not a sign).
        if re.match(r'^%\w+$', raw_token):
            code = raw_token[1:].lower()
            language = "sumerian" if code in ("sux", "es", "eg") else "akkadian"
            continue
        clean = raw_token.replace('#', '').replace('[', '').replace(']', '').replace('|', '')
        clean = re.sub(r'!\([^()]*\)', '!', clean)
        if not clean or clean in IGNORE_TOKENS: continue

        parts, last = [], 0
        for m in re.finditer(r'\{([^{}]+)\}', clean):
            if m.start() > last:
                pre = clean[last:m.start()]
                if pre: parts.append({'text': pre, 'is_det': False})
            parts.append({'text': m.group(1), 'is_det': True})
            last = m.end()
        if last < len(clean):
            parts.append({'text': clean[last:], 'is_det': False})

        for i, part in enumerate(parts):
            if not part['text']: continue
            p = part['text']
            if part['is_det']:
                t = "determinative"
            else:
                if p.isdigit() and i > 0 and parts[i-1]['is_det'] and parts[i-1]['text'] == 'd':
                    t = "logogram"
                else:
                    t = get_token_type(p)
            ann = {"token": p, "type": t, "omen_id": omen_id, "index": gi}
            ann.update(metadata)
            ann["language"] = language  # after update() so metadata can't clobber it
            annotations.append(ann)
            gi += 1
    return annotations


SIGN_BOUNDARY = re.compile(r'[.\-]')  # within-word sign boundaries: '.' and '-'


def _content_signs(part_text):
    """Split a non-determinative part into individual signs on '.' and '-'."""
    return [s for s in SIGN_BOUNDARY.split(part_text) if s]


def annotate_signs(text, omen_id, metadata, preserved_only=False):
    """SIGN-LEVEL tokenizer for the graded LDI (one row per sign).

    Unlike annotate_omen (which scores a whole space-token as a logogram if it
    contains any uppercase sign), this splits every word into its constituent
    signs on '.' and '-' and classifies each sign on its own. So 'ŠIR-MEŠ-šu₂'
    yields ŠIR(log) + MEŠ(log) + šu₂(phonetic): the phonetic complement is no
    longer absorbed into the logogram.

    Each row carries 'word_index' (signs of the same written word share it), so
    per-word logographic degrees can be computed downstream. Determinatives are
    tagged 'determinative' and, per docs/ldi-sign-level.md, are EXCLUDED from the
    logographic degree (unpronounced classifiers); numerals are not counted.
    """
    if preserved_only:
        text = strip_restored(text)
    rows = []
    gi = 0
    wi = 0
    language = "akkadian"
    for raw_token in text.strip().split():
        if re.match(r'^\d+\'?\.$', raw_token): continue
        if re.match(r'^%\w+$', raw_token):
            code = raw_token[1:].lower()
            language = "sumerian" if code in ("sux", "es", "eg") else "akkadian"
            continue
        clean = raw_token.replace('#', '').replace('[', '').replace(']', '').replace('|', '')
        clean = re.sub(r'!\([^()]*\)', '!', clean)
        if not clean or clean in IGNORE_TOKENS: continue

        parts, last = [], 0
        for m in re.finditer(r'\{([^{}]+)\}', clean):
            if m.start() > last:
                pre = clean[last:m.start()]
                if pre: parts.append({'text': pre, 'is_det': False})
            parts.append({'text': m.group(1), 'is_det': True})
            last = m.end()
        if last < len(clean):
            parts.append({'text': clean[last:], 'is_det': False})

        word_has_sign = False
        for i, part in enumerate(parts):
            if not part['text']: continue
            if part['is_det']:
                signs = [(part['text'], 'determinative')]
            elif part['text'].isdigit() and i > 0 and parts[i-1]['is_det'] and parts[i-1]['text'] == 'd':
                signs = [(part['text'], 'logogram')]  # divine name as number, e.g. {d}30
            else:
                signs = [(s, get_token_type(s)) for s in _content_signs(part['text'])]
            for sign, t in signs:
                if not sign or t == 'other':  # numerals / stray punctuation: not counted
                    continue
                row = {"token": sign, "type": t, "omen_id": omen_id,
                       "index": gi, "word_index": wi}
                row.update(metadata)
                row["language"] = language
                rows.append(row)
                gi += 1
                word_has_sign = True
        if word_has_sign:
            wi += 1
    return rows


def load_local_data(base_path="data", preserved_only=False, annotate=None):
    """Load and tokenize the corpus.

    preserved_only=True drops the editor's reconstructions ('[ ... ]') from the
    token count, so the LDI reflects only what survives on the tablet. Omen
    segmentation is unchanged — the same omens are produced either way.

    annotate selects the tokenizer: annotate_omen (default, word-level, binary
    LDI) or annotate_signs (sign-level, for the graded LDI). Use load_local_signs
    for the latter.
    """
    annotate = annotate or annotate_omen
    all_anns = []
    folder_map = {"old": "Old Babylonian", "middle": "Middle Babylonian", "new": "Neo-Assyrian"}

    for root, _, files in os.walk(base_path):
        for file in files:
            if not file.endswith(".txt"): continue
            rel = os.path.relpath(root, base_path)
            parts = rel.split(os.sep)
            default_period = folder_map.get(parts[0], parts[0].title()) if parts else "Unspecified"
            default_genre = parts[1].title() if len(parts) >= 2 else "Unspecified"

            fp = os.path.join(root, file)
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()

            metadata = {"filename": file, "period": default_period, "genre": default_genre, "section": "Unspecified"}
            body = content
            if content.startswith('---'):
                ps = content.split('---', 2)
                if len(ps) >= 3:
                    body = ps[2]
                    try:
                        fm = yaml.safe_load(ps[1])
                        if fm:
                            # The corpus field is `discipline:` (the genre is
                            # divination; extispicy, astrology … are disciplines
                            # of it). `genre:` is still read so older files — and
                            # the two comparanda that really are other genres,
                            # prayer and incantation — keep working.
                            if 'discipline' in fm and 'genre' not in fm:
                                fm['genre'] = fm['discipline']
                            metadata.update(fm)
                    except yaml.YAMLError as e:
                        # Never swallow this: a broken header means the file keeps
                        # NO metadata at all (period, genre, counting), so it silently
                        # drops out of every grouped figure. Usually an unquoted ': '
                        # inside a prose value -- quote the value or rephrase.
                        warnings.warn(f"{fp}: unparsable YAML frontmatter, metadata ignored -- {e}",
                                      stacklevel=2)

            if metadata.get("exclude"):  # documented but kept out of all counts
                continue

            raw_p = metadata.get("period", "Unspecified")
            metadata["period"] = PERIOD_MAPPING.get(raw_p, raw_p)

            current_section = "Unspecified"
            current_omen_id = "Unknown"
            lines = strip_paratext(body.splitlines())

            if metadata.get("counting") == "§":
                section_omens = {}
                cur_id = None
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    if line.startswith('@'): current_section = line.strip('@').title(); continue
                    if line.startswith('$') or line.startswith('#'): continue
                    m = re.match(r'§(\S+)\s+(.*)', line)
                    if m:
                        cur_id = m.group(1)
                        c = re.sub(r'^\d+\'?\.\s*', '', m.group(2))
                        section_omens.setdefault(cur_id, []).append({'text': c, 'section': current_section})
                for oid, dl in section_omens.items():
                    if not dl: continue
                    combined = " ".join(d['text'] for d in dl)
                    md = metadata.copy(); md['section'] = dl[0]['section']
                    all_anns.extend(annotate(combined, oid, md, preserved_only))

            elif metadata.get("counting") == "line":
                oid = 0
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    if line.startswith('@'): current_section = line.strip('@').title(); continue
                    if line.startswith('$') or line.startswith('#'): continue
                    oid += 1
                    md = metadata.copy(); md['section'] = current_section
                    all_anns.extend(annotate(line, str(oid), md, preserved_only))

            elif metadata.get("counting"):
                delim = metadata.get("counting")
                cur = {'lines': [], 'section': "Unspecified"}
                oid = 1
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    if line.startswith('@'): current_section = line.strip('@').title(); continue
                    if line.startswith('$') or line.startswith('#'): continue
                    temp = line.replace('[', '').replace(']', '')
                    # Line number may be plain (12.) or eBL relative (a+1., a+41.).
                    rgx = r'^(?:(?:[a-zA-Z]{1,2}\+)?\d+\'?\.\s*)?(?:%\w+\s+)?\s*' + re.escape(delim) + r'(?![0-9₀-₉a-zA-Z\-])'
                    # A line opening with a language shift (e.g. "%sux DIŠ ...", or a
                    # Sumerian colophon "%sux mu ...") always begins a new omen, so
                    # Sumerian lines are not folded into the preceding Akkadian omen.
                    body_after_num = re.sub(r"^(?:[a-zA-Z]{1,2}\+)?\d+'?\.\s*", '', temp).lstrip()
                    if re.match(rgx, temp) or body_after_num.startswith('%'):
                        if cur['lines']:
                            md = metadata.copy(); md['section'] = cur['section']
                            all_anns.extend(annotate(" ".join(cur['lines']), str(oid), md, preserved_only))
                            oid += 1
                        cur = {'lines': [line], 'section': current_section}
                    else:
                        cur['lines'].append(line)
                if cur['lines']:
                    md = metadata.copy(); md['section'] = cur['section']
                    all_anns.extend(annotate(" ".join(cur['lines']), str(oid), md, preserved_only))
            else:
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    if line.startswith('@'): current_section = line.strip('@').title(); continue
                    if line.startswith('$') or line.startswith('#'): continue
                    idm = re.match(r'^(\d+\'?)\.', line)
                    if idm: current_omen_id = idm.group(1)
                    md = metadata.copy(); md['section'] = current_section
                    all_anns.extend(annotate(line, current_omen_id, md, preserved_only))
    return all_anns


def _drop_contentless(frame):
    """Drop 'content-less' omens before pooling an LDI: omens whose only surviving
    scorable token is the omen particle (DIŠ/AŠ/BE/…) with everything else broken
    or lost (e.g. '[DIŠ ...] x#', or a bare '[...]'). A lone DIŠ is not evidence of
    logographic writing, so the whole omen is excluded from every metric (it still
    counts as an omen). Signal = any phonetic token, or any non-particle logogram.
    Mirrors app.py._drop_contentless so the batch script and the app agree."""
    if len(frame) == 0 or 'omen_id' not in frame.columns:
        return frame
    is_signal = frame['type'].isin(['logogram', 'phonetic']) & (
        (frame['type'] == 'phonetic') | ~frame['token'].isin(LOGOGRAM_PARTICLES))
    keys = [frame['filename'], frame['omen_id']] if 'filename' in frame.columns else [frame['omen_id']]
    return frame[is_signal.groupby(keys).transform('any')]


def ldi(sub, exclude_particles=False, monogram_as_log=False):
    # Count only logogram/phonetic tokens. Determinatives (unpronounced
    # classifiers such as {mul}, {d}, {ki}) are excluded from the denominator,
    # matching the graded metrics (graded_ldi) and app.py's word-level bin, so
    # the whole project uses ONE convention. Omen particles (DIŠ/AŠ/…) are
    # logograms and are counted unless exclude_particles is set.
    sub = sub[sub['type'].isin(['logogram', 'phonetic'])]
    sub = _drop_contentless(sub)   # lone-DIŠ / all-broken omens carry no signal
    if exclude_particles:
        mask = (sub['token'].isin(LOGOGRAM_PARTICLES)) & (sub['type'] == 'logogram')
        sub = sub[~mask]
    if len(sub) == 0: return (0.0, 0, 0)
    types = sub['type']
    if monogram_as_log:                       # count ina/ana monograms as logograms
        types = types.where(~sub['token'].isin(MONOGRAM_PARTICLES), 'logogram')
    logs = (types == 'logogram').sum()
    return (logs / len(sub), logs, len(sub))


def load_local_signs(base_path="data", preserved_only=False):
    """Sign-level load of the corpus (one row per sign) for the graded LDI.

    Same omen segmentation as load_local_data, but tokenized with annotate_signs.
    """
    return load_local_data(base_path, preserved_only, annotate=annotate_signs)


def graded_ldi(signs, exclude_particles=False, monogram_as_log=False):
    """Graded sign-level LDI from a sign-level DataFrame (see annotate_signs).

    Returns a dict with two complementary aggregates and the three-state word
    composition (see docs/ldi-sign-level.md):

      micro  : logogram / (logogram + phonetic) signs, pooled.   Weights by SIGN.
               This is the strict reading: a phonetic complement is one more
               phonetic sign, so it counts fully against the score.
      macro  : mean over WORDS of each word's logographic degree
               (log signs / (log + phon signs) within the word). Weights by WORD,
               so a logogram+complement word lands strictly between 0 and 1
               (e.g. ŠIR-MEŠ-šu₂ = 2/3) rather than being divided away.
      pure / mixed / syllabic : word counts — pure-logographic (no complement),
               mixed (logogram + phonetic complement), and syllabic.
      log / phon / det / words : raw sign and word counts.

    Determinatives are excluded from both aggregates (unpronounced classifiers).
    exclude_particles drops the omen-initial logogram particles (DIŠ/BE/…).
    """
    content = signs[signs['type'].isin(['logogram', 'phonetic'])]
    content = _drop_contentless(content)   # lone-DIŠ / all-broken omens carry no signal
    if exclude_particles:
        mask = (content['token'].isin(LOGOGRAM_PARTICLES)) & (content['type'] == 'logogram')
        content = content[~mask]
    if monogram_as_log:                       # count ina/ana monograms as logograms
        content = content.copy()
        content.loc[content['token'].isin(MONOGRAM_PARTICLES), 'type'] = 'logogram'

    logs = int((content['type'] == 'logogram').sum())
    phons = int((content['type'] == 'phonetic').sum())
    det = int((signs['type'] == 'determinative').sum())
    micro = logs / (logs + phons) if (logs + phons) else 0.0

    pure = mixed = syll = 0
    degrees = []
    for _, w in content.groupby(['filename', 'omen_id', 'word_index']):
        nl = int((w['type'] == 'logogram').sum())
        np_ = int((w['type'] == 'phonetic').sum())
        if nl + np_ == 0:
            continue
        degrees.append(nl / (nl + np_))
        if np_ == 0:
            pure += 1
        elif nl == 0:
            syll += 1
        else:
            mixed += 1
    macro = sum(degrees) / len(degrees) if degrees else 0.0

    return {"micro": micro, "macro": macro, "pure": pure, "mixed": mixed,
            "syllabic": syll, "words": len(degrees),
            "log": logs, "phon": phons, "det": det}


if __name__ == "__main__":
    anns = load_local_data("data")
    df_all = pd.DataFrame(anns)

    # The LDI measures Akkadian logogram density; Sumerian (%sux) content is
    # transliterated in lowercase and reported separately, not pooled below.
    sux = df_all[df_all['language'] == 'sumerian']
    df = df_all[df_all['language'] == 'akkadian']

    print(f"Total annotations loaded: {len(df_all)} (Akkadian {len(df)}, Sumerian {len(sux)})")
    print(f"Unique files: {df['filename'].nunique()}")
    print(f"Unique omens: {df.groupby(['filename','omen_id']).ngroups}")
    if not sux.empty:
        sr, slg, stot = ldi(sux)
        somens = sux.groupby(['filename', 'omen_id']).ngroups
        print(f"Sumerian (%sux), reported separately: LDI={sr:.3f} ({slg}/{stot}), "
              f"{somens} omens in {sux['filename'].nunique()} files")
    print()

    print("=" * 70)
    print("OVERALL LDI BY PERIOD (time-ordered)")
    print("=" * 70)
    print(f"{'Period':<18} {'LDI':>8} {'Logograms':>12} {'Total':>10} {'Omens':>8} {'Files':>8}")
    for period in PERIOD_ORDER:
        p = df[df['period'] == period]
        if p.empty: continue
        r, lg, tot = ldi(p)
        omens = p.groupby(['filename','omen_id']).ngroups
        files = p['filename'].nunique()
        print(f"{period:<18} {r:>8.3f} {lg:>12} {tot:>10} {omens:>8} {files:>8}")

    print("\n" + "=" * 70)
    print("LDI BY CORPUS (period × genre)")
    print("=" * 70)
    print(f"{'Period':<18} {'Genre':<16} {'LDI':>8} {'Logograms':>12} {'Total':>10} {'Omens':>8}")
    rows = []
    for period in PERIOD_ORDER:
        p = df[df['period'] == period]
        if p.empty: continue
        for genre in sorted(p['genre'].unique()):
            sub = p[p['genre'] == genre]
            r, lg, tot = ldi(sub)
            omens = sub.groupby(['filename','omen_id']).ngroups
            rows.append((period, genre, r, lg, tot, omens))
            print(f"{period:<18} {genre:<16} {r:>8.3f} {lg:>12} {tot:>10} {omens:>8}")

    print("\n" + "=" * 70)
    print("LDI BY INDIVIDUAL FILE (corpus)")
    print("=" * 70)
    print(f"{'Period':<18} {'Genre':<14} {'File':<28} {'LDI':>8} {'Omens':>6}")
    for period in PERIOD_ORDER:
        p = df[df['period'] == period]
        if p.empty: continue
        for fn in sorted(p['filename'].unique()):
            sub = p[p['filename'] == fn]
            r, _, _ = ldi(sub)
            omens = sub['omen_id'].nunique()
            genre = sub['genre'].iloc[0]
            print(f"{period:<18} {genre:<14} {fn:<28} {r:>8.3f} {omens:>6}")
