#!/usr/bin/env python
"""Render two-page-spread PDF pages and split each into left/right book pages,
using PyMuPDF (works on permission-restricted PDFs where pdftoppm refuses).

Usage:  python scripts/split_spread_fitz.py INPUT.pdf OUTDIR DPI IDX [IDX ...]
  IDX = 0-based PDF page indices to render (each = one L+R spread).
Outputs OUTDIR/p{book}_L.png (left/lower book page) and p{book}_R.png (right).
Book page is derived from the anchor PDF-idx6 == book p.8 (book_L = 2*idx - 4);
pass --raw to name by PDF page instead.
"""
import sys, os, fitz

def main():
    pdf, outdir, dpi = sys.argv[1], sys.argv[2], int(sys.argv[3])
    raw = '--raw' in sys.argv
    idxs = [int(a) for a in sys.argv[4:] if not a.startswith('--')]
    os.makedirs(outdir, exist_ok=True)
    d = fitz.open(pdf)
    if d.needs_pass:
        d.authenticate('')
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for idx in idxs:
        page = d[idx]
        pw, ph = page.rect.width, page.rect.height   # page coords (points)
        if raw:
            tagL, tagR = f'pdf{idx+1:03d}_L', f'pdf{idx+1:03d}_R'
        else:
            bl = 2 * idx - 4
            tagL, tagR = f'p{bl:03d}_L', f'p{bl+1:03d}_R'
        page.get_pixmap(matrix=mat, clip=fitz.Rect(0, 0, pw/2, ph)).save(
            os.path.join(outdir, tagL + '.png'))
        page.get_pixmap(matrix=mat, clip=fitz.Rect(pw/2, 0, pw, ph)).save(
            os.path.join(outdir, tagR + '.png'))
        print(f'PDF p{idx+1} -> {tagL}.png + {tagR}.png  ({int(pw*zoom)}x{int(ph*zoom)})')

if __name__ == '__main__':
    main()
