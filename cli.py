"""Command line. The console runs these in the background; you rarely need them directly.

  python cli.py scheduled                       what the schedule runs: Copart scan daily, full update weekly
  python cli.py weekly                          full weekly update
  python cli.py scan                            Copart scan: inventory and new lots for every yard (2 pages)
  python cli.py update news|macro|sec           refresh one data source
  python cli.py capture auto                    revisit saved Copart/IAA pages
  python cli.py capture guided --platform copart|iaa [--url URL]
  python cli.py report                          rebuild this week's report
  python cli.py schedule on|off|status          weekly auto-update (macOS)
  python cli.py selftest                        offline tests
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime

from cprt import capture, jobs, macro, news, report, scheduler, sec, settings, weekly


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--job-id", help=argparse.SUPPRESS)
    ap = argparse.ArgumentParser(description="CPRT console commands", epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("weekly", parents=[common])
    w.add_argument("--scheduled", action="store_true")
    w.add_argument("--skip-capture", action="store_true")
    sub.add_parser("scheduled", parents=[common])
    sub.add_parser("scan", parents=[common])
    u = sub.add_parser("update", parents=[common])
    u.add_argument("what", choices=["news", "macro", "sec"])
    c = sub.add_parser("capture", parents=[common])
    c.add_argument("mode", choices=["auto", "guided"])
    c.add_argument("--platform", choices=["copart", "iaa"])
    c.add_argument("--url")
    sub.add_parser("report", parents=[common])
    sc = sub.add_parser("schedule", parents=[common])
    sc.add_argument("action", choices=["on", "off", "status"])
    sub.add_parser("selftest", parents=[common])
    args = ap.parse_args()

    if args.cmd == "selftest":
        import unittest
        from cprt import paths
        suite = unittest.defaultTestLoader.discover(str(paths.ROOT / "tests"))
        return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1

    job_id = args.job_id
    scheduled = args.cmd == "scheduled" or getattr(args, "scheduled", False)
    if scheduled and not job_id:
        kind = "scheduled" if args.cmd == "scheduled" else "weekly"
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + kind
        jobs.write_status(job_id, id=job_id, kind=kind, status="running", scheduled=True,
                          pid=__import__("os").getpid(), started=datetime.now().isoformat(timespec="seconds"))

    def progress(msg: str, **fields):
        print(msg, flush=True)
        if job_id:
            jobs.write_status(job_id, message=msg, **fields)

    s = settings.load()
    try:
        if args.cmd == "scheduled":
            result = weekly.run_scheduled(s, progress)
        elif args.cmd == "weekly":
            result = weekly.run(s, progress, include_capture=False if args.skip_capture else None)
        elif args.cmd == "scan":
            result = weekly.logged_step("scan", lambda: capture.run_scan(s, progress))
        elif args.cmd == "update":
            fn = {"news": news.run, "macro": macro.run, "sec": sec.run}[args.what]
            result = weekly.logged_step(args.what, lambda: fn(s, progress))
        elif args.cmd == "capture" and args.mode == "auto":
            result = weekly.logged_step("capture", lambda: capture.run_auto(s, progress))
        elif args.cmd == "capture":
            if not args.platform:
                raise SystemExit("Choose --platform copart or --platform iaa")
            result = capture.run_guided(s, args.platform, args.url, jobs.stop_file(job_id), progress)
        elif args.cmd == "report":
            snap, changes = weekly.current(s)
            snap["changes"] = changes
            weekly.save_snapshot(snap)
            result = {"report": report.build(s, snap).name}
            progress(f"Report saved: {result['report']}")
        else:  # schedule
            result = {"on": lambda: scheduler.install(s), "off": scheduler.uninstall,
                      "status": lambda: str(scheduler.status(s))}[args.action]()
            print(result)
        if job_id:
            jobs.write_status(job_id, status="done", result=result,
                              finished=datetime.now().isoformat(timespec="seconds"))
        if scheduled:
            notify_done(result if isinstance(result, dict) else {})
        return 0
    except (SystemExit, Exception) as exc:  # record the failure where the console can show it
        if not isinstance(exc, SystemExit):
            traceback.print_exc()
        msg = str(exc) or exc.__class__.__name__
        print(f"Failed: {msg}", flush=True)
        if job_id:
            jobs.write_status(job_id, status="failed", message=msg,
                              finished=datetime.now().isoformat(timespec="seconds"))
        if scheduled:
            scheduler.notify("CPRT console", f"Scheduled update failed: {msg[:120]}")
        return 1


def notify_done(r: dict) -> None:
    """Daily scans stay quiet unless Copart showed a bot check; weekly updates always report."""
    if r.get("kind") == "scan":
        if r.get("blocked"):
            scheduler.notify("CPRT console", "Copart showed a bot check during today's scan, so the scan stopped. "
                                             "It runs again at the next scheduled time.")
        return
    scheduler.notify("CPRT console", f"Weekly update done: {r.get('alerts', 0)} alerts, "
                                     f"{r.get('actions', 0)} to-dos. Open the console to review.")


if __name__ == "__main__":
    sys.exit(main())
