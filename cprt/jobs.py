"""Run long tasks (weekly update, captures) in the background so the console stays responsive.

Each job is a `cli.py` subprocess. It writes progress to data/jobs/<id>.json and its
output to data/jobs/<id>.log; the console polls those files. One job runs at a time.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

from . import paths

LABELS = {
    "weekly": "Weekly update", "scheduled": "Scheduled update", "scan": "Scanning Copart",
    "news": "Updating news", "macro": "Updating macro data",
    "sec": "Updating SEC filings", "capture_auto": "Capturing saved pages",
    "capture_guided": "Recording browsing session", "report": "Building report",
}
_procs: dict[str, subprocess.Popen] = {}


def _dir():
    return paths.data_path("jobs", "x.json").parent


def status_path(job_id: str):
    return _dir() / f"{job_id}.json"


def write_status(job_id: str, **fields) -> dict:
    """Merge fields into the job's status file (called by the running job)."""
    p = status_path(job_id)
    cur = json.loads(p.read_text()) if p.exists() else {}
    cur.update(fields, updated=datetime.now().isoformat(timespec="seconds"))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, default=str))
    tmp.replace(p)
    return cur


def _alive(job: dict) -> bool:
    proc = _procs.get(job["id"])
    if proc is not None:
        return proc.poll() is None
    try:
        os.kill(int(job.get("pid", 0)), 0)
        return True
    except (OSError, ValueError):
        return False


def latest() -> dict | None:
    files = sorted(_dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files:
        try:
            job = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if job.get("status") == "running" and not _alive(job):
            job = write_status(job["id"], status="failed", message="The job stopped unexpectedly. See its log.")
        log = _dir() / f"{job['id']}.log"
        job["log_tail"] = log.read_text(errors="replace").splitlines()[-14:] if log.exists() else []
        job["label"] = LABELS.get(job.get("kind"), job.get("kind"))
        return job
    return None


def running() -> dict | None:
    job = latest()
    return job if job and job.get("status") == "running" else None


def start(kind: str, args: list[str]) -> dict:
    if running():
        raise RuntimeError("Another task is still running. Wait for it to finish.")
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + kind
    write_status(job_id, id=job_id, kind=kind, status="running", message="Starting...",
                 started=datetime.now().isoformat(timespec="seconds"))
    log = open(_dir() / f"{job_id}.log", "w")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "CPRT_DATA_DIR": str(paths.DATA)}
    proc = subprocess.Popen([sys.executable, str(paths.ROOT / "cli.py"), *args, "--job-id", job_id],
                            stdout=log, stderr=subprocess.STDOUT, cwd=str(paths.ROOT), env=env,
                            start_new_session=True)
    log.close()  # the child keeps its own handle
    _procs[job_id] = proc
    return write_status(job_id, pid=proc.pid)


def request_stop(job_id: str) -> None:
    (_dir() / f"{job_id}.stop").touch()


def stop_file(job_id: str | None):
    return _dir() / f"{job_id}.stop" if job_id else None
