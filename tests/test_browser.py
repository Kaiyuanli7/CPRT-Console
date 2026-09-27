"""Real-browser tests: Chromium against a tiny fake auction site on localhost (synthetic data)."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlparse

from helpers import TempData, copart_like_payload
from cprt import capture, db, settings

PAGE = """<html><head><title>Search results</title></head><body><h1>Results</h1><div id=out>loading</div>
<script>fetch('/api/lots?st=%s').then(r=>r.json()).then(d=>{document.getElementById('out').innerText=
d.data.results.content.length+' lots'})</script></body></html>"""
YARDS = {"TX": "TX - HOUSTON", "FL": "FL - MIAMI"}


class FakeSite(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        st = parse_qs(u.query).get("st", ["TX"])[0]
        if u.path == "/robots.txt":
            body, ctype = b"User-agent: *\nAllow: /\n", "text/plain"
        elif u.path == "/api/lots":
            base = 70000000 if st == "TX" else 71000000
            body, ctype = json.dumps(copart_like_payload(14, yard=YARDS[st], base=base)).encode(), "application/json"
        else:
            body, ctype = (PAGE % st).encode(), "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


@unittest.skipUnless(chromium_available(), "Chromium for Playwright is not installed")
class BrowserTests(TempData, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_capture_page(self):
        result = capture.capture_page(f"{self.base}/search?st=TX", show_browser=False, wait_seconds=1, scrolls=0)
        rows = capture.extract(result["payloads"], "copart")
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[0]["state"], "TX")
        self.assertIn("<html", result["html"])  # kept for spotting block pages hidden inside a frame

    def test_robots_read_through_the_browser(self):
        status, text = capture.fetch_text(f"{self.base}/robots.txt", show_browser=False, wait_seconds=0)
        self.assertEqual(status, 200)
        self.assertIn("User-agent: *", text)

    def test_recorded_session_then_weekly_replay(self):
        def person(page, drain):  # stands in for someone browsing: TX results, then FL, then closes
            page.wait_for_timeout(800)
            drain()
            page.goto(f"{self.base}/search?st=FL")
            page.wait_for_timeout(800)
            drain()
            page.close()

        s = settings.update(pause_between_pages=[0, 0], page_wait_seconds=1, scrolls_per_page=0)
        out = capture.run_guided(s, "copart", start_url=f"{self.base}/search?st=TX", progress=lambda *a, **k: None,
                                 script=person, show_browser=False)
        self.assertEqual((out["lots"], out["with_seller"], out["sources_learned"]), (28, 28, 2))
        labels = sorted(r["label"] for r in db.query("SELECT label FROM sources"))
        self.assertEqual(labels, ["FL", "TX"])

        with mock.patch("cprt.net.http_get") as get:  # robots.txt served by the fake site
            get.return_value = mock.Mock(status_code=200, text="User-agent: *\nAllow: /\n")
            res = capture.run_auto(s, progress=lambda *a, **k: None, show_browser=False)
        self.assertEqual((res["pages"], res["lots"], res["blocked"]), (2, 28, []))
        self.assertEqual({r["last_status"] for r in db.query("SELECT last_status FROM sources")}, {"ok"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
