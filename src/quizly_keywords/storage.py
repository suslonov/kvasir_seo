"""Read/write helpers for raw JSONL and processed parquet/csv artifacts.

Parquet is used where available; if pyarrow is missing we transparently fall
back to CSV so the pipeline still runs in a minimal environment.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .settings import PROCESSED_DIR, RAW_DIR


def date_bucket() -> str:
    """Month bucket used for cache keys and raw filenames, e.g. 2026-07."""
    return date.today().strftime("%Y-%m")


def today_stamp() -> str:
    return date.today().strftime("%Y%m%d")


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Append records to a JSONL file, creating parent dirs. Returns count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _has_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401

        return True
    except ImportError:
        return False


def write_table(df: pd.DataFrame, path: Path) -> Path:
    """Write a DataFrame to parquet (preferred) or csv fallback.

    If `path` ends in .parquet but pyarrow is unavailable, writes .csv beside it
    and returns the actual path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        if _has_parquet():
            df.to_parquet(path, index=False)
            return path
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path
    df.to_csv(path, index=False)
    return path


def read_table(path: Path) -> pd.DataFrame:
    """Read a processed table, tolerating the parquet->csv fallback."""
    if path.suffix == ".parquet":
        if path.exists() and _has_parquet():
            return pd.read_parquet(path)
        csv_path = path.with_suffix(".csv")
        if csv_path.exists():
            return pd.read_csv(csv_path)
        if path.exists():  # parquet exists but no engine; let pandas raise clearly
            return pd.read_parquet(path)
        raise FileNotFoundError(f"Missing {path} (and {csv_path})")
    return pd.read_csv(path)


def processed(name: str) -> Path:
    return PROCESSED_DIR / name


def raw(name: str) -> Path:
    return RAW_DIR / name
