"""The weekly update: collect everything, snapshot the week, explain what changed."""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import capture, db, macro, market, news, report, sec, tracker

STEP_LABELS = {"news": "News", "macro": "Macro data (FRED and BLS)", "sec": "SEC filings", "scan": "Copart scan",
               "capture": "Saved Copart & IAA pages", "analysis": "Analysis & report"}
PLATFORM_NAMES = {"copart": "Copart", "iaa": "IAA"}


def _signed(v: float, d: int = 1) -> str:
    return f"{v:+.{d}f}".replace("-", "−")  # a true minus sign, per the copy rules


def week_start(d: date | None = None) -> str:
    d = d or date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def snapshot(s: dict) -> dict:
    wk = week_start()
    return {
        "week": wk, "created": db.now(),
        "tracker": tracker.metrics(s),
        "copart": market.summary(),
        "macro": macro.latest(s),
        "pgr": db.query("SELECT * FROM pgr_monthly ORDER BY filing_date DESC LIMIT 3"),
        "doj": sec.doj_status(),
        "news": {"new": db.scalar("SELECT COUNT(*) FROM news WHERE first_seen >= ?", (wk,)) or 0,
                 "strong": db.scalar("SELECT COUNT(*) FROM news WHERE first_seen >= ? AND score >= 3", (wk,)) or 0},
    }


def save_snapshot(snap: dict) -> None:
    db.upsert("snapshots", [{"week": snap["week"], "created": snap["created"],
                             "metrics": json.dumps(snap, default=str)}], ["week"], update=["created", "metrics"])


def previous_snapshot(week: str) -> dict | None:
    rows = db.query("SELECT metrics FROM snapshots WHERE week < ? ORDER BY week DESC LIMIT 1", (week,))
    return json.loads(rows[0]["metrics"]) if rows else None


def what_changed(s: dict, cur: dict, pt: dict | None) -> list[dict]:
    """Plain-English notes. level: alert (needs attention), action (to do), good (supports the long), info.

    `pt` is the tracker metrics for the previous week that has listing data (None if there isn't one).
    """
    out: list[dict] = []

    def add(level: str, text: str):
        out.append({"level": level, "text": text})

    t = cur.get("tracker") or {}
    min_n = s["min_sample"]
    for level, text in market.notes(cur.get("copart") or {}):
        add(level, text)
    problem = tracker.split_problem(t)
    if t.get("has_data") and problem:
        add("info", f"Insurer split paused: {problem} Copart inventory tracks volumes instead; see the Guide.")
    elif t.get("has_data"):
        pt = pt or {}
        if t["week"] < week_start():
            add("action", "No listing data collected this week yet. Capture the saved pages or record a session.")
        if not pt.get("has_data"):
            add("info", "This is the first week of listing data. Week-over-week changes appear once a second week is collected.")
        else:
            for name in ["All insurers"] + list(s["tracked_carriers"]):
                c = t["overall"] if name == "All insurers" else t["carriers"].get(name)
                p = pt["overall"] if name == "All insurers" else pt["carriers"].get(name)
                if not c or not p or min(c["n"], p["n"]) < min_n or c["share"] is None or p["share"] is None:
                    continue
                d = c["share"] - p["share"]
                if abs(d) >= 0.05:
                    sig = tracker.two_prop_p(c["copart"], c["n"], p["copart"], p["n"]) < 0.05
                    add("alert" if sig else "info",
                        f"{name}: Copart share {'rose' if d > 0 else 'fell'} from {p['share']:.0%} to "
                        f"{c['share']:.0%} ({d * 100:+.0f} pts). ".replace("(-", "(\u2212")
                        + ("That's a statistically significant move." if sig else "Not significant yet at this sample size."))
        for name, (claim, _src) in s["benchmarks"].items():
            c = t["carriers"].get(name)
            if c and c["n"] >= min_n:
                matches = c["lo"] <= claim <= c["hi"]
                add("good" if matches else "alert",
                    f"{name}: {c['share']:.0%} of listed lots are on Copart (n={c['n']}), "
                    + (f"consistent with the expert-call claim of {claim:.0%}." if matches
                       else f"which differs from the expert-call claim of {claim:.0%}."))
        if t.get("unpaired_states"):
            add("action", f"{', '.join(t['unpaired_states'])}: only one platform sampled, so left out of the split. "
                          "Record the other site for these states.")
        for p, cov in (t.get("seller_coverage") or {}).items():
            if cov is not None and cov < 0.5:
                add("action", f"Only {cov:.0%} of {PLATFORM_NAMES.get(p, p)} lots show a seller name. "
                              "See Data quality on the Insurer tracker.")

    m = cur.get("macro") or {}
    pr = m.get("pressure_repair")
    if pr:
        ya = pr.get("year_ago")
        txt = f"Total-loss pressure index at {pr['value']:.0f} (2019 = 100)"
        if ya is not None:
            txt += f", {'up' if pr['value'] >= ya else 'down'} {abs(pr['value'] - ya):.0f} pts on a year ago"
        add("good" if ya is None or pr["value"] >= ya else "info",
            txt + ". Repairs rising faster than car values means more wrecks get totaled.")
    ins = m.get("insurance_cpi_yoy")
    if ins:
        add("good" if ins["value"] < 5 else "info",
            f"Auto insurance prices {_signed(ins['value'])}% on a year ago (peak since 2022: "
            f"{_signed(m.get('insurance_cpi_peak', 0))}%). Cooling premiums support the coverage-comeback argument.")

    pgr = [r for r in (cur.get("pgr") or []) if r.get("direct_auto_growth") is not None]
    if len(pgr) >= 2 and pgr[0]["direct_auto_growth"] != pgr[1]["direct_auto_growth"]:
        a, b = pgr[0]["direct_auto_growth"], pgr[1]["direct_auto_growth"]
        add("good" if a < b else "info",
            f"Progressive direct-auto policy growth {'slowed' if a < b else 'picked up'} to {a:.0f}% "
            f"({pgr[0].get('period') or pgr[0]['filing_date']}) from {b:.0f}%. Progressive is IAA's biggest tailwind.")

    d = cur.get("doj") or {}
    if d.get("known"):
        if d.get("changed_latest"):
            add("alert", f"Copart's DOJ disclosure wording changed in the {d['latest_form']} filed {d['latest']}. "
                         "The changes are highlighted on Filings.")
        elif d.get("found_latest"):
            add("good", f"Copart's DOJ disclosure is unchanged in the latest {d['latest_form']} ({d['latest']}).")

    n = cur.get("news") or {}
    if n.get("new"):
        add("info", f"{n['new']} new articles this week, {n.get('strong', 0)} with strong alt-data language.")
    order = {"alert": 0, "action": 1, "good": 2, "info": 3}
    return sorted(out, key=lambda x: order[x["level"]])


def previous_data_week(s: dict, t: dict) -> dict | None:
    if not t.get("has_data"):
        return None
    df = tracker.load(s)
    older = [w for w in tracker.weeks(df) if w < t["week"]]
    return tracker.metrics(s, older[0], df) if older else None


def current(s: dict) -> tuple[dict, list[dict]]:
    snap = snapshot(s)
    return snap, what_changed(s, snap, previous_data_week(s, snap["tracker"]))


def logged_step(name: str, fn):
    """Run one collection step and record the outcome in `runs` (Data freshness). Errors are re-raised."""
    started = db.now()
    try:
        res = fn()
    except sec.SecConfigError as exc:
        db.log_run(name, "skipped", str(exc), started)
        raise
    except (SystemExit, Exception) as exc:
        db.log_run(name, "failed", str(exc) or exc.__class__.__name__, started)
        raise
    db.log_run(name, "ok", json.dumps(res, default=str), started)
    return res


def is_weekly_day(s: dict, today: date | None = None) -> bool:
    """Settings count weekdays from Sunday = 0; Python's weekday() counts from Monday = 0."""
    today = today or date.today()
    return (today.weekday() + 1) % 7 == int(s["schedule_weekday"]) % 7


def run_scheduled(s: dict, progress=print, today: date | None = None) -> dict:
    """What the schedule runs: the full update on the chosen weekday, the Copart scan on the other days."""
    if not s["scan_daily"] or is_weekly_day(s, today):
        return {"kind": "weekly", **run(s, progress)}
    return {"kind": "scan", **logged_step("scan", lambda: capture.run_scan(s, progress))}


def run(s: dict, progress=print, include_capture: bool | None = None) -> dict:
    include_capture = s["capture_in_weekly"] if include_capture is None else include_capture
    started_all = db.now()
    steps = [("news", lambda: news.run(s, progress)), ("macro", lambda: macro.run(s, progress)),
             ("sec", lambda: sec.run(s, progress)), ("scan", lambda: capture.run_scan(s, progress))]
    if include_capture and db.scalar("SELECT COUNT(*) FROM sources WHERE enabled=1"):
        steps.append(("capture", lambda: capture.run_auto(s, progress, pause_first=True)))
    results = {}
    for i, (name, fn) in enumerate(steps, 1):
        progress(f"Step {i} of {len(steps) + 1}: {STEP_LABELS[name]}", step=name)
        try:
            logged_step(name, fn)
            results[name] = "ok"
        except sec.SecConfigError as exc:
            results[name] = "skipped"
            progress(f"  skipped: {exc}")
        except (SystemExit, Exception) as exc:  # one failing source never stops the rest
            results[name] = "failed"
            progress(f"  failed: {exc}")
    progress(f"Step {len(steps) + 1} of {len(steps) + 1}: {STEP_LABELS['analysis']}", step="analysis")
    try:
        snap, changes = current(s)
        snap["changes"] = changes
        save_snapshot(snap)
        path = report.build(s, snap)
    except Exception as exc:  # the collected data is saved; record that the analysis didn't finish
        db.log_run("weekly", "failed", f"Analysis and report failed: {exc!r}", started_all)
        raise
    ok = all(v in ("ok", "skipped") for v in results.values())
    summary = {"results": results, "report": path.name, "alerts": sum(1 for c in changes if c["level"] == "alert"),
               "actions": sum(1 for c in changes if c["level"] == "action")}
    db.log_run("weekly", "ok" if ok else "partial", json.dumps(summary), started_all)
    progress(f"Weekly update finished: report saved as {path.name}.", **summary)
    return summary
