"""Turn lot sightings into the insurer split: what share of each insurer's salvage sits on Copart.

    copart_share = copart_lots / (copart_lots + iaa_lots)

Computed only in states where BOTH platforms were sampled that week (otherwise a
state sampled on one site only would skew the split), with 95% Wilson intervals.
It measures listed inventory, not contract terms; weekly new-lot flow is the
closer proxy for assignments once several weeks exist.
"""
from __future__ import annotations

import math

import pandas as pd

from . import carriers, db

COLS = ["obs_date", "platform", "lot_id", "state", "yard", "seller_raw", "make", "model",
        "year", "damage", "sale_date", "source_url", "origin"]
SELLER_COVERAGE_NEEDED = 0.5  # below this on either site, the split is hidden with an explanation


def split_problem(m: dict) -> str | None:
    """Why the insurer split can't be shown for a week's metrics, in plain words, or None when it can."""
    if not m.get("has_data"):
        return "there is no listing data yet."
    cov = {p: c for p, c in (m.get("seller_coverage") or {}).items() if c is not None}
    if len(cov) < 2:
        return "only one site has listing data, and the split compares Copart with IAA."
    low = min(cov.values())
    if low < SELLER_COVERAGE_NEEDED:
        return f"seller names show on only {low:.0%} of one site's listings, so most lots can't be credited to an insurer."
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def two_prop_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided p-value that two shares differ (normal approximation)."""
    if min(n1, n2) == 0:
        return 1.0
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(k1 / n1 - k2 / n2) / se
    return math.erfc(z / math.sqrt(2))


def load(settings: dict) -> pd.DataFrame:
    df = db.df("SELECT * FROM observations")
    if df.empty:
        return pd.DataFrame(columns=COLS + ["carrier", "week", "date"])
    for c in COLS:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["platform"] = df["platform"].str.lower()
    df = df[df["platform"].isin(["copart", "iaa"])].copy()
    df["state"] = df["state"].str.upper()
    overrides = settings.get("carrier_overrides") or {}
    df["carrier"] = [carriers.canonical(s, overrides) for s in df["seller_raw"]]
    df["date"] = pd.to_datetime(df["obs_date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["week"] = (df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    return df


def paired(frame: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    by = by or []
    keys = by + ["state"]
    if frame.empty:
        return frame
    plats = frame.groupby(keys)["platform"].nunique()
    ok = set(plats[plats == 2].index)
    mask = [tuple(x) in ok if len(keys) > 1 else x[0] in ok for x in frame[keys].itertuples(index=False)]
    return frame[mask]


def share_table(frame: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    by = by or []
    cols = by + ["carrier", "copart", "iaa", "n", "share", "lo", "hi"]
    if frame.empty:
        return pd.DataFrame(columns=cols)
    uniq = frame.drop_duplicates(by + ["platform", "lot_id"])
    g = uniq.groupby(by + ["carrier", "platform"]).size().unstack("platform", fill_value=0)
    for col in ("copart", "iaa"):
        if col not in g:
            g[col] = 0
    g["n"] = g["copart"] + g["iaa"]
    g["share"] = g["copart"] / g["n"]
    ci = [wilson(int(k), int(n)) for k, n in zip(g["copart"], g["n"])]
    g["lo"] = [a for a, _ in ci]
    g["hi"] = [b for _, b in ci]
    g = g.reset_index()
    return g.sort_values(by + ["n"], ascending=[True] * len(by) + [False])[cols].reset_index(drop=True)


def _split_record(copart: int, iaa: int) -> dict:
    n = copart + iaa
    lo, hi = wilson(copart, n)
    return {"copart": int(copart), "iaa": int(iaa), "n": int(n),
            "share": copart / n if n else None, "lo": lo if n else None, "hi": hi if n else None}


def weeks(df: pd.DataFrame) -> list[str]:
    return sorted(df["week"].unique(), reverse=True) if not df.empty else []


def metrics(settings: dict, week: str | None = None, df: pd.DataFrame | None = None) -> dict:
    """Everything the dashboard needs for one week (default: the latest week with data)."""
    df = load(settings) if df is None else df
    if df.empty:
        return {"week": None, "has_data": False}
    week = week or weeks(df)[0]
    wk = df[df["week"] == week]
    pw = paired(wk)
    ins = pw[pw["carrier"].map(carriers.is_insurer).astype(bool)]  # an empty object-dtype mask would pick columns
    table = share_table(pw)
    carriers_out = {r["carrier"]: _split_record(r["copart"], r["iaa"]) for _, r in table.iterrows()}
    cov = wk.drop_duplicates(["platform", "lot_id"]).groupby(["state", "platform"]).size().unstack(fill_value=0)
    coverage = {s: {"copart": int(r.get("copart", 0)), "iaa": int(r.get("iaa", 0))} for s, r in cov.iterrows()} if not cov.empty else {}
    uniq = wk.drop_duplicates(["platform", "lot_id"])
    seller_cov = {p: (float((g["seller_raw"] != "").mean()) if len(g) else None) for p, g in uniq.groupby("platform")}
    return {
        "week": week, "has_data": True,
        "lots": int(len(uniq)),
        "lots_by_platform": {p: int(n) for p, n in uniq.groupby("platform").size().items()},
        "paired_states": sorted(s for s in pw["state"].unique()),
        "unpaired_states": sorted(s for s, c in coverage.items() if min(c["copart"], c["iaa"]) == 0),
        "overall": _split_record(int((ins["platform"] == "copart").sum()), int((ins["platform"] == "iaa").sum())),
        "carriers": carriers_out,
        "coverage": coverage,
        "seller_coverage": seller_cov,
    }


def weekly_history(settings: dict, df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = load(settings) if df is None else df
    frames = []
    for wk, grp in df.groupby("week"):
        pw = paired(grp)
        if pw.empty:
            continue
        t = share_table(pw)
        ins = pw[pw["carrier"].map(carriers.is_insurer).astype(bool)].drop_duplicates(["platform", "lot_id"])
        overall = _split_record(int((ins["platform"] == "copart").sum()), int((ins["platform"] == "iaa").sum()))
        t = pd.concat([t, pd.DataFrame([{"carrier": "All insurers", **overall}])], ignore_index=True)
        frames.append(t.assign(week=wk))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["week", "carrier", "copart", "iaa", "n", "share", "lo", "hi"])


def state_table(settings: dict, week: str, df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = load(settings) if df is None else df
    return share_table(paired(df[df["week"] == week]), ["state"])


def new_lot_flow(settings: dict, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Lots seen for the first time each week (after each platform's first week of tracking)."""
    df = load(settings) if df is None else df
    if df.empty:
        return pd.DataFrame(columns=["week", "platform", "carrier", "new_lots"])
    first = df.sort_values("date").drop_duplicates(["platform", "lot_id"])
    first = first[first["week"] > first.groupby("platform")["week"].transform("min")]
    return first.groupby(["week", "platform", "carrier"]).size().rename("new_lots").reset_index()


def unmapped_sellers(settings: dict, df: pd.DataFrame | None = None, limit: int = 40) -> pd.DataFrame:
    df = load(settings) if df is None else df
    if df.empty:
        return pd.DataFrame(columns=["seller_raw", "carrier", "lots"])
    u = df[(df["seller_raw"] != "") & df["carrier"].isin(["Unknown", "Other insurer"])]
    return (u.groupby(["seller_raw", "carrier"]).size().rename("lots").reset_index()
            .sort_values("lots", ascending=False).head(limit))
