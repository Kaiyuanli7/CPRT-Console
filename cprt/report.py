"""Weekly HTML report (self-contained, printable) and an Excel export of everything."""
from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import charts, db, macro, market, paths, tracker

_env = Environment(loader=FileSystemLoader(str(paths.ROOT / "templates")),
                   autoescape=select_autoescape(["html"]))
_env.filters["pct"] = lambda v, d=0: "" if v is None or v != v else f"{v * 100:.{d}f}%"
_env.filters["num"] = lambda v, d=0: "" if v is None or v != v else f"{v:,.{d}f}"
_env.filters["chg"] = lambda v, d=1: "" if v is None or v != v else f"{v * 100:+.{d}f}%".replace("-", "−")


def _nicedate(d):
    try:
        dt = datetime.fromisoformat(str(d)[:10])
        return f"{dt:%B} {dt.day}, {dt.year}"
    except ValueError:
        return d or ""


_env.filters["nicedate"] = _nicedate


def _b64(png: bytes | None) -> str | None:
    return base64.b64encode(png).decode() if png else None


def chart_pngs(s: dict, week: str | None, split_ok: bool = True) -> dict:
    df = tracker.load(s)
    out = {}
    hist = market.history()
    if len(hist) >= 2:
        out["copart_new"] = charts.lines(hist, {"us_new_7d": "Copart lots added in the last 7 days, US yards"},
                                         ylabel="Lots", start=None, fmt="png",
                                         source="Source: Copart's public search pages, scanned by the team.")
    if week and split_ok:
        table = tracker.share_table(tracker.paired(df[df["week"] == week]))
        out["split"] = charts.split_bars(table, s["benchmarks"], s["min_sample"],
                                         f"Where each insurer's salvage is listed, week of {week}")
        out["weekly"] = charts.weekly_shares(tracker.weekly_history(s, df), s["tracked_carriers"],
                                             s["min_sample"], fmt="png")
    m = macro.frame(s)
    if not m.empty:
        out["pressure"] = charts.lines(m, {"pressure_repair": "Repair & maintenance prices / used-car prices",
                                           "pressure_parts": "Parts prices / used-car prices"},
                                       ylabel="Index, 2019 = 100", hline=100, fmt="png",
                                       source="Source: BLS consumer price indexes via FRED.")
        out["insurance"] = charts.lines(m, {"insurance_cpi_yoy": "Motor vehicle insurance prices, % change on a year ago"},
                                        hline=0, fmt="png", pct=True, source="Source: BLS consumer price index.")
    return out


def build(s: dict, snap: dict) -> Path:
    t = snap.get("tracker") or {}
    week = t.get("week")
    split_problem = tracker.split_problem(t)
    pngs = {k: _b64(v) for k, v in chart_pngs(s, week, split_problem is None).items()}
    table = []
    if week and split_problem is None:
        df = tracker.load(s)
        table = tracker.share_table(tracker.paired(df[df["week"] == week])).to_dict("records")
    news_rows = db.query("SELECT title, source, published, link, score FROM news WHERE first_seen >= ? "
                         "ORDER BY score DESC, published DESC LIMIT 10", (snap["week"],))
    html = _env.get_template("report.html").render(
        snap=snap, t=t, table=table, charts=pngs, news=news_rows, split_problem=split_problem,
        cop=snap.get("copart") or market.summary(),
        pgr=db.query("SELECT * FROM pgr_monthly ORDER BY filing_date DESC LIMIT 6"),
        generated=datetime.now().strftime("%B %d, %Y at %H:%M"), settings=s)
    path = paths.data_path("reports", f"CPRT_weekly_{snap['week']}.html")
    path.write_text(html, encoding="utf-8")
    return path


def list_reports() -> list[dict]:
    folder = paths.data_path("reports", mkdir=False)
    if not folder.exists():
        return []
    files = sorted(folder.glob("CPRT_weekly_*.html"), reverse=True)
    return [{"name": f.name, "week": f.stem.replace("CPRT_weekly_", ""),
             "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d, %Y %H:%M"),
             "size_kb": round(f.stat().st_size / 1024)} for f in files]


def excel(s: dict) -> bytes:
    df = tracker.load(s)
    sheets: dict[str, pd.DataFrame] = {}
    sheets["Read me"] = pd.DataFrame({"CPRT alt-data export": [
        f"Generated {datetime.now():%Y-%m-%d %H:%M}",
        "Insurer split = share of each insurer's listed lots on Copart vs IAA, in states sampled on both sites.",
        "lo / hi = 95% Wilson confidence interval. n = lots in the sample.",
        "Listings measure inventory, not contract terms. See the Guide page for method and caveats.",
        "Copart sheets: counts Copart shows on its public search pages (lots listed per yard; lots added in the last "
        "7 days). They cover every kind of seller. 'Copart scan counts' has every number with its source page."]})
    inv = market.frame()
    if not inv.empty:
        sheets["Copart by state (latest)"] = market.by_state(inv, market.scan_dates(inv)[0])
        sheets["Copart scans by day"] = market.history(inv).reset_index(names="date")
        sheets["Copart scan counts"] = db.df("SELECT obs_date, view, dimension, key, count, source_url, captured "
                                             "FROM inventory ORDER BY obs_date DESC, view, dimension, key")
    wks = tracker.weeks(df)
    if wks:
        sheets["Insurer split (latest)"] = tracker.share_table(tracker.paired(df[df["week"] == wks[0]]))
        sheets["By state (latest)"] = tracker.state_table(s, wks[0], df)
        sheets["Weekly history"] = tracker.weekly_history(s, df)
        sheets["New lot flow"] = tracker.new_lot_flow(s, df)
        sheets["All lots"] = df.drop(columns=["date"], errors="ignore")
    m = macro.frame(s)
    if not m.empty:
        sheets["Macro"] = m.reset_index(names="date")
    for name, sql in (("Progressive monthly", "SELECT * FROM pgr_monthly ORDER BY filing_date DESC"),
                      ("DOJ disclosures", "SELECT filing_date, form, changed, similarity, disclosure, url FROM doj ORDER BY filing_date DESC"),
                      ("News", "SELECT published, title, source, score, matched, link, first_seen FROM news ORDER BY published DESC"),
                      ("SEC full-text hits", "SELECT * FROM fulltext_hits ORDER BY filing_date DESC"),
                      ("Release snippets", "SELECT ticker, filing_date, keyword, numbers, snippet, url FROM release_snippets ORDER BY filing_date DESC")):
        d = db.df(sql)
        if not d.empty:
            sheets[name] = d
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, d in sheets.items():
            d.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.freeze_panes = "A2"
            for i, col in enumerate(d.columns, 1):
                width = min(60, max(10, len(str(col)) + 2, *(len(str(v)) for v in d[col].head(200))))
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    return buf.getvalue()
