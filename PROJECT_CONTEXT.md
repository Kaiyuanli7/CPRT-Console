# CPRT console: full project context

This is the complete reference for anyone, human or AI, working on this codebase. `CLAUDE.md` holds the rules that apply in every session; this file explains *why* things are the way they are and *what to build next*.

Contents:

1. Who this is for and what they're trying to do
2. Investment context: what the data needs to prove or disprove
3. What the console does today
4. Architecture
5. Data model
6. Settings reference
7. UI and design system
8. Collection details, per source
9. Research findings about Copart and IAA
10. Decision tree and backlog
11. Verification status
12. Testing
13. Gotchas and lessons learned
14. Decision log
15. Glossary

---

## 1. Who this is for and what they're trying to do

**The owner** is a college student on a two-person team pitching a **long position in Copart, Inc. (CPRT)** in a Citadel stock pitch competition. They work on a Mac and aren't a professional developer. They want tools that are intuitive and automatic, with as little manual work as possible.

The team's own primer calls the event the "Citadel Associate Program / HFAC Stock Pitch Competition". Citadel's Fall 2026 pitch competition rules list a first-round deadline of **October 2, 2026** and finals on **October 23, 2026**. Confirm with the owner which rulebook applies. Those rules also restrict AI-generated submissions and require public information.

**What the console is for.** It produces independent, defensible **alternative data** that tests the key claims in the pitch, plus exports for the pitch model and deck: an Excel workbook and PNG charts. Judges will ask "how did you get this?", so every number must trace back to a raw capture or a source link.

**How the owner likes to work:**
- Depth over speed for deep dives, and honest verdicts rather than cheerleading.
- Always include primary-research steps they can do as a student.
- Plain-language explanations and exact commands.

## 2. Investment context: what the data needs to prove or disprove

Copart runs online salvage auctions; most vehicles come from insurers as total losses. Its main rival is **IAA** (Insurance Auto Auctions), owned by **RB Global (ticker RBA)**. In US insurance salvage the two form a duopoly.

**The core debate.** Copart's US insurance volumes have fallen for five straight quarters. The market reads that as structural share loss to IAA. The long thesis argues the loss is concentrated in one customer and partly offset, and that secular drivers remain intact.

Key facts from the team's research files (broker notes, expert calls and filings, as of late September 2026):

| Topic | Fact | Source |
|---|---|---|
| F4Q26 (quarter ended Jul 31, reported Sep 10, 2026) | Revenue $1.152B (+2.4%); EPS $0.35 vs $0.38 consensus; gross margin 41.8%; operating income $369M (−10.6%); US insurance units −7.5%; opex per unit +13% | Company; JPM and Barclays notes |
| Lost customer | **Progressive** moved salvage to IAA: roughly 75/25 IAA/Copart before, about 95/5 after an A/B test IAA won on speed. Migration finishing around end of September 2026 | Ex-GEICO SVP call (9/3/26); JPM F4Q note |
| Offsetting win | **GEICO** moved toward Copart: about 83/17 to 95/5 Copart/IAA. But by written premium, Progressive's loss is about 4× GEICO's gain | Same expert; Barclays |
| Ex-Progressive growth | Assignments excluding the lost customer: **+2.3%** in F4Q | Management, F4Q call |
| Market share | JPM/autoAstat rolling 12-week: **Copart 57.9% / IAA 42.1%** (Sep 11, 2026), vs about 62/38 in 2025 | JPM, Barclays |
| Net volume effect | Barclays: Copart volumes −2.5% to −3.5%, RBA +4% to +6%, Copart take-rate hit 25–50 bp. Industry data: Copart −1.4% vs RBA +14.9% in May–June | Barclays (7/21 and 8/25/26) |
| Swing factor | IAA says it gained share with its two largest customers (JPM believes State Farm and Progressive). State Farm is about 19% of US personal-auto premiums. JPM expects a busy insurer RFP cycle over the next 2–3 years | JPM |
| Secular tailwind | Total-loss frequency at a record **~23%** (CCC 2025: 23.1%; management: 23.3%) | CCC, company |
| Cyclical argument | Insurance premium spikes led drivers to drop coverage; cooling premiums should bring insured volumes back | Management, expert calls |
| M&A | ACV Auctions (ACVA): $10.50 per share cash, about $1.9B, about 45% premium; EPS-neutral FY27, accretive FY28 (JPM models ~1.9%). Reported interest in CCC Intelligent Solutions and Pickles Australia. JPM suspended its rating because it advises ACV | Filings, broker notes |
| Legal risk | DOJ anti-money-laundering investigation, disclosed since an October 2023 letter; no loss range given. Not covered in any broker note | 10-K/10-Q |
| Valuation | About $27.6 (Sep 25, 2026), near the 52-week low of $26.81; about −30% YTD; roughly 17× earnings | Market data |

**What the console must help show:**
1. Whether Copart's share loss is **one carrier (Progressive), or spreading** to State Farm, Allstate or USAA. This is the most valuable question and the hardest; see §9.
2. **Platform volume trends** measured independently, i.e. the team's own version of "Copart −3.5% vs RBA +11.8%".
3. **Structural total-loss pressure**: repair prices outrunning used-car values.
4. The **coverage-comeback** argument: insurance price inflation cooling.
5. **Progressive's growth slowing**, since Progressive is IAA's biggest tailwind.
6. Whether the **DOJ disclosure** wording changes.
7. What other investors are already seeing: news that cites alt data.

## 3. What the console does today

| Page | Contents |
|---|---|
| **This week** (`/`) | Hero split bar: Copart vs IAA share of insurance lots, with a 95% CI whisker and a dashed JPM 57.9% reference line. Insurer table with split bars, week-over-week change and significance. "This week's notes" (auto-generated, ranked). Signals: total-loss pressure index, insurance CPI YoY, Progressive direct-auto growth, DOJ status. Data freshness with "Update" buttons. First-run onboarding: name and email, then first update, then record sessions. |
| **Insurer tracker** (`/tracker`) | Tabs: **Results** (week picker; split table with CI, lots, change, expert claim; weekly trend chart; coverage by state; by-state table), **Collect data** (Record on Copart/IAA; capture saved pages; hand entry with paste-to-fill), **Saved pages** (sources with on/off, status, remove, add URL), **Data quality** (seller-name coverage; unmatched sellers with one-click insurer assignment; overrides), **All lots** (filters, CSV download). |
| **Macro** (`/macro`) | FRED charts: total-loss pressure (repair ÷ used-car CPI, 2019 = 100), repair vs used YoY, insurance CPI YoY, miles traveled YoY. PNG downloads. |
| **Filings** (`/filings`) | Progressive monthly table and chart (policies in force, growth, combined ratio); DOJ tracker with word-level diffs; release excerpts by ticker and keyword; SEC full-text hits. |
| **News** (`/news`) | Google News and trade-feed articles ranked by an alt-data term score. Views: all, new this week, unread, starred. |
| **Reports** (`/reports`) | Weekly self-contained HTML report (printable); Excel export of everything; PNG chart links. |
| **Settings** (`/settings`) | Details; weekly auto-update on/off with day and time; tracked insurers and expert claims; collection pace; news and SEC searches; advanced field overrides; delete listing data. |
| **Copart inventory** (`/inventory`) | The daily scan's counts: lots listed in US yards, lots added in the last 7 days, added yesterday, US locations; week-over-week changes; trend charts; by-state table; Scan now and Scan with me. |
| **How to use** (`/help`) | The manual: a live setup checklist (details, auto-update, latest scan and full update), then every page and number explained with the owner's current values as examples, tracing numbers to sources, limits, troubleshooting, behind the scenes and a glossary. |
| **Guide** (`/guide`) | Method, caveats for Q&A, ground rules. Points to How to use for troubleshooting. |

**Automation already in place:**
- The weekly launchd job runs news, macro, SEC, saved-page capture, analysis and report, then sends a macOS notification. If the Mac was asleep at the scheduled time, it runs on wake.
- Values-based field detection: no manual mapping.
- Sources are learned from recorded sessions.
- Insurer mapping, with one-click fixes.
- Significance-tested notes.
- Excel and PNG exports.

## 4. Architecture

```
Browser (UI) --HTTP--> app.py (Flask, 127.0.0.1:5055)
                        |-- renders templates/ using cprt/* (tracker, macro, sec, weekly...)
                        |-- POST /api/jobs/<kind> --> cprt/jobs.start()
                        |                               `-- subprocess: python cli.py <args> --job-id ID
                        |                                     |-- cprt.weekly / news / macro / sec / capture / report
                        |                                     `-- writes data/jobs/ID.json (status) and ID.log
                        `-- GET /api/job  <-- polled by static/app.js every 1.5 s (banner, then reload when done)
launchd (weekly) --> python cli.py weekly --scheduled   (same code path; notification when done)
All modules --> cprt/db.py (SQLite data/console.db, WAL) and cprt/paths.py (data folder, CPRT_DATA_DIR)
```

**Module responsibilities:**

- **`paths.py`**: `ROOT`, `DATA` (env var `CPRT_DATA_DIR`) and `data_path()`, which creates folders on demand.
- **`settings.py`**: `DEFAULTS`, `load()`, `save()`, `update()`, `sec_user_agent()`, `is_configured()`, `schedule_text()`. Unknown keys are dropped on save.
- **`db.py`**: `SCHEMA`, `connect()`, `df()`, `query()`, `scalar()`, `execute()`, `upsert()`, `save_observations()` (a same-day repeat sighting only fills blanks), `log_run()`, `last_runs()`, `last_success()`.
- **`net.py`**: `http_get()` with per-host throttle and urllib3 retries (429 and 5xx, backoff 2), plus `robots_allows()` following RFC 9309 (4xx means allowed; 5xx or unreachable means disallowed).
- **`carriers.py`**: ordered regex patterns that roll subsidiaries up to parent groups (National General, Esurance and Direct General → Allstate; Safeco → Liberty Mutual; Bristol West, 21st Century and Foremost → Farmers; Infinity → Kemper). Overrides are exact normalized seller names set in the UI. `GROUPS` is the list shown in UI dropdowns.
- **`infer.py`**: profiles every JSON field of a record list and scores it for each target (`lot_id`, `seller`, `state`, `yard`, `make`, `model`, `year`, `damage`, `sale_date`) using features such as unique, id_like, fixed_len, named_carrier, state_code, state_in_text, make, year, damage, date, numeric and avg_len. Name hints only break ties. Assignment is greedy in `ORDER`, and overrides take priority. Also provides `flatten()` (two levels, skips lists), `parse_state()` and `to_date()` (epoch seconds or milliseconds, or ISO).
- **`market.py`**:
  - `SCAN_PAGES`: the all-lots and newly-added-in-7-days search addresses.
  - `view_of()`: reads the query Copart echoes back, so only site-wide responses count.
  - `parse_search()`, `store()` (to the `inventory` table), and analysis: `day_totals()`, `by_state()` (US only), `week_earlier()` (a scan 5 to 9 days before), `history()`, `summary()` and `notes()`.
- **`capture.py`**:
  - `run_scan()`: the daily Copart scan. Robots.txt is read through the browser when that setting is on. The scan stops at a bot check, keeps what it already captured, and raises if nothing was captured.
  - `record_session()` (guided): a headed browser; responses are queued in the event handler and bodies drained in a loop. Guided sessions also save site-wide Copart counts ("Scan with me"). It stops when the window closes, the stop file appears or the timeout hits. There is a `script(page, drain)` test hook.
  - `capture_page()` (auto): blocks images, media and fonts; waits, scrolls, then reads JSON bodies.
  - `extract()`: `lot_lists()` (finds lists of dicts with an inferred lot_id plus two or more other fields), `normalize()` and de-duplication.
  - `find_total()`, `looks_blocked()` (marker phrases), `clean_url()` (drops fragments and utm/gclid/fbclid parameters) and `platform_of()`.
  - `store()`, `learn_sources()` (pages with at least `learn_sources_min_lots` lots; label is the majority state at 60%+, otherwise "Mixed").
  - `run_guided()`, `run_auto()` (robots check, random pauses, page cap; a bot check blocks that platform for the run; per-source status) and `parse_listing_text()` (paste-to-fill).
- **`tracker.py`**:
  - `load()`: maps seller to group with overrides; week is the Monday.
  - `paired()`: keeps only states with both platforms. `share_table()` gives counts, share, and Wilson CI lo/hi.
  - `two_prop_p()`, `metrics()` (the default week is the latest; returns overall insurers-only split, carriers, coverage, seller coverage, and paired/unpaired states), `weekly_history()` (adds an "All insurers" row), `state_table()`, `new_lot_flow()` (excludes each platform's first week) and `unmapped_sellers()`.
- **`weekly.py`**:
  - `snapshot()` covers tracker metrics, latest macro, the last three Progressive months, DOJ status and news counts.
  - `what_changed(s, cur, prev_week_metrics)` returns notes with levels **alert**, **action**, **good** and **info**, shown as "Needs attention", "To do", "Supports the long" and "Note".
  - `previous_data_week()`, `current()`, `run()`. Steps are logged to `runs`; an SEC step without user details is "skipped", not failed. After the steps come snapshot and report.
- **`news.py`**: Google News RSS per query, plus extra RSS/Atom feeds filtered by keywords. De-duplicates by normalized title, scores by `alt_data_terms`, and records `first_seen`.
- **`macro.py`**: fetches FRED CSVs into the `macro` table. `frame()` builds YoY columns, `pressure_repair` and `pressure_parts` (ratio to used-car CPI, 2019 average = 100) and `repair_minus_used`. `latest()` returns latest values, the year-ago pressure value and the insurance CPI peak since 2022.
- **`sec.py`**:
  - `cik_for()`, `filings()`, `html_to_text()`, `snippets()`.
  - `parse_progressive()`: best-effort regexes for period, combined ratio (current and prior), and direct/agency auto policies in force with growth.
  - `releases()`: 8-K exhibit-99 files matched with the `EXHIBIT_99` regex.
  - `fulltext()` (efts search-index), `doj()` (similarity after stripping digits; below 0.95 counts as changed), `word_diff()`, `doj_status()`. `SecConfigError` is raised when user details are missing.
- **`charts.py`**: matplotlib with palette constants.
  - `lines()`: 9.6 in wide; legend below the plot; `PercentFormatter`; ticks at data points when there are fewer than 16 points.
  - `weekly_shares()`: "All insurers" line emphasized.
  - `split_bars()`: PNG version of the split bar for slides.
- **`report.py`**: `build()` writes the Jinja `report.html` with base64 PNGs to `data/reports/CPRT_weekly_<week>.html`. `list_reports()`. `excel()` produces sheets: Read me, Insurer split (latest), By state (latest), Weekly history, New lot flow, All lots, Macro, Progressive monthly, DOJ disclosures, News, SEC full-text hits and Release snippets.
- **`jobs.py`**: `start()` refuses if a job is running; it spawns `cli.py` with `--job-id` and `CPRT_DATA_DIR`. Also `write_status()`, `latest()` (marks dead "running" jobs as failed and attaches a 14-line log tail), `running()`, `request_stop()` and `stop_file()`. `LABELS` holds UI names.
- **`scheduler.py`**: label `com.cprtconsole.weekly`, plist at `~/Library/LaunchAgents/`. `ProgramArguments` is `[sys.executable, cli.py, weekly, --scheduled]` and `StartCalendarInterval` sets weekday, hour and minute. Logs go to `data/logs/scheduled.log`. `install()` tries `launchctl bootstrap gui/<uid>` and falls back to `load -w`; `uninstall()` uses bootout or unload. Also `status()`, `protected_folder_warning()` and `notify()` (osascript).
- **`app.py` routes:**
  - Pages: `/`, `/tracker` (`?tab=results|collect|sources|quality|lots`, `&week=`), `/macro`, `/filings` (`?ticker=&keyword=`), `/news` (`?view=all|new|unread|starred&q=&min=`), `/reports`, `/settings`, `/inventory`, `/help`, `/guide`.
  - Tracker actions (POST): `/tracker/manual`, `/tracker/paste`, `/tracker/mapping`, `/tracker/sources/<id>/toggle|delete`, `/tracker/sources/add`.
  - Downloads: `/tracker/lots.csv`, `/charts/<split|weekly|pressure|spread|insurance|vmt|progressive>.png`, `/reports/<name>` (`?download=1`), `/export/excel`.
  - News and settings (POST): `/news/<key>/<star|unstar|read|unread>`, `/settings/profile`, `/settings` (`section=schedule|tracking|collection|news|sec|advanced`), `/settings/schedule/<on|off>`, `/settings/test-notification`, `/settings/reset-listings`.
  - Jobs API: `POST /api/jobs/<weekly|news|macro|sec|capture_auto|report|capture_guided>` (guided takes a JSON body `{"platform": ...}`), `GET /api/job`, `POST /api/job/<id>/stop`.
  - Template filters: `pct`, `num`, `pts` (true minus sign; "no change"), `when`, `nicedate`, `month`.
  - A `before_request` check rejects cross-origin POSTs.
- **`static/app.js`**:
  - Task banner: renders the job, polls while running, reloads when a job this tab started finishes (`sessionStorage` key `cprt-watching`); dismissal is stored in `localStorage` under `cprt-dismissed`.
  - Buttons with `data-job` / `data-platform` start jobs; `data-confirm` asks first.
  - Sortable tables (`table.sortable`, optional `data-sort` on cells), live filters (`input[data-filter="#id"]`) and `select[data-autosubmit]`.
- **Launchers:**
  - `setup.command` (bash): finds Python 3.9+, creates `.venv`, clears the quarantine flag on the folder, installs requirements and Chromium, runs the self-test, then opens the console.
  - `Open CPRT Console.command`: activates `.venv` and runs `app.py`. If the port is already in use it just opens the browser.

## 5. Data model (SQLite `data/console.db`)

| Table | Key | Columns | Notes |
|---|---|---|---|
| `sources` | `id` (url unique) | platform, url, label, enabled, origin (recorded/added), added, last_run, last_status, last_lots | Pages replayed by automatic capture |
| `observations` | (obs_date, platform, lot_id) | state, yard, seller_raw, make, model, year, damage, sale_date, source_url, origin (recorded/auto/manual) | One row per lot per day seen. The carrier is **not stored**; it's re-mapped on load so pattern and override fixes apply to history |
| `runs` | `id` | kind (news/macro/sec/capture/weekly), started, finished, status (ok/failed/skipped/partial), message | Data freshness |
| `news` | `key` (normalized title) | title, source, published, link, summary, score, matched, queries, first_seen, starred, read | |
| `macro` | (series_id, date) | value | Raw FRED values; derived series computed on read |
| `pgr_monthly` | `url` | filing_date, period, combined_ratio, combined_ratio_prior, direct_auto_pif, direct_auto_growth, agency_auto_pif, agency_auto_growth | Parsed best-effort |
| `release_snippets` | (url, keyword, snippet) | ticker, filing_date, numbers | |
| `fulltext_hits` | (query, url) | company, form, filing_date, first_seen | |
| `doj` | `url` | filing_date, form, found, disclosure, similarity, changed | |
| `snapshots` | `week` (Monday ISO date) | created, metrics (JSON) | Saved by weekly runs and reports |
| `inventory` | (obs_date, platform, view, dimension, key) | count, source_url, captured | Copart scan counts. `view` is `listed` or `new_7d`; `dimension` is `total`, `yard`, `newly_added`, `title` or `vehicle_type`. States are computed on read from yard names; a same-day re-scan replaces that day's counts |

**Other files under `data/`:**
- `settings.json`
- `raw/*.json.gz`: every captured JSON payload, gzipped. This is the audit trail and the first place to look when debugging extraction.
- `jobs/<id>.json`, `.log`, `.stop`
- `reports/CPRT_weekly_<week>.html`
- `logs/scheduled.log`

## 6. Settings reference (`cprt/settings.py` DEFAULTS)

- **Your details:** `user_name`, `user_email`. Required for SEC; `is_configured()` checks them.
- **Schedule:** `schedule_weekday` (0 = Sunday … 6 = Saturday; default 1, Monday), `schedule_hour` (8), `schedule_minute` (0), `capture_in_weekly` (True), `scan_daily` (True: launchd runs daily, and `weekly.run_scheduled` does the full update only on the chosen weekday).
- **Collection:**
  - `start_urls`: Copart and IAA home pages, used when recording starts.
  - `show_browser`: True, a visible window during automatic capture.
  - Pacing: `page_wait_seconds` 10, `scrolls_per_page` 4, `pause_between_pages` [15, 30], `max_pages_per_run` 30.
  - `respect_robots_txt`: True. Applies to automatic capture; recorded sessions are human browsing.
  - `guided_max_minutes` 30, `learn_sources_min_lots` 10.
  - `field_overrides` ({field: json_key}) and `carrier_overrides` ({NORMALIZED SELLER: group}).
- **Analysis:**
  - `tracked_carriers`: State Farm, Progressive, GEICO, Allstate, USAA.
  - `benchmarks` (Copart share claims): Progressive 0.05 and GEICO 0.95, both from the 9/3/26 ex-GEICO SVP call.
  - `min_sample` 10.
  - `market_benchmark`: [0.579, JPM autoAstat, Sep 11 2026].
- **News:** `news_queries` (13 searches), `news_lookback_days` 180, `alt_data_terms`, `extra_feeds` (Repairer Driven News RSS with keyword filter).
- **Macro:** `fred_series`, keyed by role:

  | Role | Series | Meaning |
  |---|---|---|
  | insurance_cpi | BLS:CUUR0000SETE | Motor vehicle insurance prices, from the BLS API (FRED dropped the series; `settings.MOVED_SERIES` migrates saved settings) |
  | repair_cpi | CUSR0000SETD | Maintenance and repair prices |
  | parts_cpi | CUSR0000SETC | Parts and equipment prices |
  | used_car_cpi | CUSR0000SETA02 | Used car and truck prices |
  | vmt_12m | M12MTVUSM227NFWA | 12-month total vehicle miles traveled, in millions |

- **SEC:**
  - `sec_release_targets`: PGR (14 filings; keywords policies in force, combined ratio, net premiums written), RBA (6; automotive, unit volume, lots sold, take rate, gross transaction value) and CPRT (6; insurance, units, assignments, average selling price).
  - `sec_fulltext_queries`: four phrases. `sec_fulltext_forms` "10-K,10-Q,8-K"; `sec_fulltext_start` "2025-01-01".
  - DOJ tracker: `doj_ticker` CPRT, `doj_filings` 8, `doj_keyword` "money laundering".

## 7. UI and design system

**Palette:**

| Token | Hex | Use |
|---|---|---|
| Concrete | `#F2F3F0` | Page background |
| Paper | `#FFFFFF` | Panels |
| Asphalt | `#1E2227` | Text, primary buttons, sidebar |
| Muted | `#5F646C` | Secondary text |
| Rule | `#D9DCD6` | Borders |
| Copart blue | `#2350C9` | **Copart only** |
| IAA red | `#C4412F` | **IAA only** |
| Hazard amber | `#D99A0B` | **Needs attention only** |
| Good | `#3F7A55` | "Supports the long" notes, OK badges |

Chart lines for insurers and macro series use the neutral `SERIES` palette in `charts.py`, never blue or red.

**Type:** Barlow for everything (it was modeled on California highway signs, which suits vehicle salvage), plus Barlow Semi Condensed for big numbers. Loaded from Google Fonts, with a Helvetica Neue fallback. Numbers use tabular figures.

**Signature element: the split bar.** A red track (IAA) with a blue fill (Copart share), a white 95% CI whisker, an amber diamond for an expert claim, and a dashed line for the JPM reference. The hero uses the large variant. The CSS components are `.split`, `.split-track`, `.split-copart`, `.split-ci`, `.split-claim` and `.split-ref`; the Jinja macro is `splitbar()` in `templates/_macros.html`.

**Copy rules:**
- Sentence case; no all-caps labels; plain verbs.
- A button says exactly what happens.
- Errors explain what happened and how to fix it.
- Empty states invite the next action.
- Use a true minus sign (−) in deltas.

**Layout:** a dark left rail (full height through a gradient on `.shell`) and left-aligned content up to 1180 px. One primary action per page, at the top right. Below 960 px the layout collapses to a top bar.

**Accessibility:** visible `:focus-visible` outline in amber; `prefers-reduced-motion` respected; `role="img"` and `aria-label` on split bars.

**Known CSS trap:** `.btn { display: inline-flex }` overrides the `hidden` attribute. A global `[hidden] { display: none !important; }` fixes this; keep it.

## 8. Collection details, per source

| Source | Endpoint | Politeness | Notes |
|---|---|---|---|
| Google News | `https://news.google.com/rss/search?q=<query>&hl=en-US&gl=US&ceid=US:en` | 3 s per host | Headlines and links only (copyright). Dates filtered locally |
| Trade feed | `https://www.repairerdrivennews.com/feed/` | 3 s | Keyword-filtered |
| FRED | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>` | 1 s | No key. Header may be `observation_date` or `DATE`; "." means missing |
| SEC tickers | `https://www.sec.gov/files/company_tickers.json` | 0.25 s | User-Agent required |
| SEC submissions | `https://data.sec.gov/submissions/CIK##########.json` | 0.25 s | `filings.recent` arrays |
| SEC filing index | `https://www.sec.gov/Archives/edgar/data/<cik>/<acc>/index.json` | 0.25 s | Exhibit-99 files found by filename regex |
| SEC full-text | `https://efts.sec.gov/LATEST/search-index?q=&dateRange=custom&startdt=&enddt=&forms=` | 0.25 s | **Response shape assumed** (`hits.hits[]._source`); verify live |
| Copart / IAA | Recorded session (human), or automatic replay of saved pages (Playwright Chromium) | 15–30 s between pages, at most 30 pages, images blocked | Logged out only; robots.txt checked for automatic replay; stops on bot checks |

## 9. Research findings about Copart and IAA (September 2026, from public web sources)

### Verified on the live sites (Sep 27, 2026, from the owner's Mac)

- **Copart sellers are hidden.**
  - In search results, `scn` (seller name) appears when `showSeller` is true: 7 of 180 lots.
  - `slrsr` holds only a seller type ("Dealer", "Rental", "Bank").
  - Lots carry badge codes in `lic[]`. Copart's code table `/public/data/referenceDataByObject/highlightIcons` (type "S" = seller) maps 66 of 180 lots to a "State Farm Insurance" badge, and a few to Bristol West, Bank Repo and Fleet Lease. Insurers without a badge program, such as GEICO, never show one.
- **Copart search results carry site-wide counts.** `/public/lots/search-results`, which `/lotSearchResults?...` calls, returns `totalElements` plus facets, and echoes the query it answered:
  - `Location`: about 380 locations, including Canadian yards and offsite lots. The facet ignores its own filter.
  - `Newly Added Lots` (code `NLTS`): `expected_sale_assigned_ts_utc:[NOW/DAY-1DAY TO NOW/DAY]` and the same with `-7DAY`.
  - `Title Type`, `Vehicle Type` and others.
  - Sep 27 figures: 428,262 lots in total; 420,910 at 356 US locations; 53,191 added in the last 7 days across all yards.
- **Copart robots.txt** can only be read through a browser; plain requests get an Imperva 403 page. It allows `/lotSearchResults?…` and `/public/lots/…`. It disallows `/public/data/`, `/lotSearchResults/` (with a trailing slash) and account pages.
- **Copart bot protection (Imperva).**
  - An unattended Playwright browser loaded the search page once; about 50 minutes later the scan was blocked.
  - Block pages hide their message inside an iframe (`_Incapsula_Resource?CWUDNSAI=…`, "Incapsula incident ID").
  - Normal pages also load an `_Incapsula_Resource?SWJIYLWA=` script, so that script alone isn't a sign of a block.
- **Copart's yard directory** (`/public/data/locations/…`) looks like lots to field inference: ID-like zip codes and "ST - CITY" names. It was saved as 180 fake lots until `lot_lists` started requiring a make or model.
- **IAA.**
  - Search results and vehicle pages are server-rendered HTML, so a session that visited `/Search` twice captured no lots.
  - IAA's robots.txt disallows `/Search`, `/Login/` and `/MyAuctionCenter/`.
  - Its homepage shows no inventory totals, and `/LiveAuctionsCalendar` returned an Imperva block page to an unattended browser.
- **FRED dropped the motor vehicle insurance CPI**: CUSR0000SETE and CUUR0000SETE both return 404. The BLS API still has it; version 1 needs no key and returns 3 years by GET or 10 years by POST.
- **Progressive releases.** Policies-in-force rows read "Direct – auto 16,879 15,524 9": whole thousands, no % sign, and declines in parentheses. Direct-auto growth slowed from 16% (Oct 2025) to 9% (Aug 2026).
- **Copart's DOJ paragraph.**
  - It sits in the notes of every 10-Q and 10-K. It runs from "The U.S. Department of Justice … is conducting …" to "… range of possible loss.", and the next "NOTE n —" heading follows.
  - 10-K risk factors mention the investigation earlier.
  - Real wording changes so far: "timing" became "duration" (10-Q, Nov 2025), and "Consumer Protection Branch" was dropped (10-Q, Mar 2026).

The research notes below were written before these checks.

Things **I could not verify on the live sites** from the build sandbox:

1. **Search URLs are standard, so the console can build them itself.**
   - Copart: `https://www.copart.com/lotSearchResults/?free=true&query=<keyword>`. Filters chosen in the site's UI (year, damage, location) are carried in the URL through a `searchCriteria` parameter. Lot pages are `https://www.copart.com/lot/<number>`.
   - IAA: `https://www.iaai.com/Search?keyword=<keyword>`. Filtered searches carry `url=` tokens. Vehicle pages are `https://www.iaai.com/VehicleDetail/<id>~US`.
   - IAA has no public read API for auction search.
2. **Bot protection.** Commercial scrapers document Imperva challenges on Copart and rate limits, and they use US residential proxies. IAA challenges datacenter IP addresses. Using proxies to avoid detection is **out of bounds for this project** (hard rule 1). A slow, visible, logged-out browser may or may not be accepted; the console must detect a block, stop and tell the owner.
3. **Seller names are probably hidden from logged-out visitors.**
   - An IAA scraper's documentation says seller names (and full VINs) are often masked for anonymous visitors.
   - A Copart buyer on a car forum couldn't find the seller on a lot page.
   - Third-party tools, including a Chrome extension, exist specifically to show who is selling cars on copart.com and iaai.com.

   **This is the biggest open risk.** Without seller names, the insurer split can't be computed from public pages, whether recorded or automatic. It is **not yet verified.**
4. The paid Apify scrapers and data providers such as autoAstat and Yipit are what the sell-side uses. They are not options for this project (cost, and evasion concerns), but the numbers they produce can be **cited** from broker notes (the JPM 57.9/42.1 figure).

## 10. Decision tree and backlog

### Status (Sep 27, 2026)

- **Steps 0 and 1 are done**; §9 has the results. The live runs found nine bugs, all fixed with tests:
  - the recorder crashed on "INFINITY";
  - yard lists were saved as lots;
  - freshness wasn't recorded for single updates;
  - the FRED insurance series was dead;
  - Progressive policies-in-force parsing and the December period year were wrong;
  - the DOJ tracker raised false alarms;
  - block pages hidden in a frame weren't detected;
  - robots.txt block pages were read as permission;
  - raw files were overwritten on the same day.
- **The decision was B.** Sellers are hidden, so the insurer split is hidden, with an explanation from `tracker.split_problem`.
- **The daily Copart scan replaced P1-a and delivers P1-b's counts.** Copart's own facet counts cover every yard in 2 page loads a day, which beats replaying saved pages.
  - Built: `market.py`, `capture.run_scan`, `cli.py scan|scheduled`, a daily launchd schedule, the Copart inventory page, sections on the home page and in the report, Excel sheets and PNG charts.
  - Fallback: "Scan with me", a guided session that saves the same counts.
- **Open:**
  - Does the unattended scan get past Imperva on most days? Watch the first week.
  - IAA volumes: an RB Global filings parser (P2) or a weekly manual browse. The owner hasn't decided.
  - State Farm badge tracker: first check that the badge really marks State Farm lots, then add a search filter or a lot sample.

### Step 0 (P0): live smoke test on the owner's Mac

Run `bash setup.command`, then the self-test, then **Run first update** in the UI.
- Check that news, macro and SEC all show OK under Data freshness, and fix any live-format mismatches.
- Verify Progressive parsing against two or three real monthly releases: open the filing links on Filings and compare.
- Check that the DOJ tracker finds the paragraph in the latest 10-K/10-Q.
- **Acceptance:** real charts render; the Progressive table has 6+ months with non-null growth and combined ratio that match the filings; the DOJ row says "found".

### Step 1 (P0): the seller-name check

Have the owner record one short session per site: one state, two results pages, and a few individual lots. Then check:
- The banner's "M with seller names" count.
- Data quality → "Seller names found".
- The raw JSON in `data/raw/` (search for seller-like keys and values).

**Decision:**
- **A: sellers visible** (logged out, on either or both sites). Keep the insurer split, then do P1-a.
- **B: sellers hidden on a site.** For that site, do P1-b. The insurer split then relies on cited third-party figures plus an optional small hand sample, which the team must decide on themselves. The UI should say this clearly, not show empty charts.

### P1-a: automatic setup (removes the recording step)

- Add `capture.auto_setup(settings)`. It builds start URLs from new setting templates (for example `search_templates: {"copart": ".../lotSearchResults/?free=true&query={q}", "iaa": ".../Search?keyword={q}"}`), captures N pages per platform with pagination, and learns sources.
- **Pagination:** prefer a URL page parameter if one exists; otherwise click a "Next" control found heuristically (`a[rel=next]`, `[aria-label*=Next i]`, `button:has-text("Next")`). Cap pages, and stop when no new lots appear.
- **State targeting:** use the site's own location filter URLs if their format can be derived from one observed filtered URL. Otherwise sample broadly (all lots) and rely on per-lot state parsing plus state pairing in the analysis.
- **UI:** the primary button on Collect data and the home empty state becomes "Set up automatically". Recording becomes a fallback ("Use this only if automatic setup is blocked"). The weekly run calls auto-setup for any platform with no sources.
- **Acceptance:** a fresh install plus one click gives sources and lots for both platforms, or a precise message naming which platform blocked and the one-step fallback. All hard rules hold.

### P1-b: inventory and flow tracker (for sites without seller names)

- **New metrics** per platform × state × week: the site-reported total listing count (`find_total`), captured lots, **new lots** (first seen that week), and disappeared lots (a sold or removed estimate).
- **Headline:** Copart's share of combined listed inventory by state and overall, week over week. **New-lot growth** per platform is the proxy for assignment volume: "Copart new listings −x% vs IAA +y%".
- Add notes, report sections, charts and Excel sheets for these. Label everything clearly as listed inventory, not contracts.
- Keep the insurer-split views but hide them, with an explanation, when seller coverage is below 50%.
- **Acceptance:** after two weekly captures, This week shows the platform split and the new-lot trend with sample sizes and caveats.

### P2 and P3

- **P2: capture quality.** Bigger page sizes where the site offers them. A source health check that auto-disables a page after three failures and raises a note. Better block detection: HTTP status plus title and text markers.
- **P2: parsers.** RB Global quarterly automotive table (units, gross transaction value, take rate) and Copart quarterly units into tables. Tests built on short real excerpts.
- **P3: more data.** Berkshire (GEICO) quarterly policies in force; job postings for Copart, ACV and RB Global (hiring push); Census used-vehicle exports to the Middle East; Google Trends.
- **P3: packaging.** An optional `.app` wrapper and an in-app update check.

## 11. Verification status

**Verified in the build sandbox (Linux, Python 3.12, pandas 3.0.2, no internet):**
- 28 automated tests pass.
- A real Chromium browser recorded a session on a fake local auction site (TX then FL pages, 28 lots), learned two sources, and replayed them.
- Every page and form works through the Flask test client.
- Background jobs run as subprocesses.
- The report and Excel export build.
- UI screenshots were reviewed and the problems fixed: palette misuse, legend overlap, `[hidden]`, minus signs and sidebar height.

**Verified live on the owner's Mac (Sep 27, 2026):**
- Setup and the self-test.
- News: 146 articles.
- FRED for four series, and BLS for insurance prices.
- SEC: company releases (11 Progressive months with policies in force and combined ratio), full-text search (27 hits, so the response shape assumed in §8 is right) and the DOJ tracker.
- Copart: robots.txt, the search-result counts and one unattended search.
- IAA: robots.txt, and the fact that it blocks automated browsers.
- Still not verified: the launchd schedule, which isn't installed yet, and how often Imperva blocks the daily scan.

**Not verified in the build sandbox (see the list above for what has since been checked live):**
- The live Copart and IAA sites (URL behavior, JSON shape, seller visibility, bot checks).
- Live FRED, SEC and Google News responses; the parsers match documented formats.
- The EDGAR full-text response shape.
- Progressive table regexes on real releases.
- On macOS: launchd install and runs, notifications, `.command` double-clicks and the Gatekeeper prompts.
- Barlow rendering (it wasn't loaded in the sandbox).

## 12. Testing

- `tests/helpers.py` provides:
  - `FakeResp`, a stand-in for `requests.Response`.
  - `TempData`, a mixin that gives each test a private `paths.DATA` folder.
  - Synthetic lot factories `lots()` and `split()`, and payloads `copart_like_payload()` and `iaa_like_payload()` with deliberately cryptic keys.
- `test_backend.py` (40 tests):
  - Settings, including the series migration and odd saved shapes.
  - Inference, including "INFINITY".
  - Capture storage and learning: yard lists and dated pages aren't lots, raw files are never overwritten, and recordings survive bad data and crashes.
  - Block pages hidden in a frame, robots.txt read through the browser, and `run_auto`'s handling of blocks, empty pages and browser failures.
  - The paste parser.
  - Tracker metrics, pairing, confidence intervals, history, flow, overrides and data from one site only.
  - The two-proportion test and the notes.
  - News, macro with BLS, and SEC (the real Progressive layout, the December period year, DOJ passages and like-for-like comparison).
  - The CLI's freshness logging, a weekly run with report and Excel, a failed analysis step, the scheduler plist and the job lifecycle.
- `test_market.py` (11 tests): scan parsing, storage and analysis; week-over-week notes; the echoed-query check; Scan with me; `run_scan`'s block, crash, changed-site and robots handling; the daily and weekly schedule.
- `test_browser.py` (3 tests; skipped when Chromium is missing): `capture_page`, robots.txt through the browser, and a recorded session followed by weekly replay against a local `ThreadingHTTPServer` fake site.
- `test_app.py` (7 tests):
  - Every page renders, both empty and seeded.
  - Forms, and downloads (including a path-traversal check).
  - The Copart inventory page and its scan tasks.
  - The How to use page's live setup checklist and example numbers.
  - The jobs API and origin check, and the schedule buttons.
- **Adding a test:** subclass `(TempData, unittest.TestCase)`, patch `cprt.net.http_get` with a function returning `FakeResp`, and never touch the network.

## 13. Gotchas and lessons learned

- **Playwright sync API:** queue responses in the handler and read bodies in the main loop. Closing the last window on macOS doesn't quit Chromium, so the loop ends when no pages are open.
- **The scheduler stores `sys.executable`** at install time. If `.venv` moves or is rebuilt, turn the schedule off and on again.
- **macOS privacy (TCC)** blocks launchd jobs from reading `~/Downloads`, `~/Desktop` and `~/Documents`. The project must live directly in the home folder; the UI warns and disables the button otherwise.
- **Flask** runs with `use_reloader=False` because the job registry (`jobs._procs`) lives in-process.
- **SVG charts** scale with their container, so keep one figure width (9.6 in) for full-width charts. Put legends below the plot. Use `PercentFormatter(decimals=None)`.
- **Settings** drop unknown keys on save.
- **Observations don't store the insurer group**, so mapping fixes apply retroactively.
- **"What changed"** compares against the previous week that has listing data, not the previous saved snapshot. Otherwise moves are missed when only captures ran.
- **In the build sandbox,** `pkill -f` patterns matched the calling shell, and background servers died between tool calls. This isn't relevant on the Mac.
- **Saved settings override DEFAULTS key by key.** Changing a default (a series id, say) does nothing for an existing install unless `settings.load()` migrates it; see `MOVED_SERIES`. Migrations must tolerate odd shapes, because `load()` runs before every page.
- **Python's `urllib.robotparser` ignores `$` and `*`.** With Copart's rules it still gives the right answers for the scan's URLs; a test covers this.
- **`difflib.SequenceMatcher` on long strings** at character level, with autojunk on, gives meaningless ratios. Compare word lists with `autojunk=False`.
- **EDGAR page breaks** leave "81 Table of Contents" in the middle of sentences in `html_to_text` output.
- **Plain requests to copart.com always get Imperva's 403**, and each one is a bot signal against the visitor. Read anything on Copart through the capture browser.
- **Weekday numbering differs.** Settings count from Sunday = 0; Python's `weekday()` counts from Monday = 0. Sep 27, 2026 is a Sunday.

## 14. Decision log

- **Flask rather than Streamlit.** Streamlit and Plotly weren't installable in the build sandbox. Flask let the whole UI be tested, including real-browser screenshots.
- **Server-side matplotlib charts.** They work offline with consistent styling: SVG in the UI and PNG for slides and reports.
- **SQLite.** Weekly history, de-duplication and "new since" queries in one file, in WAL mode.
- **Values-based field inference.** The sites' JSON keys are undocumented and cryptic.
- **Recorded sessions.** URL formats were unknown at build time, and a human gets past legitimate checks. The URL formats are now known (§9), so automatic setup is feasible (P1-a).
- **Logged-out only; no evasion.** Terms of service and ethics, plus judge-facing credibility: the team must be able to explain its method.
- **Copart scan over saved-page replay** (Sep 27, 2026). Copart's search responses carry counts for every yard, so 2 page loads a day give complete inventory and new-lot flow. The saved-page replay is still available.
- **Daily scan, weekly everything else** (the owner's choice). One launchd job runs every day, and `weekly.run_scheduled` does the full update on the chosen weekday.
- **robots.txt checks off for the owner's install** (the owner's decision, Sep 27). The default stays on. When it's on, robots.txt is read through the capture browser, never with a plain request.
- **No workaround for blocks, even on request.** The owner asked for "whatever it takes". The line held anyway: no CAPTCHA solving, proxies, stealth, spoofing, logged-in scraping or retries. The scan stops for the day, and "Scan with me" fills gaps with a person browsing.
- **IAA isn't automated.** Its robots.txt disallows `/Search`, its results are HTML, and it blocked an unattended browser.

## 15. Glossary

- **Assignment:** an insurer sending a totaled car to an auction platform.
- **Lot or stock number:** the platform's ID for a vehicle.
- **TLF:** total-loss frequency, the share of claims where the car is totaled.
- **PIF:** policies in force.
- **CR:** combined ratio. Under 100 means an underwriting profit.
- **Split:** Copart share = Copart lots ÷ (Copart + IAA lots) for an insurer, in paired states only.
- **Paired states:** states sampled on both platforms that week.
- **RPU / take rate:** revenue per unit, or fees as a share of vehicle price.
- **ACV:** two meanings. *Actual cash value* (a car's pre-accident value), or **ACV Auctions (ACVA)**, which Copart is acquiring.
- **IAA / IAAI:** Insurance Auto Auctions, owned by RB Global (RBA).
- **autoAstat / Yipit:** third-party data providers cited by the sell-side.
- **Imperva:** the bot-protection service used by Copart.
