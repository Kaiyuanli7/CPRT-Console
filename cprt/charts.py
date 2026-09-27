"""Charts drawn server-side (matplotlib) so they work offline: SVG for the console, PNG for slides."""
from __future__ import annotations

import io
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402
import pandas as pd  # noqa: E402

COPART = "#2350C9"
IAA = "#C4412F"
INK = "#1E2227"
MUTED = "#6B7079"
RULE = "#D9DCD6"
AMBER = "#D99A0B"
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
# Lines for insurers and macro series: never Copart blue or IAA red, which carry meaning elsewhere.
SERIES = ["#1E2227", "#2A7F7A", "#8C5E3C", "#7B5EA7", "#6B7F2A", "#7A8A99"]

plt.rcParams.update({
    "font.family": ["Barlow", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 10, "axes.edgecolor": RULE, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#ECEDEA", "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "svg.fonttype": "path", "figure.dpi": 100,
})


def _out(fig, fmt: str):
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, bbox_inches="tight", dpi=180 if fmt == "png" else 100, transparent=(fmt == "svg"))
    plt.close(fig)
    if fmt == "svg":
        svg = buf.getvalue().decode("utf-8")
        return svg[svg.find("<svg"):]
    return buf.getvalue()


def lines(df: pd.DataFrame, cols: dict[str, str], ylabel: str = "", hline: float | None = None,
          start: str | None = "2015-01-01", fmt: str = "svg", height: float = 3.3, pct: bool = False,
          colors: list[str] | None = None, source: str | None = None, emphasize_first: bool = False,
          title: str = ""):
    """Line chart of df[col] for each col in `cols` ({column: legend label}). Index must be dates."""
    data = df.loc[start:] if start is not None and len(df) else df
    fig, ax = plt.subplots(figsize=(9.6, height))
    colors = colors or SERIES
    drawn = 0
    for i, (col, label) in enumerate(cols.items()):
        if col in data and data[col].notna().any():
            s = data[col].dropna()
            ax.plot(s.index, s.values, color=colors[i % len(colors)], label=label,
                    linewidth=3.0 if (emphasize_first and i == 0) else 2.0,
                    marker="o" if len(s) < 16 else None, markersize=4)
            drawn += 1
    if hline is not None:
        ax.axhline(hline, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    if pct:
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=None))
    else:  # 428,262 rather than 4.3e5
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"))
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, loc="left", fontsize=12, color=INK)
    if isinstance(data.index, pd.DatetimeIndex) and len(data):
        idx = data.dropna(how="all", subset=[c for c in cols if c in data]).index if drawn else data.index
        span = (idx.max() - idx.min()).days if len(idx) else 0
        if 0 < len(idx) < 16 and span < 900:  # few points: label each one
            gap = pd.Series(idx).diff().dt.days.median() if len(idx) > 1 else 7
            ax.set_xticks(idx)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d" if gap < 25 else "%b %Y"))
        else:
            ax.xaxis.set_major_locator(mdates.YearLocator() if span > 900 else mdates.AutoDateLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y" if span > 900 else "%b %Y"))
    if drawn > 1:
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.13), fontsize=9, ncol=min(drawn, 3), handlelength=1.8)
    if source:
        fig.text(0.0, -0.02 if drawn < 2 else -0.12, source, fontsize=8, color=MUTED, ha="left")
    return _out(fig, fmt)


def weekly_shares(history: pd.DataFrame, carriers_list: list[str], min_n: int, fmt: str = "svg"):
    """Copart share of each insurer's lots, week by week."""
    h = history[(history["carrier"].isin(carriers_list + ["All insurers"])) & (history["n"] >= min_n)].copy()
    if h.empty or h["week"].nunique() < 2:
        return None
    h["week"] = pd.to_datetime(h["week"])
    wide = h.pivot_table(index="week", columns="carrier", values="share") * 100
    order = [c for c in ["All insurers"] + carriers_list if c in wide]
    return lines(wide, {c: c for c in order}, ylabel="Copart share of listed lots", hline=50, start=None,
                 fmt=fmt, pct=True, colors=[INK] + SERIES[1:], emphasize_first="All insurers" in order)


def split_bars(table: pd.DataFrame, benchmarks: dict, min_n: int, title: str = "", fmt: str = "png"):
    """The console's split bar for slides: blue = Copart share, red = IAA, whisker = 95% CI."""
    t = table[(table["n"] >= min_n) & ~table["carrier"].isin(["Unknown"])].sort_values("share")
    if t.empty:
        return None
    fig, ax = plt.subplots(figsize=(8.2, 0.55 * len(t) + 1.2))
    y = list(range(len(t)))
    ax.barh(y, t["share"] * 100, color=COPART, height=0.62)
    ax.barh(y, (1 - t["share"]) * 100, left=t["share"] * 100, color=IAA, height=0.62)
    ax.errorbar(t["share"] * 100, y, xerr=[(t["share"] - t["lo"]) * 100, (t["hi"] - t["share"]) * 100],
                fmt="none", ecolor=INK, elinewidth=1.4, capsize=4)
    labelled = False
    for i, (_, r) in enumerate(t.iterrows()):
        if r["carrier"] in benchmarks:
            ax.plot(benchmarks[r["carrier"]][0] * 100, i, marker="D", color=AMBER, markersize=8,
                    markeredgecolor=INK, linestyle="none", label=None if labelled else "Expert-call claim")
            labelled = True
        ax.text(101, i, f"{r['share']:.0%}  (n={int(r['n'])})", va="center", fontsize=9, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(t["carrier"])
    ax.set_xlim(0, 100)
    ax.grid(False)
    ax.set_xlabel("Share of the insurer's listed lots: Copart (blue) vs IAA (red), 95% interval")
    if title:
        ax.set_title(title, loc="left", fontsize=12, color=INK)
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend(loc="upper right", bbox_to_anchor=(1.0, -0.16), fontsize=9)
    fig.text(0.0, -0.03, "Source: team sample of public Copart and IAA listings.", fontsize=8, color=MUTED)
    return _out(fig, fmt)
