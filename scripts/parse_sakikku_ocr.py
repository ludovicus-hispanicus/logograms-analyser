#!/usr/bin/env python
"""Parse the Schmidtchen-Tafel-3 OCR dump (HTML score) and split it by MANUSCRIPT.

Input: the OCR output — one or more page blocks, each:
    === ... | text_id=... | .../page_NNN.png ===
    <p class="header">...</p> <table> <tr>...</tr> ... </table>

Each <tr> has three cells: entry number (class="entry"), siglum (class="ms",
e.g. A<sub>15f</sub>, B<sub>i 4</sub>, D<sub>Rs 9</sub>), and the transliteration
(class="tl") in the OCR's HTML markup.

We group rows by manuscript siglum (A-J), convert the HTML transliteration to the
project's plain-text convention, sort by canonical entry number, and (optionally)
write one .txt per manuscript with frontmatter ready to score.

HTML -> corpus text mapping:
  <i>x</i>            -> x                (syllabic; case preserved -> phonetic)
  PLAIN UPPERCASE     -> kept             (logogram)
  <sup>d</sup> etc.   -> {d}              (determinative; lowercase content)
  <sup>II</sup>       -> .II              (dual marker)
  <sup>?</sup>/<sup>!</sup> -> ? / !      (reading markers)
  <sup>28</sup>/<sup>?28</sup> -> dropped (footnote refs; '?' kept if present)
  <sub>4</sub>        -> ₄               (sign index, unicode subscript)
  ⸢ ⸣ (U+2E22/2E23)   -> stripped         (damaged-but-legible: kept & counted)
  [ ]                 -> kept             (restoration; dropped in preserved-only)
  <ḫa> / &lt;ḫa&gt;   -> ḫa               (scribal omission supplied by editor)
  (leer) (Strich) (?) -> removed
  (x)                 -> x                (ignored sign)
  <br> and  /         -> space           (manuscript-internal line break -> one entry)
"""
import re, sys, os, html

# siglum -> museum number, per Schmidtchen's ms list for each Tafel.
MAPS = {
    '3': {'A': 'BM.33424', 'B': 'BM.42970', 'C': 'BM.60744', 'D': 'MLC.2639',
          'E': 'BM.42502', 'F': 'BM.38637', 'G': 'VAT.14556', 'H': 'VAT.14553',
          'I': 'W.17360ac', 'J': 'VAT.14522'},
    '4': {'A': 'K.2723', 'B': 'AO.6682', 'C': 'ND.4405', 'D': 'VAT.14550',
          'E': 'W.22761', 'F': 'BM.38489', 'G': 'LKU.77', 'H': 'VAT.14567',
          'I': 'W.17360c', 'J': 'BM.34435'},
}
SUB = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')


def _sup(m):
    c = m.group(1).strip()
    if re.fullmatch(r'[a-zšḫṣṭṣ\.]+[0-9]?', c):   # lowercase letters (+opt digit) = determinative
        return '{' + c + '}'
    if re.fullmatch(r'I{2,3}', c):                # II / III = dual/plural marker
        return '.' + c
    if c in ('?', '!'):
        return c
    return '?' if '?' in c else ''                # footnote ref -> drop (keep ? if present)


def convert_tl(s):
    s = html.unescape(s)                          # &lt; &gt; &amp;
    s = re.sub(r'<br\s*/?>', ' / ', s)
    s = re.sub(r'<sup>(.*?)</sup>', _sup, s)
    s = re.sub(r'<sub>(.*?)</sub>', lambda m: m.group(1).translate(SUB), s)
    s = re.sub(r'</?i>', '', s)                    # drop italic tags, keep content
    s = re.sub(r'<[^>]+>', '', s)                  # any stray tags
    s = s.replace('⸢', '').replace('⸣', '')   # half-brackets ⸢ ⸣
    s = re.sub(r'\(leer\)|\(Strich\??\)|\(\?\)', '', s)
    s = s.replace('(...)', '...').replace('(x)', 'x')
    s = s.replace('<', '').replace('>', '')        # scribal-omission markers
    s = s.replace('/', ' ')                        # internal line breaks
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def has_content(line):
    """True if the line preserves any real sign (not only [...], x, dots, ?)."""
    t = re.sub(r'\[[^\]]*\]', ' ', line)           # drop restorations
    t = re.sub(r'[x\.\?\!\s{}]', '', t)            # drop fillers/markers/det braces
    return bool(t)


def parse(text):
    mss = {}                                       # siglum -> list of (entry_int, entry_str, line)
    rows = re.findall(r'<tr>(.*?)</tr>', text, re.S)
    cur_entry = None
    for row in rows:
        cells = re.findall(r'<td class="(\w+)">(.*?)</td>', row, re.S)
        d = {k: v for k, v in cells}
        ent = re.sub(r'<[^>]+>', '', d.get('entry', '')).strip().rstrip('.')
        if ent:
            cur_entry = ent
        ms_raw = re.sub(r'<[^>]+>', '', d.get('ms', '')).strip()
        m = re.match(r'([A-J])', ms_raw)
        if not m:
            continue
        sig = m.group(1)
        line = convert_tl(d.get('tl', ''))
        if not has_content(line):
            continue
        try:
            ei = int(re.match(r'\d+', cur_entry).group())
        except Exception:
            ei = 0
        mss.setdefault(sig, []).append((ei, cur_entry, line))
    for sig in mss:
        mss[sig].sort(key=lambda t: t[0])
    return mss


FRONT = """---
genre: diagnostic omens
period: Neo Babylonian
provenance: {museum}
recension: canonical Sakikkû Tablet {tablet}, manuscript {sig} (Schmidtchen 2021 BAM 13)
counting: line
series: Sakikkû (Diagnostic Handbook) Tablet {tablet}
source: auto-converted from Schmidtchen 2021 Tafel {tablet} OCR (score), manuscript {sig} rows only; see scripts/parse_sakikku_ocr.py. Single-manuscript witness (fragmentary).
note: Logograms uppercase, syllabic lowercase, {{}} determinative, [] restoration, x illegible. Sign indices as unicode subscripts. Damage half-brackets stripped (damaged-but-legible signs kept). Entry numbers = canonical Tablet {tablet} lines.
---

@text
"""


def main():
    # args: OCR_DUMP [OUTDIR]   flags: --tablet N   --t3map (use Tablet-3 museum map)
    pos = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not pos:
        print('usage: parse_sakikku_ocr.py OCR_DUMP.txt [OUTDIR] [--tablet N] [--t3map]'); return
    tablet = next((f.split('=')[1] for f in flags if f.startswith('--tablet=')), '?')
    namemap = MAPS.get(tablet, {})   # auto museum-number naming when the Tafel map is known
    text = open(pos[0], encoding='utf-8').read()
    mss = parse(text)
    outdir = pos[1] if len(pos) > 1 else None
    print(f'{"ms":<4}{"name":<14}{"entries":>8}')
    for sig in sorted(mss):
        rows = mss[sig]
        name = namemap.get(sig, sig)
        print(f'{sig:<4}{name:<14}{len(rows):>8}')
        if outdir:
            os.makedirs(outdir, exist_ok=True)
            fn = os.path.join(outdir, name + '.txt')
            with open(fn, 'w', encoding='utf-8') as f:
                f.write(FRONT.format(museum=namemap.get(sig, 'manuscript ' + sig),
                                     sig=sig, tablet=tablet))
                for ei, es, line in rows:
                    f.write(f'{es}. {line}\n')


if __name__ == '__main__':
    main()
