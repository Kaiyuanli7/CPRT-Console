"""User settings, stored in data/settings.json and edited from the Settings page."""
from __future__ import annotations

import copy
import json
import re

from . import paths

DEFAULTS: dict = {
    # Your details (the SEC requires a name + email on automated requests)
    "user_name": "",
    "user_email": "",

    # Weekly auto-update (macOS launchd). Weekday: 0=Sunday, 1=Monday ... 6=Saturday
    "schedule_weekday": 1,
    "schedule_hour": 8,
    "schedule_minute": 0,
    "capture_in_weekly": True,  # replay saved Copart/IAA pages during weekly updates
    "scan_daily": True,         # scan Copart's public counts every day at the scheduled time; the rest stays weekly

    # Copart / IAA collection
    "start_urls": {"copart": "https://www.copart.com/", "iaa": "https://www.iaai.com/"},
    "show_browser": True,          # a visible browser is closer to a normal visit
    "page_wait_seconds": 10,
    "scrolls_per_page": 4,
    "pause_between_pages": [15, 30],
    "max_pages_per_run": 30,
    "respect_robots_txt": True,
    "guided_max_minutes": 30,
    "learn_sources_min_lots": 10,  # pages with at least this many lots become weekly sources
    "field_overrides": {},         # advanced: {"seller": "someJsonKey"} if auto-detection misses
    "carrier_overrides": {},       # raw seller name -> insurer, set on the Data quality tab

    # Analysis
    "tracked_carriers": ["State Farm", "Progressive", "GEICO", "Allstate", "USAA"],
    "benchmarks": {
        "Progressive": [0.05, "Ex-GEICO SVP call (9/3/26): Progressive now ~95/5 IAA/Copart"],
        "GEICO": [0.95, "Ex-GEICO SVP call (9/3/26): GEICO now ~95/5 Copart/IAA"],
    },
    "min_sample": 10,
    "market_benchmark": [0.579, "JPM's autoAstat tracker (Sep 11, 2026)"],

    # News
    "news_queries": [
        "Copart market share IAA",
        "Copart insurance volumes",
        '"RB Global" automotive volumes IAA',
        'Copart "web scraping" OR "web-scraping"',
        'Yipit Copart OR "RB Global"',
        "autoAstat salvage",
        '"total loss frequency"',
        'Progressive "policies in force"',
        "GEICO policy growth",
        "Copart ACV Auctions acquisition",
        'Copart "CCC Intelligent Solutions"',
        "Copart Pickles Australia",
        "salvage auction insurer contract Copart IAA",
    ],
    "news_lookback_days": 180,
    "alt_data_terms": [
        "market share", "share", "data", "tracking", "tracker", "scrap", "survey", "index",
        "units", "volume", "assignments", "total loss", "policies in force", "policy count",
        "contract", "rfp", "take rate", "fee", "yipit", "autoastat", "web traffic", "channel check",
    ],
    "extra_feeds": [
        {"name": "Repairer Driven News", "url": "https://www.repairerdrivennews.com/feed/",
         "keywords": ["copart", "iaa", "salvage", "total loss", "ccc", "acv"]},
    ],

    # Macro: role -> [series id, label]. Plain ids are FRED series; "BLS:" ids come from the BLS API.
    # Neither needs a key.
    "fred_series": {
        "insurance_cpi": ["BLS:CUUR0000SETE", "Motor vehicle insurance prices"],
        "repair_cpi": ["CUSR0000SETD", "Motor vehicle maintenance & repair prices"],
        "parts_cpi": ["CUSR0000SETC", "Motor vehicle parts & equipment prices"],
        "used_car_cpi": ["CUSR0000SETA02", "Used car & truck prices"],
        "vmt_12m": ["M12MTVUSM227NFWA", "Vehicle miles traveled, 12-month total"],
    },

    # SEC EDGAR
    "sec_release_targets": [
        {"ticker": "PGR", "filings": 14,
         "keywords": ["policies in force", "combined ratio", "net premiums written"]},
        {"ticker": "RBA", "filings": 6,
         "keywords": ["automotive", "unit volume", "lots sold", "take rate", "gross transaction value"]},
        {"ticker": "CPRT", "filings": 6,
         "keywords": ["insurance", "units", "assignments", "average selling price"]},
    ],
    "sec_fulltext_queries": [
        '"total loss frequency"',
        '"salvage" "Copart"',
        '"automotive pricing incentives"',
        '"total loss" "salvage vendor"',
    ],
    "sec_fulltext_forms": "10-K,10-Q,8-K",
    "sec_fulltext_start": "2025-01-01",
    "doj_ticker": "CPRT",
    "doj_filings": 8,
    "doj_keyword": "money laundering",
}

WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Series that disappeared from where the console fetched them, and their replacements (FRED dropped the
# insurance index in 2026; BLS still publishes it).
MOVED_SERIES = {"CUSR0000SETE": "BLS:CUUR0000SETE"}


def settings_file():
    return paths.data_path("settings.json")


def load() -> dict:
    s = copy.deepcopy(DEFAULTS)
    f = settings_file()
    if f.exists():
        try:
            saved = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            saved = {}
        for k, v in saved.items():
            if k in s:
                s[k] = v
    s["fred_series"] = _move_series(s["fred_series"])
    return s


def _move_series(series):
    """Point saved series that moved (MOVED_SERIES) at their new source. Anything unexpected is left alone:
    load() runs before every page, so a hand-edited file must never crash it."""
    if not isinstance(series, dict):
        return series
    return {role: [MOVED_SERIES[e[0]], e[1]]
            if isinstance(e, (list, tuple)) and len(e) == 2 and isinstance(e[0], str) and e[0] in MOVED_SERIES else e
            for role, e in series.items()}


def save(s: dict) -> None:
    clean = {k: s[k] for k in DEFAULTS if k in s}
    tmp = settings_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2))
    tmp.replace(settings_file())


def update(**changes) -> dict:
    s = load()
    s.update({k: v for k, v in changes.items() if k in DEFAULTS})
    save(s)
    return s


def sec_user_agent(s: dict) -> str:
    name, email = (s.get("user_name") or "").strip(), (s.get("user_email") or "").strip()
    return f"{name} {email}" if name and EMAIL.match(email) else ""


def is_configured(s: dict) -> bool:
    return bool(sec_user_agent(s))


def schedule_text(s: dict) -> str:
    return f"{WEEKDAYS[int(s['schedule_weekday']) % 7]}s at {int(s['schedule_hour']):02d}:{int(s['schedule_minute']):02d}"


def schedule_summary(s: dict) -> str:
    """What the schedule does, for the sidebar and Settings."""
    if not s.get("scan_daily"):
        return schedule_text(s)
    return (f"Copart scan daily at {int(s['schedule_hour']):02d}:{int(s['schedule_minute']):02d}; "
            f"full update {WEEKDAYS[int(s['schedule_weekday']) % 7]}s")
