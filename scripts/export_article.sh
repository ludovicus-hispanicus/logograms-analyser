#!/usr/bin/env bash
# Export docs/The-Logographic-Shift.md to a review PDF with all 18 figures.
#
#   bash scripts/export_article.sh            -> docs/The-Logographic-Shift-draft-<today>.pdf
#   bash scripts/export_article.sh out.pdf    -> writes to out.pdf
#
# The manuscript itself is deliberately untracked (see .gitignore); only this
# exporter lives in the repo. Figures are read from assets/ via the ../assets/
# links in the .md, so nothing is embedded in the manuscript file.
#
# Requires: pandoc + a TeX installation providing xelatex, and the Charis SIL
# font (ships with TeX Live). Charis SIL is used because it is the only common
# serif face covering everything the article needs: the half brackets U+2E22 /
# U+2E23, subscript digits, and h-breve.
set -euo pipefail

cd "$(dirname "$0")/.."
SRC="docs/The-Logographic-Shift.md"
OUT="${1:-docs/The-Logographic-Shift-draft-$(date +%Y-%m-%d).pdf}"

[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/header.tex" <<'EOF'
\usepackage{needspace}
EOF

# A chart and its "**Figure N.**" caption are separate blocks, so LaTeX may break
# the page between them; reserve room for the pair before each chart.
cat > "$TMP/keep-figure-with-caption.lua" <<'EOF'
function Para(el)
  if #el.content == 1 and el.content[1].t == "Image" then
    return { pandoc.RawBlock("latex", "\\needspace{0.45\\textheight}"), el }
  end
end
EOF

# -implicit_figures keeps each chart inline instead of turning it into a float:
# floats drift to a later page, away from the caption paragraph beneath them,
# and pandoc would also render the alt text as a second, duplicate caption.
# --resource-path: the figure links are "../assets/*.png", written relative to
# docs/, but pandoc runs from the repo root -- resolve them against docs/.
pandoc "$SRC" \
  -f markdown-implicit_figures \
  --resource-path="docs" \
  --lua-filter="$TMP/keep-figure-with-caption.lua" \
  -H "$TMP/header.tex" \
  -o "$OUT" \
  --pdf-engine=xelatex \
  --toc --toc-depth=2 \
  -V mainfont="Charis SIL" \
  -V papersize=a4 -V geometry:margin=2.5cm \
  -V fontsize=11pt \
  -V colorlinks=true -V linkcolor=RoyalBlue -V toccolor=black

echo "wrote $OUT"
