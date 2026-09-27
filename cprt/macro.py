"""Macro "total-loss math" from public FRED and BLS series (no API key).

A car is totaled when repair cost is a high share of its value, so repair prices
rising faster than used-car prices mechanically pushes more wrecks into salvage.
"""
from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd

from . import db, net

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
BLS_API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_YEARS = 10  # the keyless BLS API returns at most 10 years per request, and 25 requests a day
MONTHLY = re.compile(r"M(0[1-9]|1[0-2])")  # BLS periods M01-M12; M13 is the annual average


def fetch(series_id: str) -> pd.DataFrame:
    if series_id.startswith("BLS:"):
        return fetch_bls(series_id[4:])
    df = pd.read_csv(io.StringIO(net.http_get(FRED_CSV.format(sid=series_id), min_interval=1.0).text))
    out = pd.DataFrame({"date": pd.to_datetime(df.iloc[:, 0]).dt.strftime("%Y-%m-%d"),
                        "value": pd.to_numeric(df.iloc[:, 1], errors="coerce")})  # FRED uses "." for missing
    return out.dropna()


def fetch_bls(series_id: str) -> pd.DataFrame:
    end = date.today().year
    body = net.http_post(BLS_API, {"seriesid": [series_id], "startyear": str(end - BLS_YEARS + 1),
                                   "endyear": str(end)}).json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError("BLS said: " + ("; ".join(body.get("message") or []) or str(body.get("status"))))
    monthly = [p for p in body["Results"]["series"][0]["data"] if MONTHLY.fullmatch(p.get("period", ""))]
    if not monthly:
        raise RuntimeError(f"BLS returned no monthly values for {series_id}")
    out = pd.DataFrame({"date": [f"{p['year']}-{p['period'][1:]}-01" for p in monthly],
                        "value": pd.to_numeric(pd.Series([p["value"] for p in monthly]), errors="coerce")})
    return out.dropna().sort_values("date").reset_index(drop=True)


def run(settings: dict, progress=print) -> dict:
    fetched = 0
    for role, (sid, label) in settings["fred_series"].items():
        try:
            d = fetch(sid)
            db.upsert("macro", [{"series_id": sid, "date": r.date, "value": float(r.value)} for r in d.itertuples()],
                      ["series_id", "date"], update=["value"])
            fetched += 1
            progress(f"  {label}: {len(d)} months, latest {d['date'].iloc[-1]}")
        except Exception as exc:
            progress(f"  {label} ({sid}) failed: {exc}")
    if not fetched:
        raise RuntimeError("No FRED data retrieved - check the internet connection.")
    return latest(settings)


def frame(settings: dict) -> pd.DataFrame:
    raw = db.df("SELECT series_id, date, value FROM macro")
    if raw.empty:
        return pd.DataFrame()
    wide = raw.pivot_table(index="date", columns="series_id", values="value")
    wide.index = pd.to_datetime(wide.index)
    df = pd.DataFrame(index=wide.index.sort_values())
    for role, (sid, _) in settings["fred_series"].items():
        if sid in wide:
            df[role] = wide[sid]
            df[f"{role}_yoy"] = (df[role] / df[role].shift(12) - 1) * 100
    for num, name in (("repair_cpi", "pressure_repair"), ("parts_cpi", "pressure_parts")):
        if num in df and "used_car_cpi" in df:
            ratio = df[num] / df["used_car_cpi"]
            base = ratio.loc["2019-01-01":"2019-12-31"].mean()
            df[name] = ratio / base * 100
    if "repair_cpi_yoy" in df and "used_car_cpi_yoy" in df:
        df["repair_minus_used"] = df["repair_cpi_yoy"] - df["used_car_cpi_yoy"]
    return df


def _last(df: pd.DataFrame, col: str):
    if col not in df:
        return None, None
    s = df[col].dropna()
    return (s.index[-1].strftime("%Y-%m-%d"), float(s.iloc[-1])) if len(s) else (None, None)


def latest(settings: dict, df: pd.DataFrame | None = None) -> dict:
    df = frame(settings) if df is None else df
    if df.empty:
        return {}
    out = {}
    for col in ("pressure_repair", "pressure_parts", "repair_minus_used", "insurance_cpi_yoy",
                "used_car_cpi_yoy", "repair_cpi_yoy", "vmt_12m_yoy"):
        d, v = _last(df, col)
        if d:
            out[col] = {"date": d, "value": v}
    if "pressure_repair" in df:
        s = df["pressure_repair"].dropna()
        if len(s) > 12:
            out["pressure_repair"]["year_ago"] = float(s.iloc[-13])
    if "insurance_cpi_yoy" in df:
        out["insurance_cpi_peak"] = float(df.loc["2022-01-01":, "insurance_cpi_yoy"].max())
    return out
