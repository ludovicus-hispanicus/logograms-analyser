"""Diachronic LINE chart (app style) — running lung omens across Old→Middle→Neo,
with the lung MODELS / orientation tablets overlaid as markers.

Matches app.py's trend charts: Plotly, simple_white, spline lines (width 3),
y-axis 0–1.05. Reuses compute_ratios (canonical LDI: det excluded, particles +
15/150/30 counted, Sumerian held out). Writes assets/lung-models-ldi.png.
"""
import os, sys, glob, tempfile, shutil, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import plotly.graph_objects as go
from compute_ratios import load_local_data, ldi

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(BASE, "data")
PERIODS = ["Old Period", "Middle Period", "Neo Period"]
DISP = {"Old Period": "Old<br>Babylonian",
        "Middle Period": "Middle<br>Bab./Assyr.",
        "Neo Period": "Neo<br>Bab./Assyr. + LB"}

def bin_of(df, fnames):
    s = df[df['filename'].isin(fnames) & (df['language'] == 'akkadian')]
    return ldi(s)[0] if len(s) else None

# running lung omens by period
main = pd.DataFrame(load_local_data(ROOT))
lung = set(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "**", "extispicy", "lung", "*.txt"), recursive=True))
omen = [bin_of(main[main['period'] == p], lung) for p in PERIODS]

# the two model / orientation comparanda (exclude:true → load copies)
tmp = tempfile.mkdtemp(); os.makedirs(os.path.join(tmp, "new", "extispicy"), exist_ok=True)
for f in ("CTN4-60-lung-model.txt", "KAR.444-lung-model.txt", "K.2858-liver-lung-model.txt"):
    t = open(os.path.join(ROOT, "_comparanda", f), encoding="utf-8").read()
    open(os.path.join(tmp, "new", "extispicy", f), "w", encoding="utf-8").write(re.sub(r'^exclude:.*\n', '', t, flags=re.M))
comp = pd.DataFrame(load_local_data(tmp)); shutil.rmtree(tmp, ignore_errors=True)
kar = bin_of(comp, ["KAR.444-lung-model.txt"])       # Middle Assyrian
ctn = bin_of(comp, ["CTN4-60-lung-model.txt"])       # Neo
k28 = bin_of(comp, ["K.2858-liver-lung-model.txt"])  # Neo (Koch 107)

x = [DISP[p] for p in PERIODS]
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=x, y=omen, mode="lines+markers", name="running lung omens",
    line=dict(width=3, color="#1f77b4", shape="spline", smoothing=1.3),
    marker=dict(size=11, color="#1f77b4"),
    hovertemplate="running omens<br>%{x}<br>LDI = %{y:.2f}<extra></extra>"))
fig.add_trace(go.Scatter(
    x=[DISP["Middle Period"], DISP["Neo Period"], DISP["Neo Period"]], y=[kar, ctn, k28],
    mode="markers+text", name="models / orientation",
    marker=dict(size=15, color="#d62728", symbol="diamond", line=dict(width=1, color="white")),
    text=["KAR 444", "CTN 4 60", "K 2858"], textposition=["bottom center", "top center", "bottom center"],
    textfont=dict(size=11, color="#555"),
    hovertemplate="%{text}<br>%{x}<br>LDI = %{y:.2f}<extra></extra>"))

fig.update_layout(
    template="simple_white", font_family="Arial",
    title="Lung: running omens vs. models & orientation tablets (bin LDI)",
    xaxis_title="Period", yaxis_title="LDI — bin",
    yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
    width=780, height=460, hovermode="closest",
    legend=dict(title_text="", yanchor="top", y=0.99, xanchor="left", x=0.02))

out = os.path.join(BASE, "assets", "lung-models-ldi.png")
fig.write_image(out, scale=2)
print("wrote", out)
print(f"omens OB={omen[0]:.3f} MB={omen[1]:.3f} Neo={omen[2]:.3f} | KAR444={kar:.3f} CTN460={ctn:.3f}")
