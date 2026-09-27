"""CPRT console: a local web app at http://127.0.0.1:5055.

Start it by double-clicking "Open CPRT Console.command" (or `python app.py`).
It only listens on this computer; nothing is exposed to the network.
"""
from __future__ import annotations

import io
import json
import re
import socket
import sys
import threading
import webbrowser
from datetime import date, datetime
from urllib.parse import urlparse

import pandas as pd
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from cprt import (capture, carriers, charts, db, infer, jobs, macro, market, paths, report, scheduler, sec,
                  settings, tracker, weekly)

PORT = 5055
app = Flask(__name__, template_folder=str(paths.ROOT / "templates"), static_folder=str(paths.ROOT / "static"))
app.secret_key = "cprt-console-local"  # flash messages only; the app listens on 127.0.0.1

NAV = [("/", "This week"), ("/inventory", "Copart inventory"), ("/tracker", "Insurer tracker"), ("/macro", "Macro"),
       ("/filings", "Filings"), ("/news", "News"), ("/reports", "Reports"), ("/settings", "Settings"),
       ("/help", "How to use"), ("/guide", "Guide")]
JOB_ARGS = {"weekly": ["weekly"], "news": ["update", "news"], "macro": ["update", "macro"],
            "sec": ["update", "sec"], "capture_auto": ["capture", "auto"], "report": ["report"], "scan": ["scan"],
            "scan_guided": ["capture", "guided", "--platform", "copart", "--url", market.SCAN_PAGES["listed"]]}
INVENTORY_CHARTS = {"copart_new": ("us_new_7d", "Copart lots added in the last 7 days, US yards"),
                    "copart_listed": ("us_listed", "Copart lots listed in US yards")}
PLATFORMS = {"copart": "Copart", "iaa": "IAA"}
GROUP_LABELS = {"Non-insurance": "Non-insurance sellers", "Other insurer": "Other insurers"}
MACRO_CHARTS = {
    "pressure": ({"pressure_repair": "Repair & maintenance prices / used-car prices",
                  "pressure_parts": "Parts prices / used-car prices"},
                 {"ylabel": "Index, 2019 = 100", "hline": 100}),
    "spread": ({"repair_cpi_yoy": "Repair & maintenance prices", "used_car_cpi_yoy": "Used car prices"},
               {"ylabel": "Change on a year ago", "hline": 0, "pct": True}),
    "insurance": ({"insurance_cpi_yoy": "Motor vehicle insurance prices"},
                  {"ylabel": "Change on a year ago", "hline": 0, "pct": True}),
    "vmt": ({"vmt_12m_yoy": "Vehicle miles traveled, 12-month total"},
            {"ylabel": "Change on a year ago", "hline": 0, "pct": True}),
}


# ---------------------------------------------------------------- template helpers
@app.template_filter("pct")
def f_pct(v, d=0):
    return "\u2013" if v is None or v != v else f"{v * 100:.{d}f}%"


@app.template_filter("num")
def f_num(v, d=0):
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return "\u2013"


@app.template_filter("pts")
def f_pts(v):
    if v is None or v != v:
        return ""
    return "no change" if abs(v) < 0.005 else f"{v * 100:+.0f} pts".replace("-", "\u2212")


@app.template_filter("signed")
def f_signed(v, d=1):
    """A signed number such as -5.1 as "−5.1", with a true minus sign."""
    try:
        return f"{float(v):+.{d}f}".replace("-", "−")
    except (TypeError, ValueError):
        return "–"


@app.template_filter("chg")
def f_chg(v, d=1):
    """A change such as 0.042 as "+4.2%", with a true minus sign."""
    if v is None or v != v:
        return "–"
    return f"{v * 100:+.{d}f}%".replace("-", "−")


@app.template_filter("when")
def f_when(ts):
    if not ts:
        return "never"
    try:
        dt = datetime.fromisoformat(str(ts)[:19])
    except ValueError:
        return str(ts)
    days = (date.today() - dt.date()).days
    if days == 0:
        return f"today {dt:%H:%M}"
    if days == 1:
        return f"yesterday {dt:%H:%M}"
    if 1 < days < 7:
        return f"{dt:%A} {dt:%H:%M}"
    return f"{dt:%b} {dt.day}, {dt.year}"


@app.template_filter("nicedate")
def f_nicedate(d):
    try:
        dt = datetime.fromisoformat(str(d)[:10])
        return f"{dt:%b} {dt.day}, {dt.year}"
    except ValueError:
        return d or ""


@app.template_filter("month")
def f_month(d):
    try:
        return datetime.fromisoformat(str(d)[:10]).strftime("%b %Y")
    except ValueError:
        return d or ""


@app.before_request
def same_origin_only():
    """Refuse form posts coming from other websites (the console only trusts itself)."""
    if request.method == "POST":
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)


@app.context_processor
def globals_():
    s = settings.load()
    return {"S": s, "configured": settings.is_configured(s), "job": jobs.latest(),
            "schedule": scheduler.status(s), "nav": NAV, "platforms": PLATFORMS}


# ---------------------------------------------------------------- shared view logic
def prev_metrics(s, df, week):
    older = [w for w in tracker.weeks(df) if w < week]
    return tracker.metrics(s, older[0], df) if older else None


def carrier_rows(s, m, pm):
    rows = []
    for name, rec in sorted(m["carriers"].items(), key=lambda kv: -kv[1]["n"]):
        if name == "Unknown":
            continue
        prev = (pm or {}).get("carriers", {}).get(name)
        comparable = bool(prev and prev["n"] and rec["n"])
        rows.append({
            "name": GROUP_LABELS.get(name, name), "group": name, **rec,
            "claim": (s["benchmarks"].get(name) or [None])[0],
            "delta": rec["share"] - prev["share"] if comparable else None,
            "sig": comparable and tracker.two_prop_p(rec["copart"], rec["n"], prev["copart"], prev["n"]) < 0.05,
            "tracked": name in s["tracked_carriers"], "small": rec["n"] < s["min_sample"],
        })
    return rows


def freshness():
    runs = db.last_runs()
    items = [("scan", "Copart daily scan", "scan"), ("news", "News", "news"), ("macro", "Macro data", "macro"),
             ("sec", "SEC filings", "sec"), ("capture", "Copart & IAA saved pages", "capture_auto"),
             ("weekly", "Full weekly update", "weekly")]
    return [{"key": k, "label": label, "job": job, "run": runs.get(k)} for k, label, job in items]


def macro_chart(s, name, fmt="svg", m=None):
    m = macro.frame(s) if m is None else m
    if m.empty or name not in MACRO_CHARTS:
        return None
    cols, kw = MACRO_CHARTS[name]
    return charts.lines(m, cols, fmt=fmt, source="Sources: BLS and FHWA, via FRED and the BLS API." if fmt == "png" else None,
                        **kw)


def inventory_chart(name, hist, fmt="svg"):
    col, label = INVENTORY_CHARTS[name]
    if len(hist) < 2:
        return None
    return charts.lines(hist, {col: label}, ylabel="Lots", start=None, fmt=fmt, title=label if fmt == "png" else "",
                        source="Source: Copart's public search pages, scanned by the team." if fmt == "png" else None)


def pgr_chart(fmt="svg", rows=None):
    rows = rows if rows is not None else db.query("SELECT * FROM pgr_monthly ORDER BY filing_date")
    d = pd.DataFrame([r for r in rows if r.get("direct_auto_growth") is not None])
    if len(d) < 2:
        return None
    d.index = pd.to_datetime(d["filing_date"])
    return charts.lines(d.sort_index(), {"direct_auto_growth": "Direct auto policies in force",
                                         "agency_auto_growth": "Agency auto policies in force"},
                        ylabel="Growth on a year ago", pct=True, start=None, fmt=fmt)


# ---------------------------------------------------------------- pages
@app.get("/")
def home():
    s = settings.load()
    snap, changes = weekly.current(s)
    t = snap["tracker"]
    split_ok = tracker.split_problem(t) is None
    rows = []
    if split_ok:
        df = tracker.load(s)
        pm = prev_metrics(s, df, t["week"])
        rows = [r for r in carrier_rows(s, t, pm)
                if r["group"] != "Non-insurance" and (r["tracked"] or r["n"] >= s["min_sample"])][:8]
    return render_template("home.html", snap=snap, t=t, changes=changes, rows=rows, freshness=freshness(),
                           m=snap["macro"], pgr=snap["pgr"], doj=snap["doj"], split_ok=split_ok, cop=snap["copart"],
                           n_sources=db.scalar("SELECT COUNT(*) FROM sources WHERE enabled=1") or 0,
                           market=s.get("market_benchmark"))


@app.get("/inventory")
def inventory_page():
    inv = market.frame()
    hist = market.history(inv)
    return render_template("inventory.html", cop=market.summary(inv), last=db.last_success("scan"),
                           run=db.last_runs().get("scan"),
                           svgs={k: inventory_chart(k, hist) for k in INVENTORY_CHARTS},
                           scan_urls=market.SCAN_PAGES)


@app.get("/tracker")
def tracker_page():
    s = settings.load()
    tab = request.args.get("tab", "results")
    df = tracker.load(s)
    wks = tracker.weeks(df)
    week = request.args.get("week") if request.args.get("week") in wks else (wks[0] if wks else None)
    sources = db.query("SELECT * FROM sources ORDER BY platform, label, id")
    ctx = {"tab": tab, "weeks": wks, "week": week, "has_data": bool(wks), "sources": sources,
           "source_counts": {p: sum(1 for x in sources if x["platform"] == p and x["enabled"]) for p in PLATFORMS}}
    if tab == "results" and week:
        m = tracker.metrics(s, week, df)
        pm = prev_metrics(s, df, week)
        ctx.update(m=m, rows=carrier_rows(s, m, pm), prev_week=pm["week"] if pm else None,
                   split_problem=tracker.split_problem(m),
                   weekly_svg=charts.weekly_shares(tracker.weekly_history(s, df), s["tracked_carriers"], s["min_sample"]),
                   states=tracker.state_table(s, week, df).to_dict("records"))
    elif tab == "collect":
        ctx["prefill"] = {k: request.args.get(k, "") for k in
                          ("platform", "state", "yard", "lot_id", "seller_raw", "make", "model", "year", "damage")}
        ctx["carrier_guess"] = request.args.get("carrier_guess", "")
        ctx["recent_manual"] = db.query("SELECT * FROM observations WHERE origin='manual' ORDER BY rowid DESC LIMIT 8")
        ctx["states_list"] = sorted(infer.US_STATES)
    elif tab == "quality":
        ctx.update(unmapped=tracker.unmapped_sellers(s, df).to_dict("records"),
                   overrides=s.get("carrier_overrides") or {}, groups=carriers.GROUPS,
                   m=tracker.metrics(s, week, df) if week else None)
    elif tab == "lots":
        f = {k: request.args.get(k, "") for k in ("platform", "state", "carrier", "q")}
        d = df
        if f["platform"]:
            d = d[d["platform"] == f["platform"]]
        if f["state"]:
            d = d[d["state"] == f["state"].upper()]
        if f["carrier"]:
            d = d[d["carrier"] == f["carrier"]]
        if f["q"]:
            q = f["q"].lower()
            blob = d[["lot_id", "seller_raw", "yard", "make", "model", "damage"]].astype(str).agg(" ".join, axis=1)
            d = d[blob.str.lower().str.contains(q, regex=False)]
        ctx.update(filters=f, total=len(d),
                   lots=d.sort_values("obs_date", ascending=False).head(500).to_dict("records") if len(d) else [],
                   states_all=sorted(x for x in df["state"].unique() if x) if len(df) else [],
                   carriers_all=sorted(df["carrier"].unique()) if len(df) else [])
    return render_template("tracker.html", **ctx)


@app.post("/tracker/manual")
def manual_add():
    f = request.form
    platform, lot_id = f.get("platform", ""), f.get("lot_id", "").strip()
    if platform not in PLATFORMS or not lot_id:
        flash("Choose Copart or IAA and enter the lot or stock number.", "error")
        return redirect(url_for("tracker_page", tab="collect", **{k: f.get(k, "") for k in ("platform", "state")}))
    yard = f.get("yard", "").strip()
    row = {"obs_date": f.get("obs_date") or date.today().isoformat(), "platform": platform, "lot_id": lot_id,
           "state": (f.get("state") or infer.parse_state(yard)).upper(), "yard": yard,
           "seller_raw": f.get("seller_raw", "").strip(), "make": f.get("make", "").strip().upper(),
           "model": f.get("model", "").strip().upper(), "year": f.get("year", "").strip(),
           "damage": f.get("damage", "").strip().upper(), "sale_date": "", "source_url": "", "origin": "manual"}
    db.save_observations([row])
    group = carriers.canonical(row["seller_raw"], settings.load().get("carrier_overrides"))
    flash(f"Saved lot {lot_id}: {PLATFORMS[platform]}, {row['state'] or 'no state'}, counted as {group}.", "ok")
    return redirect(url_for("tracker_page", tab="collect", platform=platform, state=row["state"]) + "#hand")


@app.post("/tracker/paste")
def paste_listing():
    parsed = capture.parse_listing_text(request.form.get("text", ""))
    if not parsed.get("lot_id"):
        flash("No lot number found in that text. Copy the whole listing page and try again, or type the details.", "error")
    return redirect(url_for("tracker_page", tab="collect", platform=request.form.get("platform", ""), **parsed) + "#hand")


@app.post("/tracker/mapping")
def mapping_save():
    s = settings.load()
    overrides = dict(s.get("carrier_overrides") or {})
    seller = carriers.normalize_name(request.form.get("seller_raw", ""))
    group = request.form.get("group", "")
    if request.form.get("remove"):
        overrides.pop(seller, None)
        flash(f"{seller} is back to automatic matching.", "ok")
    elif seller and group in carriers.GROUPS:
        overrides[seller] = group
        flash(f"{seller} now counts as {group}.", "ok")
    settings.update(carrier_overrides=overrides)
    return redirect(url_for("tracker_page", tab="quality"))


@app.post("/tracker/sources/<int:sid>/<action>")
def source_action(sid, action):
    if action == "toggle":
        db.execute("UPDATE sources SET enabled = 1 - enabled WHERE id=?", (sid,))
    elif action == "delete":
        db.execute("DELETE FROM sources WHERE id=?", (sid,))
        flash("Page removed from weekly auto-capture.", "ok")
    else:
        abort(400)
    return redirect(url_for("tracker_page", tab="sources"))


@app.post("/tracker/sources/add")
def source_add():
    url = request.form.get("url", "").strip()
    platform = request.form.get("platform") or capture.platform_of(url)
    if not url.startswith("http") or platform not in PLATFORMS:
        flash("Paste a full Copart or IAA search-results address (starting with https://).", "error")
    else:
        db.upsert("sources", [{"platform": platform, "url": capture.clean_url(url),
                               "label": request.form.get("label", "").strip().upper(), "enabled": 1,
                               "origin": "added", "added": db.now()}], ["url"])
        flash("Page added. It will be captured with the next weekly update.", "ok")
    return redirect(url_for("tracker_page", tab="sources"))


@app.get("/tracker/lots.csv")
def lots_csv():
    df = tracker.load(settings.load()).drop(columns=["date"], errors="ignore")
    return send_file(io.BytesIO(df.to_csv(index=False).encode()), mimetype="text/csv", as_attachment=True,
                     download_name=f"cprt_lots_{date.today()}.csv")


@app.get("/charts/<name>.png")
def chart_png(name):
    s = settings.load()
    png = None
    if name in ("split", "weekly"):
        df = tracker.load(s)
        wks = tracker.weeks(df)
        week = request.args.get("week") if request.args.get("week") in wks else (wks[0] if wks else None)
        if week and name == "split":
            png = charts.split_bars(tracker.share_table(tracker.paired(df[df["week"] == week])), s["benchmarks"],
                                    s["min_sample"], f"Where each insurer's salvage is listed, week of {week}")
        elif week:
            png = charts.weekly_shares(tracker.weekly_history(s, df), s["tracked_carriers"], s["min_sample"], fmt="png")
    elif name in INVENTORY_CHARTS:
        png = inventory_chart(name, market.history(), fmt="png")
    elif name in MACRO_CHARTS:
        png = macro_chart(s, name, fmt="png")
    elif name == "progressive":
        png = pgr_chart("png")
    if not png:
        abort(404)
    return send_file(io.BytesIO(png), mimetype="image/png", as_attachment=True,
                     download_name=f"cprt_{name}_{date.today()}.png")


@app.get("/macro")
def macro_page():
    s = settings.load()
    m = macro.frame(s)
    svgs = {k: macro_chart(s, k, m=m) for k in MACRO_CHARTS} if not m.empty else {}
    return render_template("macro.html", latest=macro.latest(s, m), svgs=svgs, last=db.last_success("macro"))


@app.get("/filings")
def filings_page():
    pgr = db.query("SELECT * FROM pgr_monthly ORDER BY filing_date DESC")
    oldest_first = db.query("SELECT * FROM doj ORDER BY filing_date")
    doj_rows = [{**r, "diff": sec.word_diff(older["disclosure"], r["disclosure"]) if r["changed"] and older else None}
                for r, older in zip(oldest_first, sec.previous_same_form(oldest_first))][::-1]
    ticker, keyword = request.args.get("ticker", ""), request.args.get("keyword", "")
    snips = db.query("SELECT * FROM release_snippets WHERE (?='' OR ticker=?) AND (?='' OR keyword=?) "
                     "ORDER BY filing_date DESC LIMIT 200", (ticker, ticker, keyword, keyword))
    return render_template(
        "filings.html", pgr=pgr, pgr_svg=pgr_chart("svg", list(reversed(pgr))), doj=doj_rows,
        doj_status=sec.doj_status(), snips=snips, ticker=ticker, keyword=keyword,
        tickers=[r["ticker"] for r in db.query("SELECT DISTINCT ticker FROM release_snippets ORDER BY ticker")],
        keywords=[r["keyword"] for r in db.query("SELECT DISTINCT keyword FROM release_snippets ORDER BY keyword")],
        hits=db.query("SELECT * FROM fulltext_hits ORDER BY filing_date DESC LIMIT 300"),
        last=db.last_success("sec"))


@app.get("/news")
def news_page():
    f = {"q": request.args.get("q", "").strip(), "view": request.args.get("view", "all"),
         "min": request.args.get("min", "0")}
    wk = weekly.week_start()
    sql, params = "SELECT * FROM news WHERE score >= ?", [int(f["min"]) if f["min"].isdigit() else 0]
    if f["view"] == "new":
        sql += " AND first_seen >= ?"
        params.append(wk)
    elif f["view"] == "starred":
        sql += " AND starred = 1"
    elif f["view"] == "unread":
        sql += " AND read = 0"
    if f["q"]:
        sql += " AND (title LIKE ? OR source LIKE ? OR matched LIKE ?)"
        params += [f"%{f['q']}%"] * 3
    rows = db.query(sql + " ORDER BY published DESC LIMIT 300", tuple(params))
    counts = {"all": db.scalar("SELECT COUNT(*) FROM news") or 0,
              "new": db.scalar("SELECT COUNT(*) FROM news WHERE first_seen >= ?", (wk,)) or 0,
              "unread": db.scalar("SELECT COUNT(*) FROM news WHERE read = 0") or 0,
              "starred": db.scalar("SELECT COUNT(*) FROM news WHERE starred = 1") or 0}
    return render_template("news.html", rows=rows, f=f, counts=counts, week=wk, last=db.last_success("news"))


@app.post("/news/<key>/<action>")
def news_mark(key, action):
    change = {"star": ("starred", 1), "unstar": ("starred", 0), "read": ("read", 1), "unread": ("read", 0)}.get(action)
    if not change:
        abort(400)
    db.execute(f"UPDATE news SET {change[0]}=? WHERE key=?", (change[1], key))
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    return redirect(request.referrer or url_for("news_page"))


@app.get("/reports")
def reports_page():
    return render_template("reports.html", reports=report.list_reports())


@app.get("/reports/<name>")
def report_file(name):
    if not re.fullmatch(r"CPRT_weekly_\d{4}-\d{2}-\d{2}\.html", name):
        abort(404)
    p = paths.data_path("reports", name, mkdir=False)
    if not p.exists():
        abort(404)
    return send_file(p, as_attachment=request.args.get("download") == "1", download_name=name)


@app.get("/export/excel")
def export_excel():
    return send_file(io.BytesIO(report.excel(settings.load())), as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     download_name=f"CPRT_alt_data_{date.today()}.xlsx")


@app.get("/settings")
def settings_page():
    s = settings.load()
    return render_template("settings.html", weekdays=settings.WEEKDAYS, groups=carriers.GROUPS,
                           sched=scheduler.status(s), config_data_dir=str(paths.DATA))


@app.post("/settings/profile")
def save_profile():
    s = settings.update(user_name=request.form.get("user_name", "").strip(),
                        user_email=request.form.get("user_email", "").strip())
    if settings.is_configured(s):
        flash("Saved. You're ready to run your first update.", "ok")
    else:
        flash("Enter your full name and a valid email address. The SEC requires both.", "error")
    return redirect(request.form.get("next") or url_for("settings_page"))


@app.post("/settings")
def settings_save():
    f, section = request.form, request.form.get("section", "")
    try:
        if section == "schedule":
            s = settings.update(schedule_weekday=int(f["weekday"]), schedule_hour=int(f["hour"]),
                                schedule_minute=int(f["minute"]), capture_in_weekly="capture_in_weekly" in f,
                                scan_daily="scan_daily" in f)
            if scheduler.status(s)["installed"]:
                scheduler.install(s)  # apply the new time
        elif section == "tracking":
            bm = {}
            for name in carriers.GROUPS:
                v = f.get(f"claim_{name}", "").strip().rstrip("%")
                if v:
                    bm[name] = [float(v) / 100, f.get(f"source_{name}", "").strip() or "Expert call"]
            settings.update(tracked_carriers=f.getlist("tracked"), benchmarks=bm,
                            min_sample=max(1, int(f.get("min_sample", 10))))
        elif section == "collection":
            lo, hi = int(f.get("pause_lo", 15)), int(f.get("pause_hi", 30))
            settings.update(show_browser="show_browser" in f, respect_robots_txt="respect_robots_txt" in f,
                            pause_between_pages=[min(lo, hi), max(lo, hi)],
                            max_pages_per_run=max(1, int(f.get("max_pages", 30))),
                            guided_max_minutes=max(5, int(f.get("guided_max", 30))),
                            learn_sources_min_lots=max(1, int(f.get("min_lots", 10))))
        elif section == "news":
            settings.update(news_queries=[q.strip() for q in f.get("queries", "").splitlines() if q.strip()],
                            news_lookback_days=max(7, int(f.get("lookback", 180))))
        elif section == "sec":
            start = f.get("start", "2025-01-01")
            datetime.fromisoformat(start)
            settings.update(sec_fulltext_queries=[q.strip() for q in f.get("queries", "").splitlines() if q.strip()],
                            sec_fulltext_start=start)
        elif section == "advanced":
            overrides = json.loads(f.get("field_overrides") or "{}")
            if not isinstance(overrides, dict):
                raise ValueError("field overrides must be a JSON object")
            settings.update(field_overrides=overrides)
        else:
            abort(400)
        flash("Settings saved.", "ok")
    except (ValueError, KeyError, RuntimeError) as exc:
        flash(f"Not saved: {exc}", "error")
    return redirect(url_for("settings_page") + f"#{section}")


@app.post("/settings/schedule/<action>")
def schedule_toggle(action):
    s = settings.load()
    try:
        flash(scheduler.install(s) if action == "on" else scheduler.uninstall(), "ok")
    except RuntimeError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings_page") + "#schedule")


@app.post("/settings/test-notification")
def test_notification():
    scheduler.notify("CPRT console", "Notifications are working.")
    flash("Test notification sent. If nothing appeared, allow notifications for Script Editor in System Settings.", "ok")
    return redirect(url_for("settings_page") + "#schedule")


@app.post("/settings/reset-listings")
def reset_listings():
    db.execute("DELETE FROM observations")
    db.execute("DELETE FROM snapshots")
    flash("All listing data and weekly snapshots deleted.", "ok")
    return redirect(url_for("settings_page") + "#advanced")


@app.get("/help")
def help_page():
    """The user manual, with the owner's live setup status and current numbers as worked examples."""
    s = settings.load()
    pgr = db.query("SELECT period, filing_date, direct_auto_growth FROM pgr_monthly "
                   "WHERE direct_auto_growth IS NOT NULL ORDER BY filing_date")
    return render_template("help.html", cop=market.summary(), m=macro.latest(s), doj=sec.doj_status(),
                           pgr_first=pgr[0] if pgr else None, pgr_last=pgr[-1] if pgr else None,
                           runs=db.last_runs(), config_data_dir=str(paths.DATA))


@app.get("/guide")
def guide_page():
    return render_template("guide.html")


# ---------------------------------------------------------------- background tasks
@app.post("/api/jobs/<kind>")
def api_start(kind):
    body = request.get_json(silent=True) or {}
    if kind == "capture_guided":
        platform = body.get("platform")
        if platform not in PLATFORMS:
            return jsonify(error="Choose Copart or IAA."), 400
        args = ["capture", "guided", "--platform", platform]
    elif kind in JOB_ARGS:
        args = JOB_ARGS[kind]
    else:
        return jsonify(error="Unknown task."), 404
    if kind == "sec" and not settings.is_configured(settings.load()):
        return jsonify(error="Add your name and email in Settings first. The SEC requires them."), 400
    try:
        return jsonify(jobs.start(kind, args))
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 409


@app.get("/api/job")
def api_job():
    return jsonify(jobs.latest() or {})


@app.post("/api/job/<job_id>/stop")
def api_stop(job_id):
    if not re.fullmatch(r"[\w-]+", job_id):
        abort(400)
    jobs.request_stop(job_id)
    return jsonify(ok=True)


# ---------------------------------------------------------------- start
def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    url = f"http://127.0.0.1:{PORT}/"
    if _port_in_use(PORT):
        print(f"The console is already running. Opening {url}")
        webbrowser.open(url)
        return
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"CPRT console is running at {url}\nKeep this window open while you use it. Close it to stop the console.")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
