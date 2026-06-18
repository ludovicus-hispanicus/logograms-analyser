"""Restoration-sensitivity check for the LDI.

Some tablets (notably the broken Middle Assyrian eclipse text BM 121034 =
Rochberg Text E) are heavily *restored* by the editor from parallels. The
standard loader strips '[' and ']' and therefore counts restored material as if
it were preserved. This script recomputes the LDI on a PRESERVED-ONLY variant,
where every fully-restored span '[ ... ]' is replaced with '...' (an ignored
token) before tokenizing. Damaged-but-legible signs (marked '#') are kept,
since they are physically on the tablet.

It reports, per file:
  - LDI(full)      : restored material counted  (= current pipeline value)
  - LDI(preserved) : restored material dropped
  - restoration share of countable tokens
so we can see how much of the "high" astrological LDI is an artifact of
reconstruction rather than the tablet itself.
"""
import sys
import yaml
import pandas as pd
from compute_ratios import annotate_omen, ldi


def split_frontmatter(content):
    meta = {}
    body = content
    if content.startswith('---'):
        ps = content.split('---', 2)
        if len(ps) >= 3:
            body = ps[2]
            try:
                fm = yaml.safe_load(ps[1])
                if fm:
                    meta = fm
            except yaml.YAMLError:
                pass
    return meta, body


def tokenize_body(body, meta, preserved_only=False):
    anns = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith('@') or line.startswith('$') or line.startswith('#'):
            continue
        # annotate_omen applies strip_restored() itself when preserved_only=True
        anns.extend(annotate_omen(line, omen_id='_', metadata=dict(meta),
                                  preserved_only=preserved_only))
    return pd.DataFrame(anns)


def report(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    meta, body = split_frontmatter(content)
    meta = dict(meta)
    meta.setdefault('filename', path.split('/')[-1].split('\\')[-1])

    full = tokenize_body(body, meta, preserved_only=False)
    pres = tokenize_body(body, meta, preserved_only=True)

    rf, lf, tf = ldi(full)
    rfx, _, tfx = ldi(full, exclude_particles=True)
    rp, lp, tp = ldi(pres)
    rpx, _, tpx = ldi(pres, exclude_particles=True)

    print("=" * 72)
    print(f"{meta['filename']}   ({meta.get('period','?')}, {meta.get('genre','?')})")
    print("=" * 72)
    print(f"{'variant':<16}{'LDI':>8}{'LDI-part':>10}{'logos':>8}{'tokens':>8}")
    print(f"{'full (restored)':<16}{rf:>8.3f}{rfx:>10.3f}{lf:>8}{tf:>8}")
    print(f"{'preserved only':<16}{rp:>8.3f}{rpx:>10.3f}{lp:>8}{tp:>8}")
    drop = tf - tp
    print(f"\nrestored/lost tokens dropped : {drop} of {tf}  ({drop/tf:.0%} of countable material)")
    if tp:
        print(f"LDI shift (full -> preserved): {rf:.3f} -> {rp:.3f}  (Δ {rp-rf:+.3f})")
    else:
        print("preserved-only material is empty (tablet almost wholly restored)")
    print()


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "data/middle/astrology/BM.121034.txt",
        "data/middle/astrology/MS.3119.txt",
        "data/new/astrology/IM.124485.txt",
        "data/old/astrology/BM.86381.txt",
        "data/old/astrology/BM.22696.txt",
    ]
    for t in targets:
        report(t)
