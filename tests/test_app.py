"""Web console tests: every page renders (empty and with data) and every form works. Synthetic data."""
from __future__ import annotations

import unittest
from unittest import mock

from helpers import TempData, split
import app as console
from cprt import db, jobs, market, paths, scheduler, settings, weekly

PAGES = ["/", "/inventory", "/tracker", "/tracker?tab=collect", "/tracker?tab=sources", "/tracker?tab=quality",
         "/tracker?tab=lots", "/macro", "/filings", "/news", "/reports", "/settings", "/help", "/guide"]


def seed_scans():
    """Two Copart scans a week apart (made-up counts; Calgary is outside the US)."""
    for d, (houston, miami) in (("2026-09-20", (500, 300)), ("2026-09-27", (450, 330))):
        market.store(d, "listed", {"total": 9250, "facets": {
            "yard": {"Tx - Houston": 5000, "Fl - Miami": 4000, "Ab - Calgary": 250},
            "newly_added": {"Last 24 Hours": 600, "Last 7 Days": 850}}}, market.SCAN_PAGES["listed"])
        market.store(d, "new_7d", {"total": houston + miami, "facets": {
            "yard": {"Tx - Houston": houston, "Fl - Miami": miami}}}, market.SCAN_PAGES["new_7d"])


def seed():
    rows = []
    for wk, base in (("2026-09-15", 0), ("2026-09-22", 100000)):
        for st in ("TX", "FL"):
            o = base + (0 if st == "TX" else 50000)
            rows += split(wk, st, "GEICO INSURANCE", 19, 1, o)
            rows += split(wk, st, "PROGRESSIVE CASUALTY", 1, 19, o + 1000)
            rows += split(wk, st, "STATE FARM MUTUAL", 12 if base == 0 else 9, 8 if base == 0 else 11, o + 2000)
        rows += split(wk, "CA", "STATE FARM MUTUAL", 10, 0, base + 90000)
        rows += split(wk, "TX", "ACME RECIPROCAL EXCH", 3, 3, base + 95000)
    db.save_observations(rows)
    db.upsert("sources", [{"platform": "copart", "url": "https://www.copart.com/s?st=TX", "label": "TX", "enabled": 1,
                           "last_status": "ok", "last_lots": 40, "last_run": db.now()}], ["url"])
    db.upsert("news", [{"key": "k1", "title": "Copart share data shows shift", "source": "Wire", "published": "2026-09-20",
                        "link": "https://e.com", "summary": "", "score": 3, "matched": "share; data", "queries": "q",
                        "first_seen": weekly.week_start()}], ["key"])
    db.upsert("pgr_monthly", [{"url": f"https://sec.gov/{m}", "filing_date": d, "period": p, "combined_ratio": cr,
                               "combined_ratio_prior": 83.1, "direct_auto_pif": 16880.1, "direct_auto_growth": g,
                               "agency_auto_pif": 11340.3, "agency_auto_growth": 7.0}
                              for m, d, p, cr, g in (("a", "2026-08-14", "July 2026", 88.0, 11.0),
                                                     ("b", "2026-09-16", "August 2026", 89.3, 9.0))], ["url"])
    db.upsert("doj", [{"url": "https://sec.gov/q1", "filing_date": "2026-05-29", "form": "10-Q", "found": 1,
                       "disclosure": "we cannot estimate a range of loss", "similarity": None, "changed": None},
                      {"url": "https://sec.gov/q2", "filing_date": "2026-09-25", "form": "10-Q", "found": 1,
                       "disclosure": "we recorded an accrual of $50 million", "similarity": 0.4, "changed": 1}], ["url"])
    db.log_run("news", "ok", "{}", db.now())
    seed_scans()


class AppTests(TempData, unittest.TestCase):
    def setUp(self):
        super().setUp()
        console.app.config.update(TESTING=True)
        self.client = console.app.test_client()

    def test_every_page_empty_and_full(self):
        for url in PAGES:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
        self.assertIn(b"Get set up", self.client.get("/").data)
        seed()
        settings.update(user_name="Test Student", user_email="t@school.edu")
        for url in PAGES + ["/tracker?week=2026-09-14"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
        home = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("Get set up", home)
        self.assertIn("split-big", home)
        self.assertIn("9,000", home)  # Copart lots in US yards (Calgary left out)
        self.assertIn("State Farm: Copart share fell", home)
        self.assertIn("wording changed", home.lower())
        results = self.client.get("/tracker").get_data(as_text=True)
        self.assertIn("Needs Copart", results.replace("Needs IAA", "Needs Copart"))  # CA flagged as one-sided
        self.assertIn("<svg", results)  # weekly trend chart rendered
        filings = self.client.get("/filings").get_data(as_text=True)
        self.assertIn("<del>", filings)
        self.assertIn("August 2026", filings)

    def test_forms(self):
        seed()
        r = self.client.post("/settings/profile", data={"user_name": "Jane", "user_email": "nope"}, follow_redirects=True)
        self.assertIn(b"valid email", r.data)
        self.client.post("/settings/profile", data={"user_name": "Jane Doe", "user_email": "jane@school.edu"})
        self.assertTrue(settings.is_configured(settings.load()))
        r = self.client.post("/tracker/manual", data={"platform": "iaa", "lot_id": "4012", "seller_raw": "USAA CASUALTY",
                                                     "yard": "Houston (TX)"}, follow_redirects=True)
        self.assertIn(b"counted as USAA", r.data)
        self.assertEqual(db.query("SELECT state FROM observations WHERE lot_id='4012'")[0]["state"], "TX")
        r = self.client.post("/tracker/paste", data={"text": "Lot # 70123456\nSeller: GEICO INSURANCE\n2019 TOYOTA CAMRY",
                                                    "platform": "copart"})
        self.assertIn("lot_id=70123456", r.headers["Location"])
        self.client.post("/tracker/mapping", data={"seller_raw": "acme reciprocal exch", "group": "Travelers"})
        self.assertEqual(settings.load()["carrier_overrides"], {"ACME RECIPROCAL EXCH": "Travelers"})
        sid = db.query("SELECT id FROM sources")[0]["id"]
        self.client.post(f"/tracker/sources/{sid}/toggle")
        self.assertEqual(db.query("SELECT enabled FROM sources")[0]["enabled"], 0)
        self.client.post("/tracker/sources/add", data={"url": "https://www.iaai.com/Search?st=FL", "label": "fl"})
        self.assertEqual(db.scalar("SELECT label FROM sources WHERE platform='iaa'"), "FL")
        self.client.post("/news/k1/star")
        self.assertEqual(db.scalar("SELECT starred FROM news"), 1)
        r = self.client.post("/settings", data={"section": "tracking", "tracked": ["GEICO", "State Farm"],
                                                "claim_GEICO": "90%", "source_GEICO": "call", "min_sample": "5"})
        s = settings.load()
        self.assertEqual((s["tracked_carriers"], s["benchmarks"]["GEICO"], s["min_sample"]), (["GEICO", "State Farm"], [0.9, "call"], 5))
        r = self.client.post("/settings", data={"section": "advanced", "field_overrides": "[1]"}, follow_redirects=True)
        self.assertIn(b"Not saved", r.data)
        self.client.post("/settings/reset-listings")
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM observations"), 0)

    def test_downloads(self):
        seed()
        self.assertEqual(self.client.get("/charts/split.png").mimetype, "image/png")
        self.assertEqual(self.client.get("/charts/progressive.png").mimetype, "image/png")
        self.assertEqual(self.client.get("/charts/pressure.png").status_code, 404)  # no macro data yet
        self.assertTrue(self.client.get("/tracker/lots.csv").data.startswith(b"obs_date,platform"))
        self.assertTrue(self.client.get("/export/excel").data[:2] == b"PK")
        self.assertEqual(self.client.get("/reports/../../etc/passwd").status_code, 404)

    def test_how_to_use_page_shows_live_setup_and_numbers(self):
        with mock.patch.object(scheduler, "plist_path", return_value=paths.DATA / "no-such.plist"):
            empty = self.client.get("/help").get_data(as_text=True)
            self.assertIn("Your setup", empty)
            self.assertIn("Not yet", empty)  # no name and email yet
            self.assertIn("Turn it on in Settings", empty)  # auto-update is off
            self.assertIn("href=\"/help\"", empty)  # in the sidebar
            seed()
            settings.update(user_name="Test Student", user_email="t@school.edu")
            full = self.client.get("/help").get_data(as_text=True)
        self.assertIn("Done", full)
        self.assertIn("Right now: 9,000", full)  # Copart lots in US yards from the seeded scans
        self.assertIn("+11% (July 2026) to +9% (August 2026)", full)  # Progressive direct-auto growth trend
        self.assertIn('id="troubleshooting"', full)
        self.assertIn("/help#troubleshooting", self.client.get("/guide").get_data(as_text=True))

    def test_inventory_page_and_scan_tasks(self):
        self.assertIn(b"No scan yet", self.client.get("/inventory").data)
        self.assertEqual(self.client.get("/charts/copart_new.png").status_code, 404)  # needs two scans
        seed_scans()
        page = self.client.get("/inventory").get_data(as_text=True)
        self.assertIn("By state", page)
        self.assertIn("−10.0%", page)  # Houston's new listings fell 500 -> 450, shown with a true minus sign
        self.assertEqual(self.client.get("/charts/copart_new.png").mimetype, "image/png")
        home = self.client.get("/").get_data(as_text=True)
        self.assertIn("Copart by state", home)  # no insurer split data, so the state table takes its place
        self.assertNotIn("split-big", home)
        with mock.patch.object(jobs, "start", return_value={"id": "x", "status": "running"}) as start:
            self.client.post("/api/jobs/scan", json={})
            start.assert_called_with("scan", ["scan"])
            self.client.post("/api/jobs/scan_guided", json={})
            self.assertEqual(start.call_args[0][1], ["capture", "guided", "--platform", "copart",
                                                     "--url", market.SCAN_PAGES["listed"]])

    def test_jobs_api_and_origin_check(self):
        with mock.patch.object(jobs, "start", return_value={"id": "x", "status": "running"}) as start:
            r = self.client.post("/api/jobs/weekly", json={})
            self.assertEqual(r.json["id"], "x")
            start.assert_called_with("weekly", ["weekly"])
            self.client.post("/api/jobs/capture_guided", json={"platform": "iaa"})
            start.assert_called_with("capture_guided", ["capture", "guided", "--platform", "iaa"])
        self.assertEqual(self.client.post("/api/jobs/capture_guided", json={"platform": "ebay"}).status_code, 400)
        self.assertEqual(self.client.post("/api/jobs/sec", json={}).status_code, 400)  # needs name + email
        self.assertEqual(self.client.post("/api/jobs/nope").status_code, 404)
        with mock.patch.object(jobs, "start", side_effect=RuntimeError("Another task is still running.")):
            self.assertEqual(self.client.post("/api/jobs/news").status_code, 409)
        evil = self.client.post("/tracker/sources/1/delete", headers={"Origin": "https://evil.example"})
        self.assertEqual(evil.status_code, 403)

    def test_schedule_buttons(self):
        with mock.patch.object(scheduler, "install", return_value="Weekly update scheduled for Mondays at 08:00."):
            r = self.client.post("/settings/schedule/on", follow_redirects=True)
        self.assertIn(b"Weekly update scheduled", r.data)
        with mock.patch.object(scheduler, "install", side_effect=RuntimeError("only on macOS")):
            r = self.client.post("/settings/schedule/on", follow_redirects=True)
        self.assertIn(b"only on macOS", r.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
