# CPRT console

A local macOS app (Flask web UI + CLI + SQLite) that collects alternative data for a two-person college team's **long pitch on Copart (NASDAQ: CPRT)** in a Citadel stock pitch competition. It tracks the data week by week and explains what changed.

The owner is a college student on a Mac, not a professional developer. **Before any non-trivial task, read `PROJECT_CONTEXT.md`.** It covers the investment context, full architecture, data model, research findings about Copart/IAA, known issues and the prioritized backlog.

## Current status (updated Sep 27, 2026)

The seller check is answered (PROJECT_CONTEXT §9): **sellers are hidden** from logged-out visitors, so the insurer split is paused. Per the §10 decision tree, the console pivoted to a **daily Copart scan** (`cprt/market.py`, `capture.run_scan`). The scan loads two public search pages and stores the counts Copart shows for every yard: lots listed, and lots added in the last 7 days. Automated IAA collection isn't possible within the hard rules (§9).

Next, in order:
1. Watch the daily scan. Copart's Imperva protection let an unattended browser through once and then blocked one. "Scan with me" (a guided session) is the fallback. Don't add any workaround for blocks.
2. IAA volumes from RB Global filings (parse the quarterly automotive table; P2 in §10). The owner hasn't yet picked between that and a short weekly manual IAA browse.
3. State Farm badge tracker: lots carry seller badge codes in `lic[]` (§9). Needs validating first.

## Commands (run from the project root)

- First-time setup: `bash setup.command` creates `.venv`, installs requirements and Playwright Chromium, and runs the self-test.
- Activate the environment: `source .venv/bin/activate`
- Start the console: `python app.py` opens http://127.0.0.1:5055. Add `--no-browser` to skip opening a tab.
- Tests (offline, about 20 s, 61 tests): `python cli.py selftest`
- Background tasks, the same ones the UI runs:
  - `python cli.py scheduled` (what launchd runs: the Copart scan daily, the full update on the chosen weekday)
  - `python cli.py scan` (Copart scan, 2 pages)
  - `python cli.py weekly [--scheduled] [--skip-capture]`
  - `python cli.py update news|macro|sec`
  - `python cli.py capture auto`
  - `python cli.py capture guided --platform copart|iaa`
  - `python cli.py report`
  - `python cli.py schedule on|off|status`
- Experiment without touching the owner's data: `CPRT_DATA_DIR=/tmp/cprt-scratch python app.py`

## Layout

- `app.py`: Flask routes and page views.
- `cli.py`: headless commands. The Flask app runs these as subprocesses.
- `cprt/`
  - `paths.py`: data folder location.
  - `settings.py`: settings DEFAULTS and load/save.
  - `db.py`: SQLite schema and helpers.
  - `net.py`: polite HTTP and robots.txt.
  - `capture.py`: Playwright recording, automatic replay, the daily scan (`run_scan`), extraction.
  - `market.py`: Copart scan pages, parsing of Copart's search-result counts, the `inventory` table, and inventory analysis and notes.
  - `infer.py`: values-based field detection.
  - `carriers.py`: seller-name to insurer mapping.
  - `tracker.py`: splits, confidence intervals, significance tests.
  - `weekly.py`: orchestration, snapshots, "what changed" notes.
  - `news.py`, `macro.py`, `sec.py`: collectors.
  - `charts.py`: matplotlib SVG/PNG.
  - `report.py`: weekly HTML report and Excel export.
  - `jobs.py`: background tasks.
  - `scheduler.py`: macOS launchd schedule and notifications.
- `templates/`: Jinja pages plus `report.html`, which is standalone. `help.html` is the in-app manual (How to use): update it whenever a feature, page or number changes.
- `static/`: `style.css` and `app.js` (no JS libraries).
- `tests/`: `helpers.py` (fakes and synthetic data), `test_backend.py`, `test_market.py` (scan and schedule), `test_browser.py` (real Chromium against a fake local auction site), `test_app.py`.
- `data/`: **the owner's history.** Never delete, overwrite or commit it.

## Hard rules

1. **No bot-protection evasion, ever.** No CAPTCHA solving, residential or rotating proxies, stealth plugins, fingerprint or user-agent spoofing, or retrying against blocks. When a site shows a bot check, stop that platform for the run and tell the owner.
2. **No automated collection while logged in** to a Copart or IAA account. Recorded sessions and automatic captures are for logged-out, public pages only.
3. **Respect robots.txt by default** (setting `respect_robots_txt`). On Sep 27, 2026 the owner turned this off for their own install; leave their setting as it is, and keep the default on. Copart's robots.txt allows the scan's pages. Keep polite pacing: 15–30 s random pauses between pages and at most 30 pages per run. Block images, fonts and media.
4. **SEC:** send the owner's real "Name email" User-Agent from settings and stay under 10 requests/second (currently 0.25 s between requests).
5. **Never fabricate, impute or pad data.** Never ship synthetic data in the app itself; it belongs in tests only. Every number must trace to a raw capture or a source URL.
6. **Never destroy user data.** Schema changes need idempotent migrations.
7. **Local only.** Bind to 127.0.0.1, keep the same-origin POST check in `app.py`, and send data nowhere.
8. **Don't write pitch-submission prose** (memo or deck text). The competition restricts AI-generated submissions. Tooling, analysis and charts are fine.

## Conventions

- **Python 3.9+ compatibility.** Put `from __future__ import annotations` at the top of every module. No `match` and no `zip(strict=)`.
- **pandas 2.x and 3.x compatibility.** Compute YoY as `x / x.shift(12) - 1`, not with `pct_change(fill_method=...)`. In pandas 3, `astype(str)` keeps NaN, so call `fillna` first.
- **Dependencies.** Use only the standard library and `requirements.txt`. Ask the owner before adding a dependency.
- **HTTP.** All requests go through `cprt.net.http_get`; tests patch it. Browser automation lives only in `cprt/capture.py`.
- **Settings.** New keys must be added to `DEFAULTS` in `cprt/settings.py`; unknown keys are silently dropped on save. Expose user-facing settings on the Settings page with plain-language help text.
- **Database.** Tables use `CREATE TABLE IF NOT EXISTS`. For new columns, add a guarded `ALTER TABLE` that checks `PRAGMA table_info` first.
- **Long work** runs as a background job through `cli.py` (`cprt/jobs.py`), never inside a Flask request. One job runs at a time.
- **Tests.** Every change gets an offline test. Use `tests/helpers.TempData`, which patches `paths.DATA`, and fake HTTP. Run `python cli.py selftest` before saying you're done.
- **Playwright sync API.** Don't call Playwright methods inside event handlers. Collect `Response` objects and read their bodies afterwards (see `record_session`).
- **UI rules** (details in PROJECT_CONTEXT §7):
  - Copart blue `#2350C9` and IAA red `#C4412F` mean those two companies and nothing else.
  - Amber `#D99A0B` means "needs attention".
  - Barlow typeface; sentence case; plain words.
  - One primary button per page; empty states say what to do next.
  - Keep `[hidden]{display:none!important}` in the CSS.

## Working with the owner

- Explain plans in plain language before big changes, and give exact commands to copy.
- They want maximum automation and minimal manual steps: automatic by default, with a clear fallback.
- Say what's verified and what isn't. When you test against live Copart/IAA pages, send one polite request at a time and follow the hard rules.
- There's deadline pressure: the first round is due in early October 2026 (confirm the exact date with the owner). Prefer small, working increments.
