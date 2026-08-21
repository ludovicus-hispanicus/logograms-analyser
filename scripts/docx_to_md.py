"""Regenerate the article Markdown from the hand-edited OBO docx.

    py scripts/docx_to_md.py            # rewrites docs/The-Logographic-Shift.md
    py scripts/docx_to_md.py out.md     # or somewhere else

docs/The-Logographic-Shift-OBO.docx is the source of truth: it carries the
Word-side prose, the 10pt table formatting and the positioned figures. The
Markdown is derived from it, so the two cannot drift, and footnotes come out
renumbered by appearance order.

Four things are normalised on the way, because Word's layout model does not
survive a plain conversion:
  * captions that sit in the same paragraph as the image anchored to them are
    split back onto their own line;
  * images are re-seated directly above their own caption, since a floating
    image is anchored wherever it was dropped, not where it appears;
  * pandoc's extracted imageN.png is swapped back for the real assets/ file,
    matched by figure number (Word re-encodes some images, so their bytes no
    longer hash-match what make_figures.py produced);
  * the title, which Word holds as a Title-styled paragraph and pandoc lifts
    into discarded metadata, is put back as the H1.

Caption style becomes **Table N.** / **Figure N.**; the docx keeps its own
"Fig. N:" styling. Presentation lives in the Word file, verification here.

Run scripts/verify_article.py afterwards: it recomputes every printed figure
from the corpus and is what catches a stale number in the Word file.
"""
import os, re, subprocess, sys, shutil, io

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, 'docs')
DOCX = os.path.join(DOCS, 'The-Logographic-Shift-OBO.docx')
OLD_MD = os.path.join(DOCS, 'The-Logographic-Shift.md')
SCR = os.path.join(REPO, 'docs', '_build')
os.makedirs(SCR, exist_ok=True)
PANDOC = os.environ.get('PANDOC', r'C:\Users\wende\AppData\Local\Pandoc\pandoc.exe')
OUT = sys.argv[1] if len(sys.argv) > 1 else OLD_MD

# Refuse to clobber hand edits: if the Markdown is newer than the docx, someone
# has been editing the derived file and regenerating would silently discard it.
if OUT == OLD_MD and os.path.exists(OUT) and '--force' not in sys.argv:
    if os.path.getmtime(OUT) > os.path.getmtime(DOCX):
        sys.exit(
            f"REFUSING to overwrite {os.path.basename(OUT)}: it is newer than the docx,\n"
            "so it holds edits the docx does not. Either sync those edits into the docx\n"
            "first, or write elsewhere:\n"
            f"    py scripts/docx_to_md.py somewhere-else.md\n"
            "and diff before replacing. Use --force only if the Markdown is expendable.")

log = []


def say(s):
    log.append(s)
    print(s)


# ---------------------------------------------------------------- 1. convert
media = os.path.join(SCR, '_media')
shutil.rmtree(media, ignore_errors=True)
raw = os.path.join(SCR, '_raw.md')
subprocess.run([PANDOC, DOCX, '-f', 'docx',
                '-t', 'markdown-simple_tables-multiline_tables-grid_tables',
                '--wrap=none', f'--extract-media={media}', '-o', raw], check=True)
md = open(raw, encoding='utf-8').read()
say(f"pandoc: {len(md.splitlines())} lines from {os.path.basename(DOCX)}")

# Seven captions sit in the same Word paragraph as the image anchored to them,
# so pandoc emits them glued to the image: ...{width=...}Fig. 3: LDI by ...
md, n_split = re.subn(r'(\{[^}]*\})((?:Fig\.|Figure|Table)\s*\d+\s*[.:])',
                      r'\1\n\n\2', md)
say(f"captions unglued from their image line: {n_split}")

# ------------------------------------------- 2. caption text from the old md
old = open(OLD_MD, encoding='utf-8').read()
fig_asset = {int(n): p for n, p in
             re.findall(r'!\[Figure (\d+)\]\(\.\./assets/([^)]+)\)', old)}
old_fig_cap = {int(n): t for n, t in
               re.findall(r'^\*\*Figure (\d+)\.\*\*\s*(.*)$', old, re.M)}
old_tbl_cap = {int(n): t for n, t in
               re.findall(r'^\*\*Table (\d+)\.\*\*\s*(.*)$', old, re.M)}
say(f"old md: {len(fig_asset)} figure→asset, {len(old_fig_cap)} figure captions, "
    f"{len(old_tbl_cap)} table captions")

# ------------------------------------------------------------- 3. images
IMG = re.compile(r'^!\[([^\]]*)\]\([^)]*?image(\d+)\.png\)(?:\{[^}]*\})?\s*$', re.M)
seen = set()
dropped = []


def fix_img(m):
    alt, num = m.group(1), int(m.group(2))
    if num in seen:                      # Word duplicated Figure 1
        dropped.append(num)
        return '\x00DROP\x00'
    seen.add(num)
    asset = fig_asset.get(num)
    if not asset:
        say(f"  !! no asset for image{num}.png")
        return m.group(0)
    return f'![Figure {num}](../assets/{asset})'


md = IMG.sub(fix_img, md)
md = re.sub(r'\n*\x00DROP\x00\n*', '\n\n', md)
say(f"images: {len(seen)} rewritten to ../assets/"
    + (f"; dropped duplicate Figure {dropped}" if dropped else ""))

# ------------------------------------------------------- 4. caption style
n_f = n_t = 0


def finish(t):
    """Close a caption with a full stop, unless it already ends in one or in a
    footnote reference (where a trailing stop would sit after the marker)."""
    t = t.strip()
    if t.endswith('.') or re.search(r'\[\^\d+\]$', t):
        return t
    return t + '.'


def cap_fig(m):
    global n_f
    n_f += 1
    return f'**Figure {m.group(1)}.** {finish(m.group(2))}'


def cap_tbl(m):
    global n_t
    n_t += 1
    return f'**Table {m.group(1)}.** {finish(m.group(2))}'


md = re.sub(r'^(?:Fig\.|Figure)\s*(\d+)\s*[.:]\s*(.*)$', cap_fig, md, flags=re.M)
md = re.sub(r'^Table\s*(\d+)\s*[.:]\s*(.*)$', cap_tbl, md, flags=re.M)
say(f"captions normalised: {n_f} figure, {n_t} table")

# --------------------------------------------- 5. restore lost captions
L = md.split('\n')


def has_cap(idx, kind):
    for k in range(idx, min(idx + 4, len(L))):
        if re.match(r'^\*\*%s \d+\.\*\*' % kind, L[k]):
            return True
        if L[k].strip() and not L[k].startswith(('|', '!')):
            return False
    return False


# Word anchors a floating image to whatever paragraph it was dropped near, so
# four images land beside a table caption rather than their own. Lift every
# image out and re-seat it directly above its **Figure N.** caption.
imgs, body = {}, []
for line in L:
    m = re.match(r'^!\[Figure (\d+)\]', line)
    if m:
        imgs[int(m.group(1))] = line
    else:
        body.append(line)

out, seated = [], []
for line in body:
    m = re.match(r'^\*\*Figure (\d+)\.\*\*', line)
    if m and int(m.group(1)) in imgs:
        n = int(m.group(1))
        if out and out[-1].strip():
            out.append('')
        out.extend([imgs.pop(n), ''])
        seated.append(n)
    out.append(line)
L = out
say(f"images re-seated above their caption: {len(seated)}"
    + (f"; NOT PLACED: {sorted(imgs)}" if imgs else ""))

# tables: the uncaptioned blocks take the numbers missing from the sequence
present = sorted(int(x) for x in re.findall(r'^\*\*Table (\d+)\.\*\*', '\n'.join(L), re.M))
missing = [n for n in range(1, max(present) + 1) if n not in present]
out, restored_t, mi = [], [], 0
i = 0
while i < len(L):
    if L[i].startswith('|'):
        j = i
        while j < len(L) and L[j].startswith('|'):
            j += 1
        out.extend(L[i:j])
        if not has_cap(j, 'Table') and mi < len(missing):
            n = missing[mi]
            # the one deliberately uncaptioned block is the Value/Omen example
            if not L[i].startswith('| Value '):
                out.extend(['', f'**Table {n}.** {old_tbl_cap[n]}'])
                restored_t.append(n)
                mi += 1
        i = j
    else:
        out.append(L[i])
        i += 1
L = out
say(f"table captions restored: {restored_t or 'none'} (candidates were {missing})")

md = '\n'.join(L)

# The title is a Title-styled paragraph in Word, which pandoc lifts into
# document metadata and then discards without --standalone. Put it back as the
# H1, and re-bold the byline underneath it.
if not md.lstrip().startswith('# '):
    t = re.search(r'^#\s+(.*)$', open(OLD_MD, encoding='utf-8').read(), re.M)
    title = t.group(1).strip() if t else 'The Logographic Shift'
    md = re.sub(r'^\s*(Luis Sáenz)\s*$', r'**\1**', md, count=1, flags=re.M)
    md = f'# {title}\n\n' + md.lstrip('\n')
    say(f"title restored as H1: {title[:60]}")

md = re.sub(r'\n{4,}', '\n\n\n', md)
io.open(OUT, 'w', encoding='utf-8', newline='\n').write(md)

# ------------------------------------------------------------- 6. verify
f_caps = sorted(int(x) for x in re.findall(r'^\*\*Figure (\d+)\.\*\*', md, re.M))
t_caps = sorted(int(x) for x in re.findall(r'^\*\*Table (\d+)\.\*\*', md, re.M))
notes_def = sorted(int(x) for x in re.findall(r'^\[\^(\d+)\]:', md, re.M))
notes_ref = sorted(set(int(x) for x in re.findall(r'\[\^(\d+)\]', md)) - set(notes_def))
say("")
n_img = len(re.findall(r'!\[Figure', md))
say(f"RESULT  figures {len(f_caps)}/18  tables {len(t_caps)}/32  "
    f"images {n_img}/18  footnotes {len(notes_def)}")
say(f"  figure gaps: {[n for n in range(1, 19) if n not in f_caps] or 'none'}")
say(f"  table  gaps: {[n for n in range(1, 33) if n not in t_caps] or 'none'}")
orphan_def = [n for n in notes_def if f'[^{n}]' not in md.replace(f'[^{n}]:', '')]
say(f"  footnote defs {len(notes_def)}, contiguous 1..{max(notes_def)}: "
    f"{notes_def == list(range(1, max(notes_def) + 1))}")
say(f"  orphan definitions (never referenced): {orphan_def or 'none'}")
say(f"-> {OUT}")
