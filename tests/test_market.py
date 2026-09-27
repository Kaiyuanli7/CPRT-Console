"""Copart daily scan: parsing, storage, analysis, the scan command and the schedule. Synthetic data, no internet."""
from __future__ import annotations

import gzip
import json
import unittest
from datetime import date
from unittest import mock
from urllib.parse import unquote

from helpers import TempData
from cprt import capture, db, market, net, paths, scheduler, settings, weekly

BLOCK_PAGE = ('<html><body><iframe id="main-iframe" src="/_Incapsula_Resource?CWUDNSAI=23">Request unsuccessful. '
              'Incapsula incident ID: 1-2</iframe></body></html>')


def search_payload(yards: dict, new_24h: int = 600, new_7d: int = 53000, filters: dict | None = None,
                   terms=("*",), base: int = 70000000, page_url: str = market.SEARCH) -> dict:
    """Shaped like Copart's /public/lots/search-results response (checked Sep 2026), with made-up numbers.

    Copart echoes the query it answered; `filters` and `terms` set that echo.
    """
    counts = [{"displayName": name, "count": n, "query": f'yard_name:"{name.upper()}"'} for name, n in yards.items()]
    lots = [{"lotNumberStr": str(base + i), "mkn": "TOYOTA", "lm": "CAMRY", "lcy": 2019, "yn": "TX - HOUSTON"}
            for i in range(12)]
    return {"url": "https://www.copart.com/public/lots/search-results", "page_url": page_url,
            "data": {"returnCode": 1, "data": {"query": {"query": list(terms), "filter": filters or {}, "page": 0},
                                               "results": {
                "totalElements": sum(yards.values()),
                "content": lots,
                "facetFields": [
                    {"displayName": "Newly Added Lots", "quickPickCode": "NLTS", "facetCounts": [
                        {"displayName": "Last 24 Hours", "count": new_24h}, {"displayName": "Last 7 Days", "count": new_7d}]},
                    {"displayName": "Title Type", "facetCounts": [{"displayName": "Salvage Title", "count": 100}]},
                    {"displayName": "Location", "quickPickCode": "LOC", "facetCounts": counts},
                    {"displayName": "Source", "facetCounts": []}]}}}}


def scan_day(obs_date: str, listed: dict, new: dict) -> None:
    market.store(obs_date, "listed", market.parse_search([search_payload(listed)]), market.SCAN_PAGES["listed"])
    market.store(obs_date, "new_7d", market.parse_search([search_payload(new)]), market.SCAN_PAGES["new_7d"])


class MarketTests(TempData, unittest.TestCase):
    def test_parse_store_and_summarise(self):
        listed = search_payload({"Tx - Houston": 5000, "Tx - Dallas": 3000, "Fl - Miami": 4000, "Ab - Calgary": 250})
        parsed = market.parse_search([{"url": "https://www.copart.com/public/data/x", "data": {}}, listed])
        self.assertEqual(parsed["total"], 12250)
        self.assertEqual(parsed["facets"]["yard"]["Fl - Miami"], 4000)
        self.assertEqual(parsed["facets"]["newly_added"]["Last 7 Days"], 53000)
        self.assertIsNone(market.parse_search([{"url": "https://www.copart.com/public/data/x", "data": {}}]))
        scan_day("2026-09-20", {"Tx - Houston": 5000, "Tx - Dallas": 3000, "Fl - Miami": 4000, "Ab - Calgary": 250},
                 {"Tx - Houston": 600, "Fl - Miami": 400, "Ab - Calgary": 20})
        summ = market.summary()
        self.assertEqual((summ["us_listed"], summ["us_new_7d"], summ["listed"], summ["us_yards"]), (12000, 1000, 12250, 3))
        states = {r["state"]: r for r in summ["states"]}
        self.assertEqual(set(states), {"TX", "FL"})  # Calgary is not a US yard
        self.assertEqual((states["TX"]["listed"], states["TX"]["new_7d"]), (8000, 600))
        self.assertAlmostEqual(states["FL"]["new_share"], 0.1)
        self.assertIsNone(summ["change"]["us_new_7d"])  # nothing a week earlier yet
        self.assertEqual(summ["new_24h"], 600)

    def test_week_over_week_notes(self):
        for d, new in (("2026-09-20", 1000), ("2026-09-26", 1100), ("2026-09-27", 900)):
            scan_day(d, {"Tx - Houston": 10000}, {"Tx - Houston": new})
        summ = market.summary()
        self.assertEqual((summ["date"], summ["prior_date"]), ("2026-09-27", "2026-09-20"))
        self.assertAlmostEqual(summ["change"]["us_new_7d"], -0.1)
        notes = market.notes(summ, today=date(2026, 9, 27))
        self.assertTrue(any(level == "alert" and "fell 10%" in text for level, text in notes), notes)
        self.assertEqual(len(market.history()), 3)
        stale = market.notes(summ, today=date(2026, 10, 2))
        self.assertTrue(any(level == "action" and "5 days ago" in text for level, text in stale))
        self.assertEqual(market.notes({"has_data": False})[0][0], "action")

    def test_same_day_rescan_replaces_counts(self):
        scan_day("2026-09-27", {"Tx - Houston": 100}, {"Tx - Houston": 10})
        scan_day("2026-09-27", {"Tx - Houston": 120}, {"Tx - Houston": 12})
        self.assertEqual(market.summary()["us_listed"], 120)

    def test_view_of_reads_the_echoed_query(self):
        yards = {"Tx - Houston": 1}
        self.assertEqual(market.view_of(search_payload(yards)), "listed")
        self.assertEqual(market.view_of(search_payload(yards, filters={"NLTS": [market.NEW_7D_FILTER]})), "new_7d")
        self.assertEqual(market.view_of(search_payload(yards, filters={"MAKE": ['lot_make_desc:"TOYOTA"']})), "other")
        self.assertEqual(market.view_of(search_payload(yards, terms=("toyota",))), "other")
        self.assertIsNone(market.view_of({"url": "x", "data": {"data": {}}}))  # no echo: can't tell
        narrow = search_payload(yards, filters={"MAKE": ['lot_make_desc:"TOYOTA"']})
        self.assertIsNone(market.parse_search([narrow], "listed"))  # a make search never passes as site-wide

    def test_scan_with_me_saves_site_wide_counts_only(self):
        listed = search_payload({"Tx - Houston": 5000, "Fl - Miami": 3000},
                                page_url=market.SEARCH + "?free=true&query=&qId=1")
        new = search_payload({"Tx - Houston": 500, "Fl - Miami": 250}, filters={"NLTS": [market.NEW_7D_FILTER]},
                             base=71000000, page_url=market.SCAN_PAGES["new_7d"])
        toyota = search_payload({"Tx - Houston": 99}, filters={"MAKE": ['lot_make_desc:"TOYOTA"']}, base=72000000,
                                page_url=market.SEARCH + "?make=toyota")

        def person(start_url, max_minutes, stop_file, on_payload, show_browser, script):
            for p in (listed, new, toyota):
                on_payload(p)

        with mock.patch.object(capture, "record_session", person):
            out = capture.run_guided(settings.load(), "copart", start_url=market.SCAN_PAGES["listed"],
                                     progress=lambda *a, **k: None)
        self.assertEqual(out["counts"], ["listed", "new_7d"])
        summ = market.summary()
        self.assertEqual((summ["us_listed"], summ["us_new_7d"]), (8000, 750))  # the Toyota search isn't site-wide
        self.assertEqual([r["url"] for r in db.query("SELECT url FROM sources")],
                         [market.SEARCH + "?make=toyota"])  # the daily scan covers the other two pages


class ScanTests(TempData, unittest.TestCase):
    def fake_site(self, blocked_on=None, changed=False):
        def capture_fn(url, show, wait, scrolls):
            view = "new_7d" if "NLTS" in unquote(url) else "listed"
            if view == blocked_on:
                return {"payloads": [], "title": "", "text": "", "html": BLOCK_PAGE}
            if changed:
                return {"payloads": [], "title": "Copart", "text": "A new design", "html": "<html></html>"}
            yards = {"Tx - Houston": 5000, "Fl - Miami": 4000} if view == "listed" else {"Tx - Houston": 500, "Fl - Miami": 300}
            echo = {"NLTS": [market.NEW_7D_FILTER]} if view == "new_7d" else {}
            return {"payloads": [search_payload(yards, filters=echo),
                                 {"url": "https://rs.fullstory.com/rec/bundle", "data": {"x": 1}}],
                    "title": "Search results", "text": "Results", "html": ""}
        return capture_fn

    def setUp(self):
        super().setUp()
        self.s = settings.update(pause_between_pages=[0, 0], respect_robots_txt=False)
        self.quiet = lambda *a, **k: None

    def test_scan_stores_counts_and_raw_files(self):
        out = capture.run_scan(self.s, progress=self.quiet, capture_fn=self.fake_site())
        self.assertEqual((out["listed"], out["new_7d"], out["pages"], out["blocked"]), (9000, 800, 2, False))
        self.assertEqual(market.summary()["us_new_7d"], 800)
        raws = sorted((paths.DATA / "raw").glob("*copart_scan*.json.gz"))
        self.assertEqual(len(raws), 2)
        with gzip.open(raws[0], "rt") as f:
            self.assertTrue(all("/public/lots/" in p["url"] for p in json.load(f)))  # third-party trackers not kept

    def test_scan_stops_at_a_bot_check(self):
        with self.assertRaises(RuntimeError) as err:
            capture.run_scan(self.s, progress=self.quiet, capture_fn=self.fake_site(blocked_on="listed"))
        self.assertIn("bot check", str(err.exception))
        self.assertFalse(market.summary()["has_data"])
        out = capture.run_scan(self.s, progress=self.quiet, capture_fn=self.fake_site(blocked_on="new_7d"))
        self.assertEqual((out["pages"], out["blocked"]), (1, True))  # the first page's counts are kept

    def test_scan_carries_on_when_a_page_crashes(self):
        site = self.fake_site()

        def flaky(url, *a):
            if "NLTS" not in unquote(url):
                raise RuntimeError("Target page, context or browser has been closed")
            return site(url, *a)

        said = []
        out = capture.run_scan(self.s, progress=lambda msg, **k: said.append(msg), capture_fn=flaky)
        self.assertEqual((out["pages"], out.get("new_7d")), (1, 800))  # the second page still ran
        self.assertTrue(any("browser has been closed" in m for m in said))
        with self.assertRaises(RuntimeError):
            capture.run_scan(self.s, progress=self.quiet,
                             capture_fn=lambda *a: (_ for _ in ()).throw(RuntimeError("no browser")))

    def test_scan_says_so_when_copart_changes_its_page(self):
        with self.assertRaises(RuntimeError) as err:
            capture.run_scan(self.s, progress=self.quiet, capture_fn=self.fake_site(changed=True))
        self.assertIn("may have changed", str(err.exception))

    def test_scan_follows_robots_txt_when_that_setting_is_on(self):
        s = settings.update(respect_robots_txt=True)
        calls = []
        with mock.patch.object(net, "robots_allows", return_value=False):
            with self.assertRaises(RuntimeError):
                capture.run_scan(s, progress=self.quiet, capture_fn=lambda *a: calls.append(a))
        with mock.patch.object(net, "robots_allows", side_effect=net.RobotsBlocked("bot check")):
            with self.assertRaises(RuntimeError):
                capture.run_scan(s, progress=self.quiet, capture_fn=lambda *a: calls.append(a))
        self.assertEqual(calls, [])


class ScheduleTests(TempData, unittest.TestCase):
    def test_scan_daily_and_everything_on_the_weekly_day(self):
        s = settings.load()  # Mondays 08:00, daily scan on
        with mock.patch.object(capture, "run_scan", return_value={"pages": 2, "blocked": False}) as scan, \
                mock.patch.object(weekly, "run", return_value={"alerts": 0, "actions": 0}) as full:
            self.assertEqual(weekly.run_scheduled(s, today=date(2026, 9, 29))["kind"], "scan")  # a Tuesday
            self.assertEqual(weekly.run_scheduled(s, today=date(2026, 9, 28))["kind"], "weekly")  # the Monday
            weekly.run_scheduled({**s, "scan_daily": False}, today=date(2026, 9, 29))
        self.assertEqual((scan.call_count, full.call_count), (1, 2))
        self.assertEqual(scheduler.build_plist(s)["StartCalendarInterval"], {"Hour": 8, "Minute": 0})
        self.assertEqual(scheduler.build_plist({**s, "scan_daily": False})["StartCalendarInterval"],
                         {"Weekday": 1, "Hour": 8, "Minute": 0})
        self.assertEqual(scheduler.build_plist(s)["ProgramArguments"][-1], "scheduled")
        self.assertEqual(settings.schedule_summary(s), "Copart scan daily at 08:00; full update Mondays")


if __name__ == "__main__":
    unittest.main(verbosity=2)
