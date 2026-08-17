# -*- coding: utf-8 -*-
"""Regenerate the article's 18 figures from the corpus (assets/*.png).

Mirrors the app's chart style (Plotly, simple_white, Arial, spline lines) and
compute_ratios' canonical LDI (determinatives excluded, particles + 15/150/30
counted, Sumerian held out, paratext stripped). Chart types:

  trio         Figure 1     bin/macro/micro by period, one line each
  genre        Figures 2-4  one line per discipline, one chart per measure
  per_text     Figures 5, 10, 12-14, 16-18   one node per tablet, by period
  per_omen     Figure 11    one node per omen, by period (naplastu)
  single_text  Figures 6-9, 15   one node per omen of a single tablet

Run:  py -3 scripts/make_figures.py            -> writes all
      py -3 scripts/make_figures.py general-trend trend-martu-bin   -> just these
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import plotly.graph_objects as go

import compute_ratios as cr

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "assets")

PERIODS = ["Old Period", "Middle Period", "Neo Period"]
PERIOD_DISP = {"Old Period": "Old Babylonian",
               "Middle Period": "Middle Babylonian/Assyrian",
               "Neo Period": "Neo-Babylonian/Assyrian + Late Babylonian"}
PERIOD_COLOR = {"Old Period": "#1f77b4", "Middle Period": "#ff7f0e",
                "Neo Period": "#2ca02c"}
MEASURE_COLOR = {"bin": "#1f77b4", "macro": "#ff7f0e", "micro": "#2ca02c"}
GENRE_DISP = {"astrological omens": "Astrological omens",
              "diagnostic omens": "Diagnostic omens",
              "extispicy omens": "Extispicy",
              "izbu omens": "Teratological omens",
              "terrestrial omens": "Terrestrial omens"}

LAYOUT = dict(template="simple_white", font_family="Arial")


def path_files(*needles):
    """Corpus filenames whose path below data/ contains every needle."""
    out = []
    for root, _dirs, files in os.walk(DATA):
        rel = os.path.relpath(root, DATA).replace(os.sep, "/")
        if rel.startswith("_") or rel.startswith("kal5"):
            continue
        if all(n in rel for n in needles):
            out += [f for f in files if f.endswith(".txt")]
    return sorted(set(out))


print("loading corpus ...")
WORDS = pd.DataFrame(cr.load_local_data(DATA))
WORDS["__row"] = range(len(WORDS))
WORDS = WORDS[WORDS["language"] == "akkadian"]
SIGNS = pd.DataFrame(cr.load_local_signs(DATA))
SIGNS = SIGNS[SIGNS["language"] == "akkadian"]


def lp(sub):
    """Scorable word rows: contentless omens dropped, determinatives excluded."""
    sub = cr._drop_contentless(sub)
    return sub[sub["type"].isin(["logogram", "phonetic"])]


def pooled_bin(sub):
    s = lp(sub)
    return (s["type"] == "logogram").mean() if len(s) else float("nan")


def per_text_bin(sub):
    """One row per (period, filename): bin + omen count, period-ordered."""
    s = lp(sub)
    b = s.groupby(["period", "filename"])["type"].apply(lambda t: (t == "logogram").mean()).rename("bin")
    n = sub.groupby(["period", "filename"])["omen_id"].nunique().rename("n")
    t = pd.concat([b, n], axis=1).reset_index()
    t["period"] = pd.Categorical(t["period"], categories=PERIODS, ordered=True)
    return t.sort_values(["period", "filename"]).reset_index(drop=True)


def per_omen_bin(sub):
    """One row per omen in reading order: bin, period, filename."""
    s = lp(sub)
    g = s.groupby(["filename", "omen_id"])
    o = pd.DataFrame({
        "bin": g["type"].apply(lambda t: (t == "logogram").mean()),
        "order": g["__row"].min(),
        "period": g["period"].first(),
    }).reset_index()
    o["period"] = pd.Categorical(o["period"], categories=PERIODS, ordered=True)
    return o.sort_values(["period", "filename", "order"]).reset_index(drop=True)


def annotate_periods(fig, stats, whole_of):
    """Per-period 'highest / whole / lowest' labels above the points."""
    for period in [p for p in PERIODS if (stats["period"] == p).any()]:
        sub = stats[stats["period"] == period]
        xs, ys = sub["seq"], sub["bin"]
        fig.add_annotation(
            x=(float(xs.min()) + float(xs.max())) / 2, y=1.02, xref="x", yref="y",
            text=f"highest {ys.max():.2f}<br>whole {whole_of(period):.2f}<br>lowest {ys.min():.2f}",
            showarrow=False, yanchor="bottom", align="center",
            font=dict(size=10, color=PERIOD_COLOR[period]))


def period_scatter(stats, whole_of, title, xtitle, marker_size):
    """Connected scatter coloured by period, with the spill-over connector."""
    stats = stats.copy()
    stats["seq"] = range(len(stats))
    fig = go.Figure()
    here = [p for p in PERIODS if (stats["period"] == p).any()]
    for i, period in enumerate(here):
        sub = stats[stats["period"] == period]
        lx, ly = sub["seq"].tolist(), sub["bin"].tolist()
        if i + 1 < len(here):
            nxt = stats[stats["period"] == here[i + 1]].iloc[0]
            lx.append(nxt["seq"]); ly.append(nxt["bin"])
        fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines", showlegend=False, hoverinfo="skip",
                                 line=dict(width=2.5, shape="spline", smoothing=1.0,
                                           color=PERIOD_COLOR[period])))
        fig.add_trace(go.Scatter(x=sub["seq"], y=sub["bin"], mode="markers",
                                 name=PERIOD_DISP[period],
                                 marker=dict(size=marker_size, color=PERIOD_COLOR[period],
                                             line=dict(width=1, color="white"))))
    annotate_periods(fig, stats, whole_of)
    fig.update_layout(
        title=title, xaxis_title=xtitle, yaxis_title="LDI (bin)",
        yaxis=dict(range=[-0.05, 1.30], tickmode="array",
                   tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
        xaxis=dict(showticklabels=False), width=960, height=440,
        legend_title_text="Period", **LAYOUT)
    return fig


def write(fig, name):
    out = os.path.join(OUT, name + ".png")
    fig.write_image(out, scale=2)
    print("wrote", out)


# ---------------------------------------------------------------- figure builders

def fig_general_trend():
    """Figure 1: the three measures by period."""
    rows = []
    for p in PERIODS:
        w = WORDS[WORDS["period"] == p]
        g = cr.graded_ldi(SIGNS[SIGNS["period"] == p])
        rows.append({"period": PERIOD_DISP[p], "bin": pooled_bin(w),
                     "macro": g["macro"], "micro": g["micro"]})
    cdf = pd.DataFrame(rows)
    fig = go.Figure()
    for m in ("bin", "macro", "micro"):
        fig.add_trace(go.Scatter(x=cdf["period"], y=cdf[m], mode="lines+markers", name=m,
                                 line=dict(width=3, color=MEASURE_COLOR[m],
                                           shape="spline", smoothing=1.3),
                                 marker=dict(size=10)))
    fig.update_layout(margin=dict(t=14), xaxis_title="Period", yaxis_title="LDI",
                      yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                      width=960, height=460, legend_title_text="Measure", **LAYOUT)
    write(fig, "general-trend")


def fig_genre(metric):
    """Figures 2-4: one line per discipline."""
    import plotly.express as px
    rows = []
    for genre, disp in GENRE_DISP.items():
        for p in PERIODS:
            w = WORDS[(WORDS["genre"] == genre) & (WORDS["period"] == p)]
            if w.empty:
                continue
            if metric == "bin":
                v = pooled_bin(w)
            else:
                v = cr.graded_ldi(SIGNS[(SIGNS["genre"] == genre) & (SIGNS["period"] == p)])[metric]
            rows.append({"period": PERIOD_DISP[p], "discipline": disp, metric: v})
    trend = pd.DataFrame(rows)
    fig = px.line(trend, x="period", y=metric, color="discipline", markers=True,
                  category_orders={"period": [PERIOD_DISP[p] for p in PERIODS]},
                  line_shape="spline", template="simple_white")
    fig.update_traces(line=dict(width=3, shape="spline", smoothing=1.0), marker=dict(size=11))
    fig.update_layout(margin=dict(t=14), font_family="Arial", xaxis_title="Period",
                      yaxis_title=f"LDI ({metric})",
                      yaxis=dict(range=[-0.05, 1.05], dtick=0.1, tickformat=".1f", showgrid=True),
                      width=960, height=640, legend_title_text="Discipline")
    write(fig, f"general-trend-genre-{metric}")


def fig_discipline_per_text(genre, name, label):
    """Figures 5, 14, 16, 17, 18: one node per tablet across periods."""
    sub = WORDS[WORDS["genre"] == genre]
    stats = per_text_bin(sub)
    fig = period_scatter(stats, lambda p: pooled_bin(sub[sub["period"] == p]),
                         f"{label}: bin LDI per text (Old → Neo)",
                         "Texts (chronological)", 10)
    write(fig, name)


def fig_topic_per_text(files, name, label, independent=()):
    """Figures 10, 12, 13: one node per tablet of one liver/lung feature.

    `independent`: filenames kept out of the pooled line and the annotations,
    shown as grey diamonds to the right (the app's pooled_exclude convention)."""
    sub = WORDS[WORDS["filename"].isin(files) & ~WORDS["filename"].isin(independent)]
    stats = per_text_bin(sub)
    fig = period_scatter(stats, lambda p: pooled_bin(sub[sub["period"] == p]),
                         f"{label}: bin LDI per text (Old → Neo)",
                         "Texts (chronological)", 12)
    if independent:
        ind = WORDS[WORDS["filename"].isin(independent)]
        ib = per_text_bin(ind)
        fig.add_trace(go.Scatter(
            x=[len(stats) + i for i in range(len(ib))], y=ib["bin"],
            mode="markers+text", name="excluded (independent)",
            text=[f.replace(".txt", "").replace(".", " ") for f in ib["filename"]],
            textposition="top center", textfont=dict(size=10, color="#666"),
            marker=dict(size=12, color="#9e9e9e", symbol="diamond",
                        line=dict(width=1, color="white"))))
    write(fig, name)


def fig_topic_per_omen(files, name, label):
    """Figure 11: one node per omen of one feature, across periods."""
    sub = WORDS[WORDS["filename"].isin(files)]
    stats = per_omen_bin(sub).rename(columns={})
    stats = stats.copy()
    fig = period_scatter(stats, lambda p: pooled_bin(sub[sub["period"] == p]),
                         f"{label}: bin LDI per omen (Old → Neo)",
                         "Omens (chronological)", 8)
    write(fig, name)


def fig_single_text(fname, name, label):
    """Figures 6-9, 15: one node per omen of a single tablet."""
    sub = WORDS[WORDS["filename"] == fname]
    o = per_omen_bin(sub)
    o["seq"] = range(len(o))
    whole = pooled_bin(sub)
    fig = go.Figure(go.Scatter(
        x=o["seq"], y=o["bin"], mode="lines+markers",
        line=dict(width=2, color="#1f77b4"),
        marker=dict(size=10, color="#1f77b4", line=dict(width=1, color="white")),
        showlegend=False))
    fig.add_annotation(x=float(o["seq"].mean()), y=1.02, xref="x", yref="y",
                       text=f"highest {o['bin'].max():.2f}<br>whole {whole:.2f}"
                            f"<br>lowest {o['bin'].min():.2f}",
                       showarrow=False, yanchor="bottom", align="center",
                       font=dict(size=10, color="#1f77b4"))
    fig.update_layout(title=f"{label}: bin LDI per omen",
                      xaxis_title="Omen (in text order)", yaxis_title="LDI (bin)",
                      yaxis=dict(range=[-0.05, 1.30], tickmode="array",
                                 tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0], tickformat=".1f"),
                      xaxis=dict(showticklabels=False), width=960, height=440, **LAYOUT)
    write(fig, name)


FIGURES = {
    "general-trend": fig_general_trend,
    "general-trend-genre-bin": lambda: fig_genre("bin"),
    "general-trend-genre-macro": lambda: fig_genre("macro"),
    "general-trend-genre-micro": lambda: fig_genre("micro"),
    "trend-extispicy-bin": lambda: fig_discipline_per_text("extispicy omens", "trend-extispicy-bin", "Extispicy"),
    "trend-astrology-bin": lambda: fig_discipline_per_text("astrological omens", "trend-astrology-bin", "Astrological omens"),
    "trend-diagnostic-by-text-bin": lambda: fig_discipline_per_text("diagnostic omens", "trend-diagnostic-by-text-bin", "Diagnostic omens"),
    "trend-teratological-bin": lambda: fig_discipline_per_text("izbu omens", "trend-teratological-bin", "Teratological omens"),
    "trend-terrestrial-bin": lambda: fig_discipline_per_text("terrestrial omens", "trend-terrestrial-bin", "Terrestrial omens"),
    "trend-martu-bin": lambda: fig_topic_per_text(
        path_files("extispicy", "liver/martu"), "trend-martu-bin", "martu",
        independent=("VAT.8611.txt",)),
    "trend-padanu-bin": lambda: fig_topic_per_text(
        path_files("extispicy", "liver/padanu"), "trend-padanu-bin", "padanu"),
    "trend-hasu-bin": lambda: fig_topic_per_text(
        path_files("extispicy", "lung"), "trend-hasu-bin", "hasu (lung)"),
    "trend-naplastu-per-omen-bin": lambda: fig_topic_per_omen(
        path_files("extispicy", "liver/naplastu"), "trend-naplastu-per-omen-bin", "naplastu/manzazu"),
    "trend-cusas-18-25-bin": lambda: fig_single_text("CUSAS-18.25.txt", "trend-cusas-18-25-bin", "CUSAS 18 25"),
    "trend-vat-10418-bin": lambda: fig_single_text("VAT.10418.txt", "trend-vat-10418-bin", "VAT 10418"),
    "trend-vat-10206-bin": lambda: fig_single_text("VAT.10206.txt", "trend-vat-10206-bin", "VAT 10206"),
    "trend-vat-8611-bin": lambda: fig_single_text("VAT.8611.txt", "trend-vat-8611-bin", "VAT 8611"),
    "trend-BM-86381-bin": lambda: fig_single_text("BM.86381.txt", "trend-BM-86381-bin", "BM 86381"),
}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(FIGURES)
    for w in wanted:
        if w not in FIGURES:
            print("unknown figure:", w); continue
        FIGURES[w]()
