"""Work out which JSON field holds what (lot number, seller, state...) from the values.

Copart and IAA don't document their data and their field names are often cryptic
("scn", "yn", "lcy"). Instead of asking you to map fields by hand, every field is
profiled - are the values unique IDs? insurer names? car makes? 4-digit years? -
and each target gets the field that looks most like it. Name hints only break ties.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from . import carriers

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "PR", "RI", "SC", "SD", "TN", "TX",
    "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}
MAKES = {
    "ACURA", "ALFA ROMEO", "AUDI", "BMW", "BUICK", "CADILLAC", "CHEVROLET", "CHEVY", "CHRYSLER",
    "DODGE", "FIAT", "FORD", "FREIGHTLINER", "GENESIS", "GMC", "HARLEY-DAVIDSON", "HONDA", "HYUNDAI",
    "INFINITI", "INTERNATIONAL", "ISUZU", "JAGUAR", "JEEP", "KAWASAKI", "KENWORTH", "KIA",
    "LAND ROVER", "LEXUS", "LINCOLN", "MASERATI", "MAZDA", "MERCEDES-BENZ", "MERCEDES", "MERCURY",
    "MINI", "MITSUBISHI", "NISSAN", "PETERBILT", "POLARIS", "PONTIAC", "PORSCHE", "RAM", "RIVIAN",
    "SATURN", "SCION", "SMART", "SUBARU", "SUZUKI", "TESLA", "TOYOTA", "VOLKSWAGEN", "VOLVO", "VW",
    "YAMAHA", "POLESTAR", "LUCID",
}
DAMAGE_WORDS = ("FRONT", "REAR", "SIDE", "HAIL", "FLOOD", "WATER", "MECHANICAL", "ALL OVER",
                "ROLLOVER", "ROOF", "VANDAL", "BURN", "FIRE", "UNDERCARRIAGE", "MINOR", "DENT",
                "NORMAL WEAR", "STRIP", "BIOHAZARD", "ELECTRICAL", "ENGINE", "SUSPENSION", "FRAME",
                "THEFT", "STOLEN", "PARTIAL REPAIR", "REPLACED VIN", "DAMAGE", "COLLISION", "TOP")
HINTS = {
    "lot_id": r"lot|stock|item|^id$|^ln$",
    "seller": r"seller|slr|consignor|vendor|scn|owner|insur",
    "state": r"state|^st$|province",
    "yard": r"yard|branch|location|facility|^yn$|site|city",
    "make": r"make|mkn|^mk$|manufacturer",
    "model": r"model|^lm$|mmod",
    "year": r"year|^yr$|lcy",
    "damage": r"damage|^dd$|loss|pdmg",
    "sale_date": r"date|^ad$|auction|sale",
}
ORDER = ["lot_id", "year", "make", "seller", "state", "yard", "damage", "sale_date", "model"]
STATE_PATTERNS = [re.compile(r"^\s*([A-Z]{2})\s*-\s*"), re.compile(r"\(([A-Z]{2})\)"),
                  re.compile(r",\s*([A-Z]{2})\b"), re.compile(r"\b([A-Z]{2})\s+\d{5}\b")]


def flatten(d: dict, prefix: str = "", depth: int = 0) -> dict:
    """Flatten nested dicts (2 levels) into dotted keys; skip nested lists (photos etc.)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and depth < 2:
            out.update(flatten(v, key + ".", depth + 1))
        elif not isinstance(v, (list, tuple)):
            out[key] = v
    return out


def parse_state(*values) -> str:
    for v in values:
        if v in (None, ""):
            continue
        s = str(v).strip().upper()
        if s in US_STATES:
            return s
        for rx in STATE_PATTERNS:
            m = rx.search(s)
            if m and m.group(1) in US_STATES:
                return m.group(1)
    return ""


def _is_year(v) -> bool:
    # Check the shape first: float("INFINITY") (a make code in Copart's reference data) can't become an int.
    s = str(v).strip()
    return re.fullmatch(r"\d{4}(\.0)?", s) is not None and 1950 <= int(float(s)) <= 2030


def _is_date(v) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return 1e9 <= v <= 2.2e9 or 1e12 <= v <= 2.2e12  # epoch seconds / milliseconds
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", str(v))) or bool(re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", str(v)))


def to_date(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        secs = v / 1000 if v > 1e11 else v
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(v))
    return m.group(0) if m else str(v)[:20]


def _mean(flags) -> float:
    flags = list(flags)
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


def profile(records: list[dict]) -> dict[str, dict]:
    flats = [flatten(r) for r in records[:200] if isinstance(r, dict)]
    if not flats:
        return {}
    counts: dict[str, int] = {}
    for f in flats:
        for k in f:
            counts[k] = counts.get(k, 0) + 1
    out = {}
    for key, c in counts.items():
        if c < 0.5 * len(flats):
            continue
        vals = [f[key] for f in flats if f.get(key) not in (None, "", " ")]
        if not vals:
            continue
        strs = [str(v).strip() for v in vals]
        groups = [carriers.canonical(s) for s in strs]
        out[key] = {
            "n": len(strs),
            "unique": len(set(strs)) / len(strs),
            "fixed_len": Counter(len(x) for x in strs).most_common(1)[0][1] / len(strs),
            "id_like": _mean(re.fullmatch(r"[A-Z0-9-]{5,14}", s.upper()) and any(ch.isdigit() for ch in s)
                             and not re.fullmatch(r"\d{4}", s) for s in strs),
            "named_carrier": _mean(g not in carriers.NOT_INSURANCE for g in groups),
            "any_seller": _mean(g != "Unknown" for g in groups),
            "state_code": _mean(s.upper() in US_STATES for s in strs),
            "state_in_text": _mean(parse_state(s) != "" for s in strs),
            "make": _mean(s.upper() in MAKES for s in strs),
            "year": _mean(_is_year(v) for v in vals),
            "damage": _mean(any(w in s.upper() for w in DAMAGE_WORDS) for s in strs),
            "date": _mean(_is_date(v) for v in vals),
            "numeric": _mean(isinstance(v, (int, float)) or re.fullmatch(r"-?\d+(\.\d+)?", s) for v, s in zip(vals, strs)),
            "avg_len": sum(len(s) for s in strs) / len(strs),
        }
    return out


def _score(field: str, key: str, f: dict) -> float:
    hint = 1.0 if re.search(HINTS[field], key.split(".")[-1], re.I) else 0.0
    if field == "lot_id":
        ok = f["unique"] >= 0.9 and f["id_like"] >= 0.8 and f["date"] < 0.5 and f["year"] < 0.5
        return 2 * f["unique"] + 2 * f["id_like"] + 1.5 * f["fixed_len"] + hint if ok else 0.0
    if field == "seller":
        ok = (f["named_carrier"] >= 0.15 or (hint and f["numeric"] < 0.5)) and f["make"] < 0.5
        return 3 * f["named_carrier"] + f["any_seller"] + hint if ok else 0.0
    if field == "state":
        return 3 * f["state_code"] + hint if f["state_code"] >= 0.8 else 0.0
    if field == "yard":
        if f["state_in_text"] >= 0.6 and f["state_code"] < 0.8:
            return 2 * f["state_in_text"] + hint
        return 0.5 if hint and f["numeric"] < 0.5 and f["avg_len"] > 3 else 0.0
    if field == "make":
        return 3 * f["make"] + hint if f["make"] >= 0.6 else 0.0
    if field == "year":
        return 3 * f["year"] + hint if f["year"] >= 0.8 else 0.0
    if field == "damage":
        return 3 * f["damage"] + hint if f["damage"] >= 0.5 and f["named_carrier"] < 0.3 else 0.0
    if field == "sale_date":
        return 2 * f["date"] + hint if f["date"] >= 0.8 else 0.0
    if field == "model":
        plain = f["numeric"] < 0.5 and f["make"] < 0.2 and f["named_carrier"] < 0.1 and f["damage"] < 0.3
        return 1.0 + hint if hint and plain else 0.0
    return 0.0


def infer_mapping(records: list[dict], overrides: dict | None = None) -> tuple[dict, dict]:
    """Return ({field: json_key}, {field: score}) for one list of records."""
    prof = profile(records)
    mapping, conf, used = {}, {}, set()
    for field, key in (overrides or {}).items():
        if key in prof:
            mapping[field], conf[field] = key, 99.0
            used.add(key)
    for field in ORDER:
        if field in mapping:
            continue
        best = max(((_score(field, k, f), k) for k, f in prof.items() if k not in used), default=(0.0, None))
        if best[0] > 0:
            mapping[field], conf[field] = best[1], round(best[0], 2)
            used.add(best[1])
    return mapping, conf
