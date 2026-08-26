# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the full-featured desktop build: real CPython, so the
# eBL API fetch works (real sockets, no browser CORS), the streamlit-ace editor
# ships, and imported texts persist to the real _internal/data/ folder.
# The lightweight fully-offline Electron build lives in desktop/ (stlite; no network).
#
# Build (from the repo root):
#   py -3.12 -m PyInstaller packaging/desktop_exe.spec --noconfirm ^
#       --distpath packaging/dist --workpath packaging/build
# Output: packaging/dist/Logograms Analyser/Logograms Analyser.exe
# Distribute the whole folder (zip it); the app is portable, no installer needed.

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Only the files the app actually reads at runtime — assets/ (2.3 GB of article
# figures) and docs/ (the unpublished article) must NOT be bundled wholesale.

# The corpus, file by file rather than as one tree: data/_custom is where the
# app files texts the reader imports, so a build machine that has been used to
# try the app would otherwise ship someone's private corpus inside the exe. The
# packaged app creates the folder itself on the first import.
def _corpus_files():
    src = os.path.join(ROOT, "data")
    custom = os.path.join(src, "_custom")
    out = []
    for dp, dirs, fs in os.walk(src):
        if os.path.commonpath([os.path.abspath(dp), os.path.abspath(custom)]) == os.path.abspath(custom):
            dirs[:] = []
            continue
        rel = os.path.relpath(dp, src)
        dest = "data" if rel == "." else os.path.join("data", rel)
        out += [(os.path.join(dp, f), dest) for f in fs]
    return out

datas = [
    (os.path.join(ROOT, "app.py"), "."),
    (os.path.join(ROOT, "references.bib"), "."),
    (os.path.join(ROOT, "assets", "logo"), os.path.join("assets", "logo")),
    (os.path.join(ROOT, "assets", "trend-vat-10418-bin.png"), "assets"),
    (os.path.join(ROOT, "docs", "catalogue-of-sources.md"), "docs"),
    (os.path.join(ROOT, "docs", "kal5-ldi-by-tradition.csv"), "docs"),
] + _corpus_files()
binaries = []
hiddenimports = [
    "streamlit.web.cli",
    # pywebview's Windows backends; resolved lazily at runtime, so named here.
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    # app.py is bundled as data (streamlit runs it by path), so import analysis
    # never sees it — its imports must be declared by hand.
    "streamlit_ace",
    "pandas",
    "plotly",
    "plotly.express",
    "plotly.graph_objects",
    "plotly.io",
    "yaml",
]

# Streamlit needs its static frontend, package data and dist metadata.
d, b, h = collect_all("streamlit")
datas += d
binaries += b
hiddenimports += h

# Component/package data resolved at runtime rather than by import analysis.
datas += collect_data_files("streamlit_ace")   # bundled ace editor frontend
datas += collect_data_files("plotly")
datas += collect_data_files("altair")          # vega schema json
for dist in ("streamlit_ace", "altair"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # The shared Python install carries an ML/vision stack the app never touches;
    # optional-dependency probes in pandas/plotly/streamlit would drag it all in
    # (torch alone is 3.5 GB in the bundle).
    excludes=[
        "torch", "torchvision", "torchaudio", "triton", "bitsandbytes",
        "transformers", "tokenizers", "safetensors", "accelerate", "peft",
        "datasets", "polars", "llvmlite", "numba", "cv2", "imageio",
        "imageio_ffmpeg", "av", "onnxruntime", "onnx", "scipy", "sklearn",
        "matplotlib", "sympy", "networkx", "numexpr", "bottleneck",
        "IPython", "jupyter", "notebook", "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Logograms Analyser",
    icon=os.path.join(ROOT, "desktop", "res", "icon.ico"),
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Logograms Analyser",
)
