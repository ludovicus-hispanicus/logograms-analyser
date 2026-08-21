// Stages the Streamlit app into the desktop/ project root for stlite packaging.
// Copies app.py (as streamlit_app.py) + the data/ corpus from the repo root.
// These staged files are git-ignored; stlite bundles them into the Electron app.
const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const dest = __dirname;

// Clean only the generated artifacts (never touch package.json, node_modules, etc.)
fs.rmSync(path.join(dest, "streamlit_app.py"), { force: true });
fs.rmSync(path.join(dest, "references.bib"), { force: true });
fs.rmSync(path.join(dest, "data"), { recursive: true, force: true });
fs.rmSync(path.join(dest, "assets"), { recursive: true, force: true });
fs.rmSync(path.join(dest, "docs"), { recursive: true, force: true });

// Entry point: app.py -> streamlit_app.py
fs.copyFileSync(path.join(repoRoot, "app.py"), path.join(dest, "streamlit_app.py"));

// Bibliography source for the Bibliography tab
fs.copyFileSync(path.join(repoRoot, "references.bib"), path.join(dest, "references.bib"));

// Bundle the corpus (data/), skipping caches and the data license file
const SKIP = new Set(["__pycache__"]);
function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}
copyDir(path.join(repoRoot, "data"), path.join(dest, "data"));

// The few assets the app reads at runtime (the logo and the one figure the LDI
// page embeds) — never the whole assets/ folder (gigabytes of article figures).
copyDir(path.join(repoRoot, "assets", "logo"), path.join(dest, "assets", "logo"));
fs.copyFileSync(path.join(repoRoot, "assets", "trend-vat-10418-bin.png"),
                path.join(dest, "assets", "trend-vat-10418-bin.png"));

// Supplementary downloads offered on the Sources tab (exists-guarded in app.py) —
// only these two files, never docs/ wholesale (it holds the unpublished article).
fs.mkdirSync(path.join(dest, "docs"), { recursive: true });
for (const f of ["catalogue-of-sources.md", "kal5-ldi-by-tradition.csv"]) {
  fs.copyFileSync(path.join(repoRoot, "docs", f), path.join(dest, "docs", f));
}

console.log("Staged streamlit_app.py, references.bib, data/, assets/ and docs/ into", dest);
