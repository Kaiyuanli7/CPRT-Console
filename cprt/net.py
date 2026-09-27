"""Polite HTTP: per-host throttling, retries, robots.txt checks (RFC 9309) and bot-check detection."""
from __future__ import annotations

import logging
import time
from urllib import robotparser
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("cprt")
# Phrases in the visible text of pages that sites show instead of content when they suspect a bot.
BLOCK_MARKERS = ["access denied", "incapsula", "request unsuccessful", "pardon our interruption",
                 "attention required", "are you a robot", "verify you are human", "captcha",
                 "unusual traffic", "bot detection", "request blocked"]
# Imperva's block page puts its message inside a frame, so the page's own text is empty. Normal pages load
# Imperva's script too (_Incapsula_Resource?SWJIYLWA=...), so only the challenge frame and incident ID count.
FRAME_MARKERS = ["_incapsula_resource?cwudnsai", "incapsula incident id"]
_session: requests.Session | None = None
_last_hit: dict[str, float] = {}
_robots: dict[str, robotparser.RobotFileParser] = {}
_robots_blocked: set[str] = set()


class RobotsBlocked(RuntimeError):
    """The site answered its robots.txt with a bot check, so its rules can't be read."""


def looks_like_bot_check(title: str = "", text: str = "", html: str = "") -> bool:
    blob = f"{title} {text[:1500]}".lower()
    return any(m in blob for m in BLOCK_MARKERS) or any(m in html[:20_000].lower() for m in FRAME_MARKERS)


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), respect_retry_after_header=True)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def _wait_turn(url: str, min_interval: float) -> None:
    host = urlparse(url).netloc
    wait = _last_hit.get(host, 0.0) + min_interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def http_get(url: str, params: dict | None = None, headers: dict | None = None,
             min_interval: float = 1.0, timeout: int = 30, raise_for_status: bool = True):
    """Throttled GET with retries. Tests replace this function with a fake."""
    _wait_turn(url, min_interval)
    resp = session().get(url, params=params, headers=headers or {}, timeout=timeout)
    if raise_for_status:
        resp.raise_for_status()
    return resp


def http_post(url: str, payload: dict, headers: dict | None = None, min_interval: float = 1.0, timeout: int = 30):
    """Throttled JSON POST (the BLS API needs one to return more than three years). Tests replace it too."""
    _wait_turn(url, min_interval)
    resp = session().post(url, json=payload, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp


def forget_robots() -> None:
    _robots.clear()
    _robots_blocked.clear()


def robots_allows(url: str, user_agent: str = "*", fetch=None) -> bool:
    """4xx robots.txt = allowed; 5xx or unreachable = disallowed.

    `fetch(robots_url)` -> (status, text) reads the file instead of a plain request. Browser captures pass their
    browser here: Copart's firewall refuses plain requests outright, and each refusal counts against the visitor.
    A bot check instead of the file raises RobotsBlocked, once per site; the caller stops that site. A block is
    never treated as permission.
    """
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base in _robots_blocked:
        raise RobotsBlocked(f"{p.netloc} showed a bot check instead of its robots.txt")
    rp = _robots.get(base)
    if rp is None:
        status, text = _read_robots(base, fetch)
        rp = robotparser.RobotFileParser()
        if status == 200:
            rp.parse(text.splitlines())
        elif 400 <= status < 500:
            rp.parse([])
        else:
            rp.parse(["User-agent: *", "Disallow: /"])
        _robots[base] = rp
    return rp.can_fetch(user_agent, url)


def _read_robots(base: str, fetch) -> tuple[int, str]:
    robots_url = base + "/robots.txt"
    try:
        if fetch is not None:
            status, text = fetch(robots_url)
        else:
            resp = http_get(robots_url, timeout=15, raise_for_status=False)
            status, text = resp.status_code, resp.text
    except requests.RequestException as exc:
        log.warning("Could not reach %s (%s); treating as disallowed", robots_url, exc)
        return 503, ""
    if looks_like_bot_check(text=text, html=text):
        _robots_blocked.add(base)
        raise RobotsBlocked(f"{urlparse(base).netloc} showed a bot check instead of its robots.txt")
    return status, text
