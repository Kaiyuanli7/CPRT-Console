"""SEC EDGAR (official free APIs; the SEC asks for <=10 requests/second and a real name + email).

* Progressive monthly releases -> policies in force + combined ratio, parsed into a table
* RB Global / Copart releases  -> keyword snippets with the numbers next to them
* Full-text search             -> every filing that mentions a phrase
* DOJ tracker                  -> Copart's anti-money-laundering paragraph, filing by filing,
                                  flagging real wording changes (dates/numbers ignored)
"""
from __future__ import annotations

import difflib
import html
import re
from datetime import date

from bs4 import BeautifulSoup

from . import db, net, settings as settings_mod

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"
EXHIBIT_99 = re.compile(r"(ex|exhibit)[-_]?99|dex99", re.I)
NUMBER = re.compile(r"\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$?\d+\.\d+%?|\d+%")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTH_NUMBER = {name.lower(): i for i, name in enumerate(MONTHS.split("|"), 1)}
# A policies-in-force row such as "Direct – auto 16,879 15,524 9": this year, last year, % change. The monthly
# releases give whole thousands without a % sign, and show a fall in parentheses: "(2)".
PIF_ROW = (r"{channel}\s*[-–—]?\s*auto[^0-9(]{{0,25}}([\d,]{{3,}}(?:\.\d+)?)\s+([\d,]{{3,}}(?:\.\d+)?)"
           r"\s+(?:\((\d+(?:\.\d+)?)\)|(-?\d+(?:\.\d+)?))")
DOJ_NAME = re.compile(r"department of justice|\(doj\)", re.I)
DOJ_SUBJECT = re.compile(r"(?:The\s+)?(?:U\.S\.\s+)?Department of Justice", re.I)  # opens the notes paragraph
NEXT_NOTE = re.compile(r"\bNOTE\s+\d+\s*[–—-]")  # "NOTE 16 — Guarantees", the next note heading
SENTENCE_END = re.compile(r"[a-z0-9)\]]\.\s")  # "loss. " ends a sentence; "U.S. " doesn't
PAGE_BREAK = re.compile(r"(?:\b\d{1,3}\s+)?Table of Contents\b\s*")  # "81 Table of Contents" mid-sentence
AS_OF_DATE = re.compile(rf"\b(?:{MONTHS})\s+\d{{1,2}},\s*\d{{4}}", re.I)  # "April 30, 2026"
_cik: dict[str, int] = {}


class SecConfigError(RuntimeError):
    pass


def _headers(s: dict) -> dict:
    ua = settings_mod.sec_user_agent(s)
    if not ua:
        raise SecConfigError("Add your name and email in Settings first - the SEC requires them.")
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def get(url: str, s: dict, params: dict | None = None):
    return net.http_get(url, params=params, headers=_headers(s), min_interval=0.25)


def cik_for(ticker: str, s: dict) -> int:
    if not _cik:
        for row in get(TICKERS_URL, s).json().values():
            _cik[row["ticker"].upper()] = int(row["cik_str"])
    if ticker.upper() not in _cik:
        raise RuntimeError(f"Ticker {ticker} not found on EDGAR")
    return _cik[ticker.upper()]


def filings(cik: int, s: dict, forms: set[str], limit: int) -> list[dict]:
    recent = get(SUBMISSIONS_URL.format(cik=cik), s).json()["filings"]["recent"]
    out = []
    for i, form in enumerate(recent["form"]):
        if form in forms:
            out.append({"form": form, "filing_date": recent["filingDate"][i],
                        "acc": recent["accessionNumber"][i].replace("-", ""),
                        "primary_doc": recent["primaryDocument"][i]})
            if len(out) >= limit:
                break
    return out


def html_to_text(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def snippets(text: str, keyword: str, width: int = 260, max_hits: int = 2) -> list[str]:
    found, last = [], -10**9
    for m in re.finditer(re.escape(keyword), text, re.I):
        if m.start() - last < width:
            continue
        found.append(text[max(0, m.start() - width // 2): m.end() + width])
        last = m.start()
        if len(found) >= max_hits:
            break
    return found


def _num(x: str | None) -> float | None:
    return float(x.replace(",", "")) if x else None


def _period_year(month: int, filing_date: str) -> int:
    """A release covers the month before it's filed, so a December release filed in January is last year's."""
    year, filed = int(filing_date[:4]), int(filing_date[5:7])
    return year - 1 if month > filed else year


def parse_progressive(text: str, filing_date: str) -> dict:
    """Pull the headline numbers out of a Progressive monthly release (best effort)."""
    out = {"period": None, "combined_ratio": None, "combined_ratio_prior": None,
           "direct_auto_pif": None, "direct_auto_growth": None,
           "agency_auto_pif": None, "agency_auto_growth": None}
    m = re.search(rf"({MONTHS})\s+(?:(\d{{4}})\s+)?results", text[:3000], re.I) or \
        re.search(rf"({MONTHS})\s+(\d{{4}})", text[:3000], re.I)
    if m:
        month = m.group(1).title()
        out["period"] = f"{month} {m.group(2) or _period_year(MONTH_NUMBER[month.lower()], filing_date)}"
    m = re.search(r"combined ratio[^0-9]{0,40}?(\d{2,3}\.\d)\s+(\d{2,3}\.\d)", text, re.I)
    if m:
        out["combined_ratio"], out["combined_ratio_prior"] = float(m.group(1)), float(m.group(2))
    else:
        m = re.search(r"combined ratio(?:\s*\(CR\))?\s*(?:of|was)\s*(\d{2,3}\.\d)", text, re.I)
        if m:
            out["combined_ratio"] = float(m.group(1))
    start = text.lower().find("policies in force")  # premiums tables earlier in the release have auto rows too
    pif = text[start:] if start >= 0 else text
    for channel in ("direct", "agency"):
        m = re.search(PIF_ROW.format(channel=channel), pif, re.I)
        if m:
            out[f"{channel}_auto_pif"] = _num(m.group(1))
            out[f"{channel}_auto_growth"] = -float(m.group(3)) if m.group(3) else float(m.group(4))
    return out


# ---------------------------------------------------------------- collectors
def releases(s: dict, progress=print) -> int:
    snips, pgr_rows = [], []
    for target in s["sec_release_targets"]:
        ticker = target["ticker"]
        cik = cik_for(ticker, s)
        items = filings(cik, s, {"8-K"}, target.get("filings", 6))
        progress(f"  {ticker}: checking {len(items)} recent releases")
        for f in items:
            try:
                idx = get(INDEX_URL.format(cik=cik, acc=f["acc"]), s).json()
            except Exception as exc:
                progress(f"    skipped {f['filing_date']} ({exc})")
                continue
            for it in idx.get("directory", {}).get("item", []):
                name = it["name"]
                if not (EXHIBIT_99.search(name) and name.lower().endswith((".htm", ".html", ".txt"))):
                    continue
                url = DOC_URL.format(cik=cik, acc=f["acc"], name=name)
                text = html_to_text(get(url, s).text)
                for kw in target["keywords"]:
                    for snip in snippets(text, kw):
                        snips.append({"url": url, "keyword": kw, "snippet": snip, "ticker": ticker,
                                      "filing_date": f["filing_date"],
                                      "numbers": ", ".join(NUMBER.findall(snip[:360])[:6])})
                if ticker == "PGR":
                    parsed = parse_progressive(text, f["filing_date"])
                    if parsed["combined_ratio"] is not None or parsed["direct_auto_pif"] is not None:
                        pgr_rows.append({"url": url, "filing_date": f["filing_date"], **parsed})
    db.upsert("release_snippets", snips, ["url", "keyword", "snippet"])
    db.upsert("pgr_monthly", pgr_rows, ["url"], update=[k for k in pgr_rows[0] if k != "url"] if pgr_rows else None)
    progress(f"  {len(snips)} release snippets, {len(pgr_rows)} Progressive months parsed")
    return len(snips)


def fulltext(s: dict, progress=print) -> int:
    rows = []
    for q in s["sec_fulltext_queries"]:
        params = {"q": q, "dateRange": "custom", "startdt": s["sec_fulltext_start"],
                  "enddt": date.today().isoformat(), "forms": s["sec_fulltext_forms"]}
        try:
            hits = get(FULLTEXT_URL, s, params).json().get("hits", {}).get("hits", [])
        except Exception as exc:
            progress(f"  full-text search failed for {q}: {exc}")
            continue
        for h in hits:
            src = h.get("_source", {})
            adsh, _, fname = h.get("_id", "").partition(":")
            ciks = src.get("ciks") or [""]
            if not (ciks[0] and adsh and fname):
                continue
            rows.append({"query": q, "url": DOC_URL.format(cik=int(ciks[0]), acc=adsh.replace("-", ""), name=fname),
                         "company": "; ".join(src.get("display_names", [])),
                         "form": src.get("form") or src.get("file_type", ""),
                         "filing_date": src.get("file_date", ""), "first_seen": date.today().isoformat()})
        progress(f"  full-text {q}: {len(hits)} filings")
    db.upsert("fulltext_hits", rows, ["query", "url"])
    return len(rows)


def _norm(text: str) -> str:
    """Words only: as-of dates, numbers, punctuation and hyphens aren't wording."""
    return " ".join(re.sub(r"[^a-z]+", " ", AS_OF_DATE.sub(" ", text).lower()).split())


def _sentence_start(text: str, pos: int, lookback: int = 400) -> int:
    lo = max(0, pos - lookback)
    ends = list(SENTENCE_END.finditer(text, lo, pos))
    return ends[-1].end() if ends else lo


def doj_passage(text: str, keyword: str, max_chars: int = 1400) -> str:
    """The disclosure paragraph in the financial-statement notes, which 10-Ks and 10-Qs both carry.

    It runs from the sentence that opens with the Department of Justice to the next note heading, so passages are
    comparable from filing to filing. Risk-factor mentions (a 10-K's first "anti-money laundering" is one) are only
    a fallback when no such sentence exists.
    """
    text = PAGE_BREAK.sub("", text)
    kw = re.compile(r"[\s-]+".join(map(re.escape, keyword.split())), re.I)  # "money-laundering" counts too
    starts = [_sentence_start(text, m.start()) for m in DOJ_NAME.finditer(text) if kw.search(text, m.start(), m.start() + 400)]
    if starts:
        start = next((s for s in starts if DOJ_SUBJECT.match(text, s)), starts[0])
    else:
        hit = kw.search(text)
        if not hit:
            return ""
        start = _sentence_start(text, hit.start())
    end = min(len(text), start + max_chars)
    heading = NEXT_NOTE.search(text, start + 1, end)  # a resolved matter may leave a one-sentence paragraph
    if heading:
        end = heading.start()
    elif end < len(text):
        stops = list(SENTENCE_END.finditer(text, start, end))
        end = stops[-1].start() + 2 if stops else end
    return text[start:end].strip()


def previous_same_form(rows: list[dict]) -> list[dict | None]:
    """For rows sorted oldest first: each one's previous filing of the same form (10-Q to 10-Q, 10-K to 10-K)."""
    last: dict[str, dict] = {}
    out = []
    for r in rows:
        out.append(last.get(r["form"]))
        last[r["form"]] = r
    return out


def _compare(prev: dict | None, cur: dict) -> tuple[float | None, int | None]:
    """(similarity, changed) of a filing's passage against the previous one of the same form."""
    if prev is None or not (prev["found"] or cur["found"]):
        return None, None
    if prev["found"] != cur["found"]:
        return 0.0, 1  # the passage appeared or disappeared
    a, b = _norm(prev["disclosure"]).split(), _norm(cur["disclosure"]).split()
    # Share of words kept (character-level matching is unreliable on long text); any real word change counts
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3), int(a != b)


def doj(s: dict, progress=print) -> dict:
    cik = cik_for(s["doj_ticker"], s)
    found = []
    for f in filings(cik, s, {"10-K", "10-Q"}, s["doj_filings"]):
        url = DOC_URL.format(cik=cik, acc=f["acc"], name=f["primary_doc"])
        passage = doj_passage(html_to_text(get(url, s).text), s["doj_keyword"])
        found.append({"url": url, "filing_date": f["filing_date"], "form": f["form"],
                      "found": int(bool(passage)), "disclosure": passage})
    found.sort(key=lambda r: r["filing_date"])
    rows = [{**r, **dict(zip(("similarity", "changed"), _compare(prev, r)))}
            for r, prev in zip(found, previous_same_form(found))]
    db.upsert("doj", rows, ["url"], update=["found", "disclosure", "similarity", "changed"])
    changed = [r for r in rows if r["changed"]]
    progress(f"  DOJ disclosure: {'wording changed in ' + ', '.join(r['form'] + ' ' + r['filing_date'] for r in changed) if changed else 'wording unchanged'} across {len(rows)} filings")
    return {"filings": len(rows), "changed": [r["filing_date"] for r in changed]}


def run(s: dict, progress=print) -> dict:
    _headers(s)
    progress("SEC: company releases")
    n_snips = releases(s, progress)
    progress("SEC: full-text search")
    n_hits = fulltext(s, progress)
    progress("SEC: DOJ disclosure tracker")
    d = doj(s, progress)
    return {"snippets": n_snips, "fulltext": n_hits, "doj": d}


def word_diff(old: str, new: str) -> str:
    """HTML with removed words in <del> and added words in <ins>."""
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == "equal":
            out.append(html.escape(" ".join(a[i1:i2])))
        if op in ("delete", "replace"):
            out.append(f"<del>{html.escape(' '.join(a[i1:i2]))}</del>")
        if op in ("insert", "replace"):
            out.append(f"<ins>{html.escape(' '.join(b[j1:j2]))}</ins>")
    return " ".join(out)


def doj_status() -> dict:
    rows = db.query("SELECT filing_date, form, url, found, changed FROM doj ORDER BY filing_date")
    if not rows:
        return {"known": False}
    latest = rows[-1]
    return {"known": True, "filings": len(rows), "latest": latest["filing_date"], "latest_form": latest["form"],
            "changed_latest": bool(latest["changed"]),
            "last_change": next((r["filing_date"] for r in reversed(rows) if r["changed"]), None),
            "found_latest": bool(latest["found"])}
