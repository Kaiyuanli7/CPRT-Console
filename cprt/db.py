"""SQLite storage (data/console.db). One file holds every week of history."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, url TEXT UNIQUE, label TEXT,
  enabled INTEGER DEFAULT 1, origin TEXT, added TEXT, last_run TEXT, last_status TEXT,
  last_lots INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS observations(
  obs_date TEXT, platform TEXT, lot_id TEXT, state TEXT, yard TEXT, seller_raw TEXT,
  make TEXT, model TEXT, year TEXT, damage TEXT, sale_date TEXT, source_url TEXT, origin TEXT,
  PRIMARY KEY(obs_date, platform, lot_id));
CREATE INDEX IF NOT EXISTS obs_by_platform ON observations(platform, lot_id);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started TEXT, finished TEXT, status TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS news(
  key TEXT PRIMARY KEY, title TEXT, source TEXT, published TEXT, link TEXT, summary TEXT,
  score INTEGER, matched TEXT, queries TEXT, first_seen TEXT, starred INTEGER DEFAULT 0,
  read INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS macro(series_id TEXT, date TEXT, value REAL, PRIMARY KEY(series_id, date));
CREATE TABLE IF NOT EXISTS pgr_monthly(
  url TEXT PRIMARY KEY, filing_date TEXT, period TEXT, combined_ratio REAL, combined_ratio_prior REAL,
  direct_auto_pif REAL, direct_auto_growth REAL, agency_auto_pif REAL, agency_auto_growth REAL);
CREATE TABLE IF NOT EXISTS release_snippets(
  url TEXT, keyword TEXT, snippet TEXT, ticker TEXT, filing_date TEXT, numbers TEXT,
  PRIMARY KEY(url, keyword, snippet));
CREATE TABLE IF NOT EXISTS fulltext_hits(
  query TEXT, url TEXT, company TEXT, form TEXT, filing_date TEXT, first_seen TEXT,
  PRIMARY KEY(query, url));
CREATE TABLE IF NOT EXISTS doj(
  url TEXT PRIMARY KEY, filing_date TEXT, form TEXT, found INTEGER, disclosure TEXT,
  similarity REAL, changed INTEGER);
CREATE TABLE IF NOT EXISTS snapshots(week TEXT PRIMARY KEY, created TEXT, metrics TEXT);
CREATE TABLE IF NOT EXISTS inventory(
  obs_date TEXT, platform TEXT, view TEXT, dimension TEXT, key TEXT, count INTEGER, source_url TEXT, captured TEXT,
  PRIMARY KEY(obs_date, platform, view, dimension, key));
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(paths.data_path("console.db"), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


@contextmanager
def session():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with session() as con:
        return pd.read_sql_query(sql, con, params=params)


def query(sql: str, params: tuple = ()) -> list[dict]:
    with session() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def scalar(sql: str, params: tuple = ()):
    with session() as con:
        row = con.execute(sql, params).fetchone()
        return row[0] if row else None


def execute(sql: str, params: tuple = ()) -> int:
    with session() as con:
        return con.execute(sql, params).rowcount


def upsert(table: str, rows: list[dict], keys: list[str], update: list[str] | None = None) -> int:
    """Insert rows; on key conflict update `update` columns (or ignore). Returns rows changed."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
    if update:
        sql += f" ON CONFLICT({','.join(keys)}) DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in update)
    else:
        sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
    with session() as con:
        before = con.total_changes
        con.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
        return con.total_changes - before


def save_observations(rows: list[dict]) -> int:
    """Add lot sightings; a repeat sighting on the same day only fills in blank fields."""
    if not rows:
        return 0
    cols = ["obs_date", "platform", "lot_id", "state", "yard", "seller_raw", "make", "model",
            "year", "damage", "sale_date", "source_url", "origin"]
    fill = [c for c in cols if c not in ("obs_date", "platform", "lot_id")]
    sql = (f"INSERT INTO observations({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
           "ON CONFLICT(obs_date, platform, lot_id) DO UPDATE SET "
           + ",".join(f"{c}=CASE WHEN IFNULL({c},'')='' THEN excluded.{c} ELSE {c} END" for c in fill))
    with session() as con:
        before = con.total_changes
        con.executemany(sql, [tuple("" if r.get(c) is None else str(r.get(c)) for c in cols) for r in rows])
        return con.total_changes - before


def log_run(kind: str, status: str, message: str, started: str) -> None:
    with session() as con:
        con.execute("INSERT INTO runs(kind, started, finished, status, message) VALUES(?,?,?,?,?)",
                    (kind, started, now(), status, message[:2000]))


def last_runs() -> dict[str, dict]:
    rows = query("SELECT r.* FROM runs r JOIN (SELECT kind, MAX(id) AS id FROM runs GROUP BY kind) m "
                 "ON r.id = m.id")
    return {r["kind"]: r for r in rows}


def last_success(kind: str) -> str | None:
    return scalar("SELECT finished FROM runs WHERE kind=? AND status='ok' ORDER BY id DESC LIMIT 1", (kind,))
