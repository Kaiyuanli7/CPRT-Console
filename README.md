# CPRT console

A local app for the Copart pitch that collects the alternative data, tracks it week by week, and explains what changed. It runs on your Mac and opens in your browser. Nothing is sent anywhere except the requests it makes to collect data.

## Set up (once, about 5 minutes)

1. **Put the folder in your home folder.** Unzip, then drag `cprt-console` into your home folder (in Finder: Go > Home). Keep it out of Downloads, Desktop and Documents. macOS blocks background tasks from those folders, which would stop the weekly auto-update.
2. **Double-click `setup.command`.** It installs everything (including the browser used for recording), runs a self-test, and opens the console.
   - If Python is missing, the setup window tells you where to download it.
   - If macOS refuses to open the file, open Terminal and run `cd ~/cprt-console && bash setup.command` instead.
3. **In the console:**
   - Enter your name and email. The SEC requires them.
   - Click **Run first update**. It fetches news, macro data and SEC filings, and scans Copart.
   - In **Settings**, turn on **auto-update**. Copart is scanned every day and everything else once a week.

After that, double-click **`Open CPRT Console.command`** whenever you want to use the console. Keep its Terminal window open while you use it; close the window to stop the console.

## The Copart scan (automatic)

Copart's public search pages show counts for the whole site next to the lots they list. Every day the console opens two of those pages in a normal, logged-out browser and saves the counts: lots listed at every yard, and lots added in the last 7 days. That gives Copart's inventory and new-lot flow by state, with no browsing on your part.

If Copart shows the automated browser a bot check, the scan stops for the day and tells you; it never tries to get around it. To fill that day's gap, click **Scan with me** on Copart inventory. A Copart window opens; open **Newly added lots → Last 7 days**, then close the window.

Recording a browsing session (Insurer tracker → Collect data) still works, but it's optional. Copart and IAA hide sellers from logged-out visitors, so the insurer split is paused; see the Guide.

## What runs automatically

| When | What happens |
|---|---|
| Every day (your chosen time) | The Copart scan: two public pages, counts for every yard. You're notified only if Copart blocks it. |
| Every week (your chosen day) | News, macro data (FRED and BLS), SEC filings, the Copart scan and any saved pages are collected. The analysis runs, a report is saved, and you get a notification. If the Mac is asleep, it runs when the Mac wakes. |
| Every time you open a page | Insurer splits, confidence intervals, week-over-week significance tests, expert-claim checks and the notes on This week are recalculated. |
| On every capture | Duplicate lots are merged. Sellers are matched to parent insurers (e.g. National General counts as Allstate). Bot checks stop that site for the day. |

## The pages

| Page | Use it to |
|---|---|
| This week | See Copart's inventory, the week's notes, key signals and data freshness |
| Copart inventory | Lots listed and lots added in the last 7 days, by state and over time; Scan now or Scan with me |
| Insurer tracker | The Copart vs IAA split by insurer (paused while sellers are hidden); collect data; saved pages; seller matches; every lot |
| Macro | Total-loss pressure (repair vs used-car prices), insurance inflation, miles driven |
| Filings | Progressive's monthly policy growth and combined ratio; DOJ disclosure changes with highlighted wording; company release excerpts; SEC full-text hits |
| News | Articles ranked by alt-data language, with new, unread and starred views |
| Reports | Weekly printable reports; one-click Excel export of everything; PNG charts for slides |
| Settings | Your details, schedule, what to track and expert claims to test, collection pace, searches |
| How to use | The full manual: your setup status, every page and number explained, tracing numbers to sources, troubleshooting, glossary |
| Guide | Method, caveats for Q&A, ground rules |

## Your data

Everything lives in `cprt-console/data/`. Copy that folder to back it up.

| File or folder | Contents |
|---|---|
| `console.db` | All history (a single SQLite database) |
| `reports/` | Weekly reports |
| `raw/` | Raw captures (your audit trail for "how did you collect this?") |
| `jobs/` | Logs of every task |
| `settings.json` | Your settings |

## Ground rules

Copart's and IAA's terms of service likely restrict automated access, so read them and decide as a team. The console keeps volumes small and paces like a person. It stays logged out and respects robots.txt. When it meets a bot check it stops rather than working around it. Use the data for your research only.

Check your competition's rules on public information and AI use, and describe your collection method in the write-up. If required, disclose that this tooling was built with AI assistance.

## Troubleshooting

- **A task failed:** open Details on the banner at the top of the console to see the log.
- **The browser says it can't connect:** the console's Terminal window was closed. Double-click `Open CPRT Console.command` again.
- **The weekly auto-update never runs:** make sure the folder isn't inside Downloads, Desktop or Documents, then turn the schedule off and on again in Settings.
- **The Copart scan was blocked:** nothing to fix; it runs again at the next scheduled time. Use Scan with me on Copart inventory if you need that day's numbers.
- **Few seller names:** Copart and IAA hide most sellers from logged-out visitors, which is why the insurer split is paused. You can still add lots by hand on Collect data.
- **Start over:** Settings > Advanced > Delete listing data. News, macro data and filings are kept.

## For the technically curious

The console is a Flask app (`app.py`) backed by the `cprt/` package, and the background tasks run through `cli.py`. From the folder, with `source .venv/bin/activate`, you can run these directly:

```
python cli.py scan                # the Copart scan (2 public pages)
python cli.py weekly              # the full weekly update
python cli.py scheduled           # what the schedule runs: the scan daily, the full update on your day
python cli.py capture guided --platform copart
python cli.py capture auto
python cli.py update news|macro|sec
python cli.py schedule on|off|status
python cli.py selftest            # 58 offline tests, including real-browser tests on a fake local site
```
