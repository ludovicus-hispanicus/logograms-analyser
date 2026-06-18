#!/usr/bin/env python
"""Parse a PLAIN-TEXT Schmidtchen score (one 'siglum-ref  transliteration' per
line, as copied cleanly from the PDF) and split it by MANUSCRIPT — the text-format
sibling of parse_sakikku_ocr.py (which handles the HTML-OCR format).

Each entry is a number ("1.", "30.", "162′") followed by the leading manuscript's
siglum-ref and transliteration; further manuscripts for the same entry follow on
their own lines, beginning with their siglum-ref (e.g. "Bi 1a", "C10′b", "Aii 7",
"A2 iv 1", "FRs 5′"). The siglum is the leading capital letter A-L.

HTML is absent here; instead we handle the print apparatus directly:
  ˹ ˺ ˻ ˼ ⸢ ⸣        half-brackets (damaged-but-legible) -> stripped (kept & counted)
  [ ]                restoration (kept; dropped in preserved-only)
  < >                scribal omission supplied by editor -> unwrapped
  (leer) (Strich)    -> removed ;  (x) -> x ;  {x} -> removed ;  / -> space
  15 / 150           right/left numbers -> ZAG / GUB₃ (corpus convention; these
                     are the only digit-tokens in the diagnostic body that stand
                     for logograms — dates use 1/3/41 etc.)
  SA5 GE6 DU8 …      sign indices -> unicode subscripts
Determinatives written as lowercase prefixes (dXV, lúGIG, gišMÁ) are LEFT as-is:
they don't change a token's logogram/phonetic class, so the LDI is unaffected.
"""
import sys, os, re

MAPS = {
    '14': {'A': 'K.2006', 'B': 'VAT.14542', 'C': 'VAT.303', 'D': 'VAT.14543',
           'E': 'VAT.14545', 'F': 'BM.38655', 'G': 'VAT.14540', 'H': 'VAT.14541',
           'I': 'VAT.14547', 'J': 'VAT.14548', 'K': 'W.17360o', 'L': 'LKU.65'},
}
SUB = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
HALF = '˹˺˻˼⸢⸣⸤⸥'
# transliteration begins at the first of these markers on the (raw) line:
TLSTART = re.compile(r'(\[|˹|˻|⸢|DIŠ|\(leer|\(Strich|\(x\))')


def convert(s):
    for c in HALF:
        s = s.replace(c, '')
    s = re.sub(r'\(leer\)|\(Strich\??\)|\(\?\)', '', s)
    s = s.replace('(...)', '...').replace('(x)', 'x').replace('{x}', '')
    s = s.replace('<', '').replace('>', '')
    s = s.replace('/', ' ')
    s = re.sub(r'\b150\b', 'GUB₃', s)          # left  (150 before 15!)
    s = re.sub(r'\b15\b', 'ZAG', s)            # right
    s = re.sub(r'([A-ZÀ-ÿ])(\d+)', lambda m: m.group(1) + m.group(2).translate(SUB), s)
    return re.sub(r'\s+', ' ', s).strip()


def has_content(line):
    t = re.sub(r'\[[^\]]*\]', ' ', line)
    t = re.sub(r'[x.\?\!\s:{}]', '', t)
    return bool(t)


def parse(text):
    mss = {}
    cur_entry = '0'
    section = None                              # None | 'Stichzeile' | 'Kolophon'
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if 'Textbearbeitung' in line or line == 'JJ' or re.match(r'^\d{4}\s', line):
            continue                            # page headers / footnotes
        if re.match(r'^\d{3}$', line):
            continue                            # bare page numbers
        ms = re.match(r'^(Stichzeile|Kolophon)\b', line)
        if ms:
            section = ms.group(1)
            line = line[ms.end():].lstrip(' :')
            if not line:
                continue
        # entry-number prefix?
        em = re.match(r"^(\d{1,3})(['′]?)\.?\s+(.*)$", line)
        if em:
            cur_entry = em.group(1) + em.group(2)
            line = em.group(3)
            section = None          # a numbered entry ends any Stichzeile/Kolophon run
        sm = re.match(r'^([A-L])', line)
        if not sm:
            continue
        sig = sm.group(1)
        tm = TLSTART.search(line)
        if not tm:
            continue
        tl = convert(line[tm.start():])
        if not has_content(tl):
            continue
        label = cur_entry if section is None else section
        try:
            ei = int(re.match(r'\d+', cur_entry).group())
        except Exception:
            ei = 9999
        mss.setdefault(sig, []).append((ei, label, tl))
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
source: extracted from Schmidtchen 2021 Tafel {tablet} edition (score), manuscript {sig} rows only; see scripts/parse_sakikku_text.py. Single-manuscript witness (fragmentary).
note: Logograms uppercase, syllabic lowercase, [] restoration (dropped in preserved-only), x illegible; sign indices as unicode subscripts; right/left numbers 15/150 normalised to ZAG/GUB₃. Damage half-brackets stripped (damaged-but-legible signs kept). Divine/other determinatives left as lowercase prefixes (LDI-neutral). Entry numbers = canonical Tablet {tablet} lines; Stichzeile/Kolophon labelled.
---

@text
"""


def main():
    pos = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not pos:
        print('usage: parse_sakikku_text.py SCORE.txt [OUTDIR] [--tablet=N]'); return
    tablet = next((f.split('=')[1] for f in flags if f.startswith('--tablet=')), '?')
    namemap = MAPS.get(tablet, {})
    mss = parse(open(pos[0], encoding='utf-8').read())
    outdir = pos[1] if len(pos) > 1 else None
    print(f'{"ms":<4}{"name":<12}{"entries":>8}')
    for sig in sorted(mss):
        rows = mss[sig]
        name = namemap.get(sig, sig)
        print(f'{sig:<4}{name:<12}{len(rows):>8}')
        if outdir:
            os.makedirs(outdir, exist_ok=True)
            with open(os.path.join(outdir, name + '.txt'), 'w', encoding='utf-8') as f:
                f.write(FRONT.format(museum=namemap.get(sig, 'manuscript ' + sig),
                                     sig=sig, tablet=tablet))
                for ei, label, tl in rows:
                    pre = '# ' if label in ('Stichzeile', 'Kolophon') else ''
                    f.write(f'{pre}{label}. {tl}\n')


if __name__ == '__main__':
    main()
