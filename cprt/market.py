"""Copart's own inventory counts, read from its public search pages once a day.

Next to the 20 lots it shows, a Copart search result carries counts for the whole site: every yard's listed
lots, lots newly added in the last 24 hours and 7 days, and title types. The daily scan (capture.run_scan)
loads two search pages, all lots and lots added in the last 7 days, and stores those counts here. That gives
Copart's listed inventory and new-lot flow by state without anyone browsing.

These are listed lots of every kind (insurance, dealer, rental, charity), not insurance assignments.
"Added in the last 7 days" counts lots still listed that Copart assigned to a sale in the last 7 days, so it is
a consistent weekly-flow proxy rather than a full count of arrivals.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.parse import quote, urlparse

import pandas as pd

from . import db, infer

SEARCH = "https://www.copart.com/lotSearchResults"
# Copart's own "Newly Added Lots: Last 7 Days" filter (seen in its search responses, Sep 2026)
NEW_7D_FILTER = "expected_sale_assigned_ts_utc:[NOW/DAY-7DAY TO NOW/DAY]"
FACETS = {"Location": "yard", "Newly Added Lots": "newly_added", "Title Type": "title", "Vehicle Type": "vehicle_type"}
VIEW_LABELS = {"listed": "all listed lots", "new_7d": "lots added in the last 7 days"}
WEEK_SLACK_DAYS = 2  # a scan 5 to 9 days earlier counts as "a week earlier"
STALE_DAYS = 2
BIG_MOVE = 0.05  # week-over-week moves of 5% or more get their own note


def criteria_url(filters: dict) -> str:
    """A search-results address with filters, in the format Copart's own pages use."""
    crit = {"query": ["*"], "filter": filters, "searchName": "", "watchListOnly": False, "freeFormSearch": False}
    return f"{SEARCH}?free=false&searchCriteria={quote(json.dumps(crit, separators=(',', ':')))}"


SCAN_PAGES = {"listed": f"{SEARCH}?free=true&query=", "new_7d": criteria_url({"NLTS": [NEW_7D_FILTER]})}


# ---------------------------------------------------------------- reading and storing
def is_search_results(payload: dict) -> bool:
    return urlparse(payload.get("url", "")).path == "/public/lots/search-results"


def view_of(payload: dict) -> str | None:
    """Which site-wide count a search response holds, from the query Copart echoes back.

    "listed" (no filters), "new_7d" (only the 7-day newly-added filter), "other" (any narrower search, such as
    one make or yard, whose counts aren't site-wide), or None when the response doesn't echo its query.
    """
    query = ((payload.get("data") or {}).get("data") or {}).get("query")
    if not isinstance(query, dict):
        return None
    filters = {k: v for k, v in (query.get("filter") or {}).items() if v}
    if (query.get("query") or ["*"]) != ["*"]:
        return "other"
    if not filters:
        return "listed"
    if set(filters) == {"NLTS"} and any(NEW_7D_FILTER in str(v) for v in filters["NLTS"]):
        return "new_7d"
    return "other"


def parse_search(payloads: list[dict], view: str | None = None) -> dict | None:
    """{"total": n, "facets": {dimension: {name: count}}} from a search-results response, or None if absent.

    With `view`, responses that echo a different query are skipped.
    """
    for p in payloads:
        if not is_search_results(p) or (view is not None and view_of(p) not in (view, None)):
            continue
        results = ((p.get("data") or {}).get("data") or {}).get("results") or {}
        if "totalElements" not in results:
            continue
        facets: dict[str, dict[str, int]] = {}
        for f in results.get("facetFields") or []:
            dim = FACETS.get(f.get("displayName"))
            if not dim:
                continue
            counts: dict[str, int] = {}
            for c in f.get("facetCounts") or []:
                name, n = c.get("displayName"), c.get("count")
                if name and n is not None:
                    counts[name] = counts.get(name, 0) + int(n)  # Copart repeats some names; they're separate values
            facets[dim] = counts
        return {"total": int(results["totalElements"]), "facets": facets}
    return None


def store(obs_date: str, view: str, parsed: dict, source_url: str, platform: str = "copart") -> int:
    base = {"obs_date": obs_date, "platform": platform, "view": view, "source_url": source_url, "captured": db.now()}
    rows = [{**base, "dimension": "total", "key": "all", "count": parsed["total"]}]
    rows += [{**base, "dimension": dim, "key": key, "count": n}
             for dim, counts in parsed["facets"].items() for key, n in counts.items()]
    return db.upsert("inventory", rows, ["obs_date", "platform", "view", "dimension", "key"],
                     update=["count", "source_url", "captured"])


# ---------------------------------------------------------------- analysis
def frame(platform: str = "copart") -> pd.DataFrame:
    return db.df("SELECT obs_date, view, dimension, key, count FROM inventory WHERE platform=?", (platform,))


def state_of(yard: str) -> str:
    """"Il - Chicago North" -> "IL". Yards outside the US (e.g. "Ab - Calgary") give ""."""
    return infer.parse_state(str(yard).upper())


def scan_dates(inv: pd.DataFrame) -> list[str]:
    return sorted(inv["obs_date"].unique(), reverse=True) if not inv.empty else []


def _us_yards(day: pd.DataFrame) -> pd.DataFrame:
    yards = day[day["dimension"] == "yard"]
    return yards.assign(state=[state_of(k) for k in yards["key"]]).query("state != ''")


def day_totals(inv: pd.DataFrame, obs_date: str) -> dict:
    day = inv[inv["obs_date"] == obs_date]

    def site_total(view: str):
        s = day[(day["view"] == view) & (day["dimension"] == "total")]["count"]
        return int(s.iloc[0]) if len(s) else None

    us = _us_yards(day)
    newly = day[(day["view"] == "listed") & (day["dimension"] == "newly_added")].set_index("key")["count"]
    us_sum = {v: int(us[us["view"] == v]["count"].sum()) if (us["view"] == v).any() else None for v in VIEW_LABELS}
    return {"listed": site_total("listed"), "new_7d": site_total("new_7d"),
            "us_listed": us_sum["listed"], "us_new_7d": us_sum["new_7d"],
            "new_24h": int(newly["Last 24 Hours"]) if "Last 24 Hours" in newly else None,
            "us_yards": int(us[us["view"] == "listed"]["key"].nunique())}


def by_state(inv: pd.DataFrame, obs_date: str) -> pd.DataFrame:
    """US states for one scan: listed lots, lots added in the last 7 days, and new as a share of listed."""
    cols = ["state", "listed", "new_7d", "new_share"]
    us = _us_yards(inv[inv["obs_date"] == obs_date])
    if us.empty:
        return pd.DataFrame(columns=cols)
    t = us.pivot_table(index="state", columns="view", values="count", aggfunc="sum", fill_value=0)
    for view in VIEW_LABELS:
        if view not in t:
            t[view] = 0
    t["new_share"] = t["new_7d"] / t["listed"].where(t["listed"] > 0)
    return t.reset_index().sort_values("listed", ascending=False)[cols].reset_index(drop=True)


def week_earlier(dates: list[str], latest: str) -> str | None:
    """The scan closest to seven days before `latest`, within two days either side."""
    target = date.fromisoformat(latest) - timedelta(days=7)
    near = [d for d in dates if abs((date.fromisoformat(d) - target).days) <= WEEK_SLACK_DAYS]
    return min(near, key=lambda d: abs((date.fromisoformat(d) - target).days)) if near else None


def history(inv: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per scan day (index = date): US listed and US added in the last 7 days."""
    inv = frame() if inv is None else inv
    rows = []
    for d in scan_dates(inv):
        t = day_totals(inv, d)
        rows.append({"date": d, "us_listed": t["us_listed"], "us_new_7d": t["us_new_7d"]})
    if not rows:
        return pd.DataFrame(columns=["us_listed", "us_new_7d"])
    out = pd.DataFrame(rows).sort_values("date")
    out.index = pd.to_datetime(out.pop("date"))
    return out


def _change(cur, prev):
    return cur / prev - 1 if cur is not None and prev else None


def summary(inv: pd.DataFrame | None = None) -> dict:
    """Everything the pages, notes and report need about the latest scan."""
    inv = frame() if inv is None else inv
    dates = scan_dates(inv)
    if not dates:
        return {"has_data": False}
    latest = dates[0]
    cur = day_totals(inv, latest)
    prior_date = week_earlier(dates, latest)
    prior = day_totals(inv, prior_date) if prior_date else {}
    states = by_state(inv, latest)
    before = by_state(inv, prior_date).set_index("state")["new_7d"].to_dict() if prior_date else {}
    states["new_7d_change"] = [_change(n, before.get(st)) for st, n in zip(states["state"], states["new_7d"])]
    return {"has_data": True, "date": latest, "prior_date": prior_date, "scans": len(dates), **cur,
            "prior": prior, "change": {k: _change(cur[k], prior.get(k)) for k in ("us_listed", "us_new_7d")},
            "states": states.to_dict("records")}


def notes(summ: dict, today: date | None = None) -> list[tuple[str, str]]:
    """(level, text) notes for This week: alert, action, good or info."""
    today = today or date.today()
    if not summ.get("has_data"):
        return [("action", "No Copart scan yet. Run it on Copart inventory; it loads two public pages and takes "
                           "about a minute. The daily scan then runs by itself once the schedule is on.")]
    out = []
    age = (today - date.fromisoformat(summ["date"])).days
    if age > STALE_DAYS:
        out.append(("action", f"The last Copart scan was {age} days ago. Turn on the daily schedule in Settings, "
                              "or run the scan now."))
    if summ["us_listed"] is not None:
        new = f"; {summ['us_new_7d']:,} were added in the last 7 days" if summ["us_new_7d"] is not None else ""
        out.append(("info", f"Copart has {summ['us_listed']:,} lots listed in US yards{new} "
                            f"(scan of {summ['date']})."))
    ch = summ["change"].get("us_new_7d")
    if ch is not None and abs(ch) >= BIG_MOVE:
        prev = summ["prior"]["us_new_7d"]
        out.append(("good" if ch > 0 else "alert",
                    f"Copart's new US listings {'rose' if ch > 0 else 'fell'} {abs(ch):.0%} on a week earlier "
                    f"({prev:,} to {summ['us_new_7d']:,}, 7-day windows ending {summ['prior_date']} and {summ['date']})."))
    return out
