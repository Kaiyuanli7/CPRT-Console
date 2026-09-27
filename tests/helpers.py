"""Shared test helpers. All data here is SYNTHETIC - made up to exercise the code."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from cprt import paths  # noqa: E402


class FakeResp:
    def __init__(self, text: str = "", status: int = 200, obj=None):
        self._obj = obj
        self.text = json.dumps(obj) if obj is not None else text
        self.status_code = status

    def json(self):
        return self._obj if self._obj is not None else json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class TempData:
    """Mixin: every test gets an empty, private data folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(paths, "DATA", Path(self._tmp.name) / "data")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()


def lots(platform: str, state: str, seller: str, n: int, start: int, obs_date: str, origin: str = "auto"):
    """n synthetic lot sightings for one platform/state/seller."""
    return [{"obs_date": obs_date, "platform": platform, "lot_id": f"{platform[0]}{start + i:07d}",
             "state": state, "yard": f"{state} - YARD", "seller_raw": seller, "make": "TOYOTA",
             "model": "CAMRY", "year": "2019", "damage": "FRONT END", "sale_date": "", "source_url": "",
             "origin": origin} for i in range(n)]


def split(obs_date: str, state: str, seller: str, copart: int, iaa: int, start: int):
    return lots("copart", state, seller, copart, start, obs_date) + lots("iaa", state, seller, iaa, start, obs_date)


def copart_like_payload(n: int, seller: str = "GEICO INSURANCE", yard: str = "TX - HOUSTON", base: int = 70000000):
    """A payload shaped like a salvage-auction search API, with deliberately cryptic keys."""
    content = [{"lotNumberStr": str(base + i), "yn": yard, "mkn": "TOYOTA", "lm": "CAMRY", "lcy": 2019,
                "dd": "FRONT END", "ad": 1790000000000, "scn": seller, "imgs": [{"u": "x"}]} for i in range(n)]
    return {"data": {"results": {"totalElements": 1500, "content": content,
                                 "facets": [{"name": "Make", "count": 4}]}}}


def iaa_like_payload(n: int, seller: str = "PROGRESSIVE CASUALTY", branch: str = "Houston (TX)", base: int = 40000000):
    return {"vehicles": [{"stockNumber": str(base + i), "branchName": branch, "seller": seller, "make": "HONDA",
                          "model": "CIVIC", "year": 2020, "primaryDamage": "REAR END",
                          "saleDate": "2026-10-02T10:00:00"} for i in range(n)], "totalCount": 2210}
