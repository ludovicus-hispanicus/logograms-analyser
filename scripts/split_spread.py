#!/usr/bin/env python
"""Render a two-page-spread scan (e.g. Rochberg 1988) and split each spread into
its left and right book pages, for cleaner OCR.

Usage:  python scripts/split_spread.py INPUT.pdf OUTDIR [dpi] [first] [last]
Outputs OUTDIR/pNNN_L.png and pNNN_R.png (left = lower book page, right = higher).
"""
import sys, os, glob, subprocess
from PIL import Image


def main():
    pdf = sys.argv[1]
    outdir = sys.argv[2]
    dpi = sys.argv[3] if len(sys.argv) > 3 else '300'
    rng = []
    if len(sys.argv) > 5:
        rng = ['-f', sys.argv[4], '-l', sys.argv[5]]
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.join(outdir, '_spread')
    subprocess.run(['pdftoppm', '-png', '-r', dpi] + rng + [pdf, stem], check=True)
    n = 0
    for f in sorted(glob.glob(stem + '*.png')):
        im = Image.open(f)
        w, h = im.size
        mid = w // 2
        num = os.path.basename(f).replace('_spread-', '').replace('.png', '')
        im.crop((0, 0, mid, h)).save(os.path.join(outdir, f'p{num}_L.png'))
        im.crop((mid, 0, w, h)).save(os.path.join(outdir, f'p{num}_R.png'))
        os.remove(f)
        n += 1
    print(f'split {n} spreads -> {2*n} half-pages in {outdir}')


if __name__ == '__main__':
    main()
