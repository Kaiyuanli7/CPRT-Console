"""Collect Copart / IAA listings with as little manual work as possible.

Two modes, both feeding the same database:

* Recorded session ("guided"): a browser window opens and you browse normally -
  search a state, open a few result pages, close the window. Every lot your
  browser receives is saved, and the pages that returned lots are remembered.
* Automatic replay ("auto"): revisits the remembered pages, weekly or on demand.

The browser only records data the site already sends to it. No logins, no
CAPTCHA solving, no disguises; robots.txt is respected and a blocked page stops
that site for the day.
"""
from __future__ import annotations

import gzip
import json
import random
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from . import carriers, db, infer, market, net, paths

TOTAL_KEY = re.compile(r"^(total(Elements|Records|Count|Hits|Results)|numFound|recordsTotal|resultCount)$", re.I)
PLATFORM_HOSTS = {"copart": "copart", "iaa": "iaai"}
VEHICLE_FIELDS = {"make", "model"}  # yard, sale and reference lists have IDs and states but never a make or model
DATED_PAGE = re.compile(r"/\d{4}-\d{2}-\d{2}(?=[/?#]|$)")  # pages for one sale day, e.g. /saleListResult/366/2026-09-28
EMPTY_PAGES_BEFORE_STOP = 2  # saved pages in a row with no lots before a site is left alone for the run


# ---------------------------------------------------------------- extraction
def iter_dict_lists(obj, path: str = "$"):
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:10]):
            yield path, obj
        for i, x in enumerate(obj[:50]):
            yield from iter_dict_lists(x, f"{path}[{i}]")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_dict_lists(v, f"{path}.{k}")


def lot_lists(data, field_overrides: dict | None = None):
    """Yield (path, records, mapping) for every list in `data` that looks like vehicle lots.

    A lot list needs an ID, a make or model, and at least two lot fields. Copart's yard directory has ID-like zip
    codes, "ST - CITY" names and state codes, so without the vehicle check its yards were saved as lots.
    """
    for path, lst in iter_dict_lists(data):
        if len(lst) < 3:
            continue
        mapping, _ = infer.infer_mapping(lst, field_overrides)
        if ("lot_id" in mapping and mapping.keys() & VEHICLE_FIELDS
                and len(set(mapping) & {"seller", "make", "year", "yard", "state", "damage"}) >= 2):
            yield path, lst, mapping


def normalize(records: list[dict], mapping: dict, platform: str, label: str = "", source_url: str = "") -> list[dict]:
    rows = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        flat = infer.flatten(rec)

        def get(field):
            key = mapping.get(field)
            v = flat.get(key) if key else None
            return "" if v is None else str(v).strip()

        lot_id = get("lot_id")
        if not lot_id:
            continue
        yard = get("yard")
        rows.append({
            "platform": platform, "lot_id": lot_id,
            "state": infer.parse_state(get("state"), yard, label), "yard": yard,
            "seller_raw": get("seller"), "make": get("make"), "model": get("model"),
            "year": get("year").replace(".0", ""), "damage": get("damage"),
            "sale_date": infer.to_date(flat.get(mapping["sale_date"])) if "sale_date" in mapping else "",
            "source_url": source_url,
        })
    return rows


def extract(payloads: list[dict], platform: str, field_overrides: dict | None = None,
            label: str = "", default_url: str = "") -> list[dict]:
    """All unique lots found in a list of captured JSON payloads."""
    seen, rows = set(), []
    for p in payloads:
        for _, lst, mapping in lot_lists(p["data"], field_overrides):
            for r in normalize(lst, mapping, platform, label, p.get("page_url") or default_url):
                if r["lot_id"] not in seen:
                    seen.add(r["lot_id"])
                    rows.append(r)
    return rows


def find_total(payloads: list[dict]) -> int | None:
    best = None

    def walk(o):
        nonlocal best
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, int) and not isinstance(v, bool) and TOTAL_KEY.match(str(k)):
                    best = max(best or 0, v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o[:50]:
                walk(x)

    for p in payloads:
        walk(p["data"])
    return best


def looks_blocked(title: str, text: str, html: str = "") -> bool:
    return net.looks_like_bot_check(title, text, html)


def clean_url(url: str) -> str:
    """Drop fragments and tracking parameters so the same page isn't saved twice."""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith(("utm_", "gclid", "fbclid"))]
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


def platform_of(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    for platform, needle in PLATFORM_HOSTS.items():
        if needle in host:
            return platform
    return None


# ---------------------------------------------------------------- browser
def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright is not installed. Run setup again (it installs everything).") from None
    return sync_playwright


def _is_json(response) -> bool:
    try:
        return "json" in (response.headers.get("content-type") or "")
    except Exception:
        return False


def _frame_url(response) -> str:
    try:
        return response.frame.url
    except Exception:
        return ""


def _skip_heavy_files(page) -> None:
    """Don't download images, media or fonts (hard rule 3: keep volumes small)."""
    page.route("**/*", lambda route: route.abort()
               if route.request.resource_type in ("image", "media", "font") else route.continue_())


def capture_page(url: str, show_browser: bool = True, wait_seconds: int = 10, scrolls: int = 4) -> dict:
    """Open one page, let it load its data, return the JSON it received."""
    responses = []
    with _playwright()() as p:
        browser = p.chromium.launch(headless=not show_browser)
        context = browser.new_context(viewport={"width": 1366, "height": 900}, locale="en-US")
        page = context.new_page()
        _skip_heavy_files(page)
        context.on("response", lambda r: responses.append((r, _frame_url(r))) if _is_json(r) else None)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(wait_seconds * 1000)
        for _ in range(scrolls):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)
        payloads = []
        for r, frame_url in responses:
            try:
                payloads.append({"url": r.url, "page_url": url, "data": r.json()})
            except Exception:
                continue
        result = {"payloads": payloads, "title": page.title(), "text": page.inner_text("body")[:200_000],
                  "html": page.content()[:20_000]}  # enough to recognise a block page hidden inside a frame
        context.close()
        browser.close()
    return result


def fetch_text(url: str, show_browser: bool = True, wait_seconds: int = 7) -> tuple[int, str]:
    """Read a plain-text page (robots.txt) with the capture browser: (status, text), or the block page's HTML."""
    with _playwright()() as p:
        browser = p.chromium.launch(headless=not show_browser)
        page = browser.new_context(locale="en-US").new_page()
        _skip_heavy_files(page)
        resp = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(wait_seconds * 1000)
        title, text, html = page.title(), page.inner_text("body"), page.content()
        status = resp.status if resp else 0
        browser.close()
    if looks_blocked(title, text, html):
        return status or 403, html
    # a bot-protection check that the browser passed can leave the first response's status behind
    return (200 if "user-agent" in text.lower() else status), text


def record_session(start_url: str, max_minutes: int = 30, stop_file: Path | None = None,
                   on_payload=None, show_browser: bool = True, script=None) -> list[dict]:
    """Open a browser for the person to use; record JSON responses until the window closes.

    `script(page)` is a testing hook that drives the browser instead of a person.
    """
    pending, payloads = [], []
    with _playwright()() as p:
        browser = p.chromium.launch(headless=not show_browser)
        context = browser.new_context(no_viewport=True) if show_browser else browser.new_context()
        context.on("response", lambda r: pending.append((r, _frame_url(r))) if _is_json(r) else None)
        page = context.new_page()
        page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
        deadline = time.monotonic() + max_minutes * 60

        def drain():
            while pending:
                r, frame_url = pending.pop(0)
                try:
                    item = {"url": r.url, "page_url": frame_url, "data": r.json()}
                except Exception:
                    continue
                payloads.append(item)
                if on_payload:
                    on_payload(item)

        if script:
            script(page, drain)
        while time.monotonic() < deadline:
            drain()
            if stop_file is not None and stop_file.exists():
                break
            open_pages = [pg for pg in context.pages if not pg.is_closed()]
            if not open_pages:
                break
            try:
                open_pages[0].wait_for_timeout(500)  # keeps browser events flowing
            except Exception:
                break
        drain()
        try:
            context.close()
            browser.close()
        except Exception:
            pass
    return payloads


def save_raw(payloads: list[dict], name: str) -> Path:
    """Gzip the payloads into data/raw. Names carry the time, so a second capture that day never overwrites one."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = paths.data_path("raw", f"{stamp}_{name}.json.gz")
    n = 2
    while path.exists():
        path = paths.data_path("raw", f"{stamp}_{name}_{n}.json.gz")
        n += 1
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payloads, f, default=str)
    return path


# ---------------------------------------------------------------- storage helpers
def store(rows: list[dict], origin: str, obs_date: str | None = None) -> int:
    d = obs_date or date.today().isoformat()
    return db.save_observations([{**r, "obs_date": d, "origin": origin} for r in rows])


def majority_state(rows: list[dict]) -> str:
    states = Counter(r["state"] for r in rows if r.get("state"))
    if not states:
        return ""
    state, n = states.most_common(1)[0]
    return state if n >= 0.6 * sum(states.values()) else "Mixed"


def learn_sources(rows: list[dict], platform: str, min_lots: int, skip: set[str] = frozenset()) -> list[dict]:
    """Remember every page that returned enough lots, so it can be replayed weekly (except pages in `skip`)."""
    by_page = defaultdict(list)
    for r in rows:
        if r.get("source_url"):
            by_page[clean_url(r["source_url"])].append(r)
    added = []
    for url, page_rows in by_page.items():
        if (len(page_rows) < min_lots or not url.startswith("http") or url in skip
                or DATED_PAGE.search(urlparse(url).path)):
            continue  # a page for one sale day is empty once that sale is over
        rec = {"platform": platform, "url": url, "label": majority_state(page_rows), "enabled": 1,
               "origin": "recorded", "added": db.now(), "last_run": db.now(), "last_status": "ok",
               "last_lots": len(page_rows)}
        if db.upsert("sources", [rec], ["url"]):
            added.append(rec)
        else:
            db.execute("UPDATE sources SET last_run=?, last_status='ok', last_lots=? WHERE url=?",
                       (db.now(), len(page_rows), url))
    return added


# ---------------------------------------------------------------- commands
def run_guided(settings: dict, platform: str, start_url: str | None = None, stop_file: Path | None = None,
               progress=print, script=None, show_browser: bool | None = None) -> dict:
    start_url = start_url or settings["start_urls"][platform]
    overrides = settings.get("field_overrides") or None
    seen: dict[str, dict] = {}
    pages: set[str] = set()
    payloads: list[dict] = []
    counted: dict[str, str] = {}  # site-wide Copart count view -> the page it came from
    last_report = [0.0]

    def on_payload(item):
        payloads.append(item)
        try:
            for r in extract([item], platform, overrides):
                seen.setdefault(r["lot_id"], r)
                if r["source_url"]:
                    pages.add(r["source_url"])
            _save_counts(item, counted, progress)
        except Exception as exc:  # one odd response must never end a recording
            progress(f"Skipped one data feed the console couldn't read ({exc}).")
            return
        if time.monotonic() - last_report[0] > 2:
            with_seller = sum(1 for r in seen.values() if r["seller_raw"])
            progress(f"Recording: {len(seen)} lots ({with_seller} with seller names) from {len(pages)} pages",
                     lots=len(seen), with_seller=with_seller, pages=len(pages))
            last_report[0] = time.monotonic()

    progress(f"Opening {start_url} - browse normally, then close the window when you're done.")
    finished = False
    try:
        record_session(start_url, settings["guided_max_minutes"], stop_file, on_payload,
                       settings["show_browser"] if show_browser is None else show_browser, script)
        finished = True
    finally:  # keep everything recorded so far, even when the browser crashes
        if not finished:
            progress(f"The browser stopped unexpectedly. Saving the {len(seen)} lots recorded before that.")
        summary = _save_recording(settings, platform, payloads, list(seen.values()), len(pages), progress, counted)
    return summary


def _save_counts(item: dict, counted: dict, progress) -> None:
    """Site-wide Copart counts seen while recording ("Scan with me") go to the inventory tracker."""
    if not market.is_search_results(item):
        return
    view = market.view_of(item)
    parsed = market.parse_search([item], view) if view in market.VIEW_LABELS else None
    if parsed:
        market.store(date.today().isoformat(), view, parsed, item.get("page_url") or market.SEARCH)
        counted[view] = clean_url(item.get("page_url") or "")
        progress(f"Saved Copart's counts for {market.VIEW_LABELS[view]}: {parsed['total']:,} lots.")


def _save_recording(settings: dict, platform: str, payloads: list[dict], rows: list[dict], n_pages: int,
                    progress, counted: dict) -> dict:
    if payloads:
        save_raw(payloads, f"{platform}_recorded")
    saved = store(rows, "recorded")
    # pages that answered a site-wide count are covered by the daily scan, so they aren't replayed as well
    learned = learn_sources(rows, platform, settings["learn_sources_min_lots"], skip=set(counted.values()))
    with_seller = sum(1 for r in rows if r["seller_raw"])
    summary = {"platform": platform, "lots": len(rows), "with_seller": with_seller, "saved": saved,
               "pages": n_pages, "sources_learned": len(learned), "counts": sorted(counted)}
    counts = f" Copart counts saved for {' and '.join(market.VIEW_LABELS[v] for v in sorted(counted))}." if counted else ""
    progress(f"Saved {len(rows)} lots ({with_seller} with seller names). "
             f"{len(learned)} new pages added to weekly auto-capture.{counts}", **summary)
    return summary


def run_scan(settings: dict, progress=print, capture_fn=None, show_browser: bool | None = None) -> dict:
    """The daily Copart scan: two public search pages whose counts cover every Copart yard (see market.py).

    Stops at the first bot check and keeps what was already captured. Raises when nothing was captured, so the
    task and Data freshness show a failure instead of OK.
    """
    capture_fn = capture_fn or capture_page
    show = settings["show_browser"] if show_browser is None else show_browser
    today = date.today().isoformat()
    out = {"platform": "copart", "date": today, "pages": 0, "blocked": False}
    problems = []
    for i, (view, url) in enumerate(market.SCAN_PAGES.items(), 1):
        label = market.VIEW_LABELS[view]
        if settings["respect_robots_txt"]:
            try:
                allowed = net.robots_allows(url, fetch=lambda u: fetch_text(u, show))
            except net.RobotsBlocked:
                out["blocked"] = True
                break
            except Exception as exc:  # the browser failed while reading robots.txt
                problems.append(f"Copart's robots.txt couldn't be read ({exc}).")
                continue
            if not allowed:
                problems.append(f"Copart's robots.txt asks automated tools not to load the page of {label}.")
                continue
        if out["pages"]:
            time.sleep(random.uniform(*settings["pause_between_pages"]))
        progress(f"Copart scan: {label} ({i} of {len(market.SCAN_PAGES)})")
        try:
            result = capture_fn(url, show, settings["page_wait_seconds"], 0)
        except Exception as exc:  # a crashed page shouldn't cost the other one
            problems.append(f"The page of {label} didn't load ({exc}).")
            continue
        parsed = market.parse_search(result["payloads"], view)
        if parsed is None:
            if looks_blocked(result.get("title", ""), result.get("text", ""), result.get("html", "")):
                out["blocked"] = True
                break
            problems.append(f"The page of {label} loaded without Copart's lot counts, so the site may have changed.")
            continue
        save_raw([p for p in result["payloads"] if "/public/lots/" in p.get("url", "")], f"copart_scan_{view}")
        market.store(today, view, parsed, url)
        out[view] = parsed["total"]
        out["pages"] += 1
        progress(f"  {parsed['total']:,} lots across {len(parsed['facets'].get('yard', {}))} yards")
    for problem in problems:
        progress(problem)
    if out["blocked"]:
        progress("Copart showed a bot check, so the scan stopped for today instead of retrying.")
    if not out["pages"]:
        raise RuntimeError("Copart showed a bot check, so nothing was scanned today. The console stops instead of "
                           "retrying." if out["blocked"] else " ".join(problems) or "Nothing was scanned.")
    return out


def run_auto(settings: dict, progress=print, capture_fn=None, show_browser: bool | None = None,
             pause_first: bool = False) -> dict:
    """Replay the saved pages. `pause_first` waits before the first page too (when another capture just ran)."""
    capture_fn = capture_fn or capture_page
    sources = db.query("SELECT * FROM sources WHERE enabled=1 ORDER BY platform, id")
    if not sources:
        progress("No saved pages yet. Record a browsing session on Copart and IAA first.")
        return {"pages": 0, "lots": 0, "blocked": []}
    overrides = settings.get("field_overrides") or None
    show = settings["show_browser"] if show_browser is None else show_browser
    blocked, total_lots, pages = set(), 0, 0
    empty_in_a_row: dict[str, int] = {}
    for src in sources[: settings["max_pages_per_run"]]:
        platform = src["platform"]
        if platform in blocked:
            continue
        if settings["respect_robots_txt"]:
            try:
                allowed = net.robots_allows(src["url"], fetch=lambda u: fetch_text(u, show))
            except net.RobotsBlocked:
                blocked.add(platform)
                db.execute("UPDATE sources SET last_run=?, last_status='blocked' WHERE id=?", (db.now(), src["id"]))
                progress(f"  {platform} showed a bot check instead of its robots.txt. Skipping {platform} for today.")
                continue
            except Exception as exc:  # the browser failed while reading robots.txt: skip this page, keep going
                db.execute("UPDATE sources SET last_run=?, last_status=? WHERE id=?",
                           (db.now(), f"error: {str(exc)[:80]}", src["id"]))
                progress(f"  couldn't read {platform}'s robots.txt ({exc}); skipped this page.")
                continue
            if not allowed:
                db.execute("UPDATE sources SET last_run=?, last_status='robots.txt disallows' WHERE id=?",
                           (db.now(), src["id"]))
                progress(f"Skipped {platform} page (robots.txt disallows it).")
                continue
        if pages or pause_first:
            time.sleep(random.uniform(*settings["pause_between_pages"]))
        progress(f"Capturing {platform} [{src['label'] or 'page'}] ({pages + 1} of {min(len(sources), settings['max_pages_per_run'])})")
        try:
            result = capture_fn(src["url"], show, settings["page_wait_seconds"], settings["scrolls_per_page"])
        except Exception as exc:  # network error, browser crash...
            db.execute("UPDATE sources SET last_run=?, last_status=? WHERE id=?",
                       (db.now(), f"error: {str(exc)[:80]}", src["id"]))
            progress(f"  error: {exc}")
            continue
        pages += 1
        rows = extract(result["payloads"], platform, overrides, src["label"], src["url"])
        if not rows and looks_blocked(result.get("title", ""), result.get("text", ""), result.get("html", "")):
            blocked.add(platform)
            db.execute("UPDATE sources SET last_run=?, last_status='blocked' WHERE id=?", (db.now(), src["id"]))
            progress(f"  {platform} showed a bot check. Skipping {platform} for today.")
            continue
        if result["payloads"]:
            save_raw(result["payloads"], f"{platform}_auto_{src['id']}")
        store(rows, "auto")
        total_lots += len(rows)
        status = "ok" if rows else "no lots found"
        db.execute("UPDATE sources SET last_run=?, last_status=?, last_lots=? WHERE id=?",
                   (db.now(), status, len(rows), src["id"]))
        progress(f"  {len(rows)} lots ({sum(1 for r in rows if r['seller_raw'])} with seller names)")
        empty_in_a_row[platform] = 0 if rows else empty_in_a_row.get(platform, 0) + 1
        if empty_in_a_row[platform] >= EMPTY_PAGES_BEFORE_STOP:  # may be a bot check no marker recognises
            blocked.add(platform)
            progress(f"  {EMPTY_PAGES_BEFORE_STOP} {platform} pages in a row came back empty, which can mean a bot "
                     f"check. Stopping {platform} for today.")
    summary = {"pages": pages, "lots": total_lots, "blocked": sorted(blocked)}
    progress(f"Automatic capture finished: {total_lots} lots from {pages} pages."
             + (f" Blocked today: {', '.join(sorted(blocked))}." if blocked else ""))
    return summary


# ---------------------------------------------------------------- hand entry helpers
PASTE_PATTERNS = {
    "lot_id": [r"Lot\s*(?:#|Number|No\.?)\s*:?\s*([A-Z0-9-]{5,14})", r"Stock\s*(?:#|Number|No\.?)\s*:?\s*([A-Z0-9-]{5,14})"],
    "seller_raw": [r"Seller(?:\s*Name)?\s*:?\s*\n?\s*([A-Za-z0-9&'.,/ -]{3,60})"],
    "damage": [r"Primary\s+Damage\s*:?\s*\n?\s*([A-Za-z /-]{3,40})", r"Loss\s+Type\s*:?\s*\n?\s*([A-Za-z /-]{3,40})"],
    "yard": [r"(?:Location|Selling\s+Branch|Yard|Branch)\s*:?\s*\n?\s*([A-Za-z0-9 ().,-]{3,50})"],
}
TITLE = re.compile(r"\b((?:19|20)\d{2})\s+([A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+)?)\s+([A-Z0-9][A-Za-z0-9-]+)")


def parse_listing_text(text: str) -> dict:
    """Best-effort fill of the hand-entry form from text copied off a listing page."""
    out = {}
    for field, pats in PASTE_PATTERNS.items():
        for pat in pats:
            m = re.search(pat, text, re.I)
            if m:
                out[field] = m.group(1).strip().split("\n")[0].strip()
                break
    m = TITLE.search(text)
    if m:
        make = m.group(2).upper()
        if make.split()[0] in {x.split()[0] for x in infer.MAKES}:
            out.update(year=m.group(1), make=make.split()[0] if make not in infer.MAKES else make, model=m.group(3).upper())
    state = infer.parse_state(out.get("yard", ""))
    if state:
        out["state"] = state
    if "seller_raw" in out:
        out["carrier_guess"] = carriers.canonical(out["seller_raw"])
    return out
