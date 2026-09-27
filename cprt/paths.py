"""Where things live. Set CPRT_DATA_DIR to keep data somewhere else (tests do this)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("CPRT_DATA_DIR", ROOT / "data"))


def data_path(*parts: str, mkdir: bool = True) -> Path:
    """Path inside the data folder; parent folders are created on demand."""
    path = DATA.joinpath(*parts)
    if mkdir:
        (path if not path.suffix else path.parent).mkdir(parents=True, exist_ok=True)
    return path
