#!/usr/bin/env python3
"""Generate a manifest of every text in data/ with its omen count.

Single source of truth for "how many omens does each text / period / genre
have". Re-run after any change to the corpus so the article tables can be
checked against it:

    py -3 scripts/corpus_manifest.py

Writes:
    data/corpus-manifest.md   human-readable, grouped by period/genre with subtotals
    data/corpus_manifest.csv  one row per text (file, group, period, genre, omens, excluded)

Counting reuses compute_ratios.load_local_data (the same omen segmentation the
app uses), so the numbers match the tool. Excluded texts (comparanda, KAL 5
supplement) are counted too — with `exclude` stripped in a temp copy — and
listed separately, flagged, so they are never silently folded into the totals.
"""
import os
import re
import sys
import tempfile

import pandas as pd

# Import the app's loader (this script lives in scripts/, package root is ..)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compute_ratios as cr  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# app.py maps this combined label to Neo; compute_ratios.PERIOD_MAPPING does not,
# so fold it here to keep EAE 55/57 in the Neo bucket.
PERIOD_FOLD = {"Neo-Assyrian / Late Babylonian": "Neo Period"}
PERIOD_ORDER = ["Old Period", "Middle Period", "Neo Period"]


def group_of(relpath, excluded):
    """Bucket a text: comparandum / kal5 / held-out / corpus.

    `held-out` = a text in a period folder (old/middle/new) that carries its own
    `exclude: true` (e.g. too fragmentary) — kept in the tree but out of the counts.
    """
    top = relpath.replace("\\", "/").split("/")[0]
    if top == "_comparanda":
        return "comparandum"
    if top == "kal5":
        return "kal5"
    if excluded:
        return "held-out"
    return "corpus"


def per_file(df):
    """filename -> (period, genre, omen_count) from a loaded annotation frame."""
    out = {}
    for fn, g in df.groupby("filename"):
        raw_period, raw_genre = g["period"].iloc[0], g["genre"].iloc[0]
        if pd.isna(raw_period) or pd.isna(raw_genre):
            # a draft saved without period/discipline (e.g. an app scratch file):
            # not part of the corpus yet, so leave it out rather than crash.
            print(f"  [skip] {fn}: missing period/genre frontmatter (draft?)")
            continue
        period = PERIOD_FOLD.get(raw_period, raw_period)
        out[fn] = {"period": period, "genre": str(raw_genre),
                   "omens": int(g["omen_id"].nunique())}
    return out


def load_frame(base):
    anns = cr.load_local_data(base)
    return pd.DataFrame(anns) if anns else pd.DataFrame(
        columns=["filename", "period", "genre", "omen_id"])


def main():
    # Walk data/: record every .txt and whether it is individually excluded.
    excluded_rels, rel_of_name = set(), {}
    for root, _, files in os.walk(DATA):
        for f in files:
            if not f.endswith(".txt"):
                continue
            rel = os.path.relpath(os.path.join(root, f), DATA)
            rel_of_name[f] = rel
            if re.search(r"^\s*exclude:\s*true", open(os.path.join(root, f),
                                                       encoding="utf-8").read(), re.M):
                excluded_rels.add(rel)

    # Pass 1: non-excluded texts (the counted corpus).
    counts = per_file(load_frame(DATA))

    # Pass 2: excluded texts — strip `exclude:` into a temp copy so the loader
    # will segment them too, then merge (without overriding pass-1 counts).
    with tempfile.TemporaryDirectory() as tmp:
        for rel in excluded_rels:
            txt = open(os.path.join(DATA, rel), encoding="utf-8").read()
            txt = re.sub(r"^[ \t]*exclude:\s*true.*$\n?", "", txt, flags=re.M)
            dst = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "w", encoding="utf-8").write(txt)
        if excluded_rels:
            for fn, rec in per_file(load_frame(tmp)).items():
                counts.setdefault(fn, rec)

    # Assemble rows
    rows = []
    for fn, rec in counts.items():
        rel = rel_of_name.get(fn, fn)
        grp = group_of(rel, rel in excluded_rels)
        rows.append({"file": fn, "group": grp, "period": rec["period"],
                     "genre": rec["genre"], "omens": rec["omens"],
                     "excluded": grp != "corpus"})
    rows.sort(key=lambda r: (r["group"] != "corpus", r["period"], r["genre"], r["file"]))

    # --- CSV ---
    csv_path = os.path.join(DATA, "corpus_manifest.csv")
    pd.DataFrame(rows, columns=["file", "group", "period", "genre", "omens",
                                "excluded"]).to_csv(csv_path, index=False)

    # --- Markdown ---
    corpus = [r for r in rows if r["group"] == "corpus"]
    heldout = [r for r in rows if r["group"] == "held-out"]
    comp = [r for r in rows if r["group"] == "comparandum"]
    kal5 = [r for r in rows if r["group"] == "kal5"]

    L = ["# Corpus manifest",
         "",
         "Auto-generated by `scripts/corpus_manifest.py` — **do not edit by hand**; "
         "re-run the script after any change to `data/`. Omen counts use the same "
         "segmentation as the app (`compute_ratios.load_local_data`).",
         ""]

    def period_key(p):
        return PERIOD_ORDER.index(p) if p in PERIOD_ORDER else len(PERIOD_ORDER)

    # Counted corpus, grouped period -> genre
    g_tot_o = sum(r["omens"] for r in corpus)
    g_tot_t = len(corpus)
    L += [f"## Counted corpus — {g_tot_o} omens in {g_tot_t} texts", ""]
    periods = sorted({r["period"] for r in corpus}, key=period_key)
    for p in periods:
        pr = [r for r in corpus if r["period"] == p]
        L += [f"### {p} — {sum(r['omens'] for r in pr)} omens ({len(pr)} texts)", ""]
        for gen in sorted({r["genre"] for r in pr}):
            gr = sorted((r for r in pr if r["genre"] == gen), key=lambda r: r["file"])
            L += [f"**{gen}** — {sum(r['omens'] for r in gr)} omens ({len(gr)} texts)", ""]
            L += [f"- {r['file']} — {r['omens']}" for r in gr]
            L += [""]

    # Period x genre summary table
    L += ["## Summary: omens (texts) by period × genre", ""]
    genres = sorted({r["genre"] for r in corpus})
    header = "| Genre | " + " | ".join(PERIOD_ORDER) + " | Total |"
    L += [header, "| " + " | ".join(["---"] * (len(PERIOD_ORDER) + 2)) + " |"]
    col_o = {p: 0 for p in PERIOD_ORDER}
    col_t = {p: 0 for p in PERIOD_ORDER}
    for gen in genres:
        cells, ro, rt = [], 0, 0
        for p in PERIOD_ORDER:
            gr = [r for r in corpus if r["genre"] == gen and r["period"] == p]
            o = sum(r["omens"] for r in gr)
            cells.append(f"{o} ({len(gr)})" if gr else "–")
            ro += o
            rt += len(gr)
            col_o[p] += o
            col_t[p] += len(gr)
        L.append(f"| {gen} | " + " | ".join(cells) + f" | **{ro} ({rt})** |")
    tot_cells = " | ".join(f"**{col_o[p]} ({col_t[p]})**" for p in PERIOD_ORDER)
    L.append(f"| **Total** | {tot_cells} | **{g_tot_o} ({g_tot_t})** |")
    L += [""]

    # Excluded groups
    for title, grp in [("Held out of counts (in corpus folders, `exclude: true`)", heldout),
                       ("Comparanda (excluded from counts)", comp),
                       ("KAL 5 supplement (excluded from main counts)", kal5)]:
        if not grp:
            continue
        L += [f"## {title} — {sum(r['omens'] for r in grp)} omens in {len(grp)} texts", ""]
        for r in sorted(grp, key=lambda r: r["file"]):
            L.append(f"- {r['file']} — {r['omens']}  ({r['genre']}, {r['period']})")
        L += [""]

    md_path = os.path.join(DATA, "corpus-manifest.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(L))

    print(f"corpus: {g_tot_o} omens / {g_tot_t} texts")
    for p in periods:
        pr = [r for r in corpus if r["period"] == p]
        print(f"  {p:14s} {sum(r['omens'] for r in pr):6d} omens  {len(pr):3d} texts")
    print(f"held-out: {len(heldout)}  comparanda: {len(comp)}  kal5: {len(kal5)}")
    print(f"wrote {os.path.relpath(md_path, ROOT)} and {os.path.relpath(csv_path, ROOT)}")


if __name__ == "__main__":
    main()
