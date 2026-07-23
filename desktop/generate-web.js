// Generate the static web build (GitHub Pages) using @stlite/browser.
//
// Unlike the Electron desktop build (@stlite/desktop, offline), this produces a
// plain static site: index.html loads stlite from the jsDelivr CDN (so stlite's
// own worker/wasm come from the CDN, sidestepping any base-path issues) and mounts
// the app, fetching the corpus from ./app_files/ via relative URLs. Works at any
// path, root or project sub-path. Node built-ins only — no npm install needed.
//
// Output: desktop/web/  (git-ignored; the CI workflow deploys it to Pages).
const fs = require("fs");
const path = require("path");

const STLITE_VERSION = "1.8.1";
const repoRoot = path.resolve(__dirname, "..");
const out = path.join(__dirname, "web");
const appFiles = path.join(out, "app_files");

// --- clean + stage the app, bibliography and corpus into web/app_files/ ---
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(appFiles, { recursive: true });
fs.copyFileSync(path.join(repoRoot, "app.py"), path.join(appFiles, "streamlit_app.py"));
fs.copyFileSync(path.join(repoRoot, "references.bib"), path.join(appFiles, "references.bib"));

const SKIP = new Set(["__pycache__"]);
function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (SKIP.has(e.name)) continue;
    const s = path.join(src, e.name), d = path.join(dst, e.name);
    e.isDirectory() ? copyDir(s, d) : fs.copyFileSync(s, d);
  }
}
copyDir(path.join(repoRoot, "data"), path.join(appFiles, "data"));

// --- build the stlite files map: FS path -> { url } (fetched at load) ---
const files = {};
(function walk(dir, rel) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, e.name);
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) walk(abs, r);
    else files[r] = { url: `./app_files/${r}` };
  }
})(appFiles, "");

// --- index.html ---
const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Logograms Analyser</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@${STLITE_VERSION}/build/stlite.css" />
    <style>html, body, #root { height: 100%; margin: 0; }</style>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
    <script type="module">
      import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@${STLITE_VERSION}/build/stlite.js";
      mount(
        {
          requirements: ["pandas", "plotly", "pyyaml"],
          entrypoint: "streamlit_app.py",
          files: ${JSON.stringify(files)},
          streamlitConfig: { "client.toolbarMode": "viewer" },
        },
        document.getElementById("root"),
      );
    </script>
  </body>
</html>
`;
fs.writeFileSync(path.join(out, "index.html"), html);
fs.writeFileSync(path.join(out, "404.html"), html);
fs.writeFileSync(path.join(out, ".nojekyll"), "");
console.log(`web/ built: ${Object.keys(files).length} files mounted (stlite ${STLITE_VERSION})`);
