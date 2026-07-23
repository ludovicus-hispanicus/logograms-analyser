// Post-process the stlite build for static hosting under a sub-path
// (e.g. GitHub Pages project site https://<user>.github.io/<repo>/).
//
// The @stlite/desktop build emits ABSOLUTE asset URLs ("/assets/…") which resolve
// to the domain root and 404 under a sub-path. stlite already derives its own
// base path from window.location.pathname (so app_files / data / site-packages
// load correctly), so we only need to relativise the two hard-coded "/assets/…"
// references: the entry <script>/<link> in index.html and the worker URL inside
// the bundled JS. After this, everything resolves relative to index.html, so the
// bundle works at any path (root or sub-path). Idempotent.
const fs = require("fs");
const path = require("path");

const build = path.join(__dirname, "build");
const html = path.join(build, "index.html");

// 1) index.html: "/assets/…"  ->  "assets/…"  (relative to the page directory)
let h = fs.readFileSync(html, "utf8");
h = h.replace(/(src|href)="\/assets\//g, '$1="assets/');
// Title (cosmetic — the desktop shell says "Stlite Desktop")
h = h.replace(/<title>[^<]*<\/title>/, "<title>Logograms Analyser</title>");
fs.writeFileSync(html, h);

// 2) bundled JS: the worker is loaded as new URL("/assets/worker-….js", import.meta.url).
//    import.meta.url already points inside assets/, so drop the leading "/assets/"
//    to make it relative to the entry script.
const assetsDir = path.join(build, "assets");
let patchedWorker = 0;
for (const f of fs.readdirSync(assetsDir)) {
  if (!f.endsWith(".js")) continue;
  const p = path.join(assetsDir, f);
  let js = fs.readFileSync(p, "utf8");
  const before = js;
  js = js.replace(/\/assets\/(worker-[A-Za-z0-9_-]+\.js)/g, "$1");
  if (js !== before) { fs.writeFileSync(p, js); patchedWorker++; }
}

// 3) SPA fallback + disable Jekyll (so the _-prefixed / underscore paths are served).
fs.copyFileSync(html, path.join(build, "404.html"));
fs.writeFileSync(path.join(build, ".nojekyll"), "");

console.log(`postbuild-web: relativised index.html + worker refs in ${patchedWorker} JS file(s); wrote 404.html + .nojekyll`);
