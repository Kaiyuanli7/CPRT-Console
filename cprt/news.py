"""Articles that cite salvage / insurance alternative data (Google News RSS + trade feeds).

Stores headline, source, date and link only; each article keeps the date it was first
seen so the console can show what's new this week.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from . import db, net

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
ATOM = "{http://www.w3.org/2005/Atom}"


def _strip(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_feed(xml_text: str, label: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        src = it.find("source")
        items.append({"query": label, "title": _strip(it.findtext("title", "")),
                      "source": (src.text or "").strip() if src is not None and src.text else "",
                      "published": _date(it.findtext("pubDate", "")),
                      "link": (it.findtext("link", "") or "").strip(),
                      "summary": _strip(it.findtext("description", ""))[:400]})
    for it in root.iter(f"{ATOM}entry"):
        link = it.find(f"{ATOM}link")
        items.append({"query": label, "title": _strip(it.findtext(f"{ATOM}title", "")), "source": label,
                      "published": _date(it.findtext(f"{ATOM}updated", "") or it.findtext(f"{ATOM}published", "")),
                      "link": link.get("href", "") if link is not None else "",
                      "summary": _strip(it.findtext(f"{ATOM}summary", ""))[:400]})
    return items


def key_for(title: str) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", title)  # drop Google's " - Publisher" suffix
    return re.sub(r"[^a-z0-9]", "", title.lower())[:180]


def run(settings: dict, progress=print) -> dict:
    items: list[dict] = []
    for q in settings["news_queries"]:
        try:
            items += parse_feed(net.http_get(GOOGLE_NEWS_RSS.format(q=quote_plus(q)), min_interval=3.0).text, q)
        except Exception as exc:
            progress(f"  news search failed ({q}): {exc}")
    for feed in settings.get("extra_feeds", []):
        try:
            kws = [k.lower() for k in feed.get("keywords", [])]
            for it in parse_feed(net.http_get(feed["url"], min_interval=3.0).text, feed["name"]):
                blob = f"{it['title']} {it['summary']}".lower()
                if not kws or any(k in blob for k in kws):
                    it["source"] = it["source"] or feed["name"]
                    items.append(it)
        except Exception as exc:
            progress(f"  feed failed ({feed.get('name')}): {exc}")
    if not items:
        raise RuntimeError("No articles retrieved - check the internet connection.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings["news_lookback_days"])
    terms = [t.lower() for t in settings["alt_data_terms"]]
    merged: dict[str, dict] = {}
    for it in items:
        if it["published"] and it["published"] < cutoff:
            continue
        k = key_for(it["title"])
        if not k:
            continue
        if k in merged:
            if it["query"] not in merged[k]["queries"]:
                merged[k]["queries"] += " | " + it["query"]
            continue
        text = f"{it['title']} {it['summary']}".lower()
        hits = [t for t in terms if t in text]
        merged[k] = {"key": k, "title": it["title"], "source": it["source"],
                     "published": it["published"].isoformat() if it["published"] else "",
                     "link": it["link"], "summary": it["summary"], "score": len(hits),
                     "matched": "; ".join(hits), "queries": it["query"], "first_seen": date.today().isoformat()}
    rows = list(merged.values())
    known = {r["key"] for r in db.query("SELECT key FROM news")}
    new = sum(1 for r in rows if r["key"] not in known)
    db.upsert("news", rows, ["key"], update=["score", "matched", "queries", "summary"])
    progress(f"News: {len(rows)} articles checked, {new} new.")
    return {"articles": len(rows), "new": new}
