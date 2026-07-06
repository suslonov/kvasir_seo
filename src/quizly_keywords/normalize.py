"""Stage 5a: deduplicate and merge discovered keywords with volume metrics.

Produces one row per (normalized keyword, location, language) with metrics and
provenance (all source terms / endpoints that surfaced it) preserved.
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_keyword(keyword: str) -> str:
    kw = (keyword or "").lower().strip()
    kw = _PUNCT_RE.sub(" ", kw)
    return _WS_RE.sub(" ", kw).strip()


def _keyword_id(normalized: str, location_code, language_code) -> str:
    h = hashlib.sha1(f"{normalized}|{location_code}|{language_code}".encode("utf-8"))
    return h.hexdigest()[:16]


def _join_unique(series: pd.Series) -> str:
    vals = {str(v).strip() for v in series.dropna() if str(v).strip()}
    return "|".join(sorted(vals))


def _first_non_null(series: pd.Series):
    for v in series:
        if pd.notna(v):
            return v
    return None


def merge(discovered: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    if discovered.empty:
        return discovered.assign(keyword_id=[], keyword_normalized=[])

    disc = discovered.copy()
    disc["keyword_normalized"] = disc["keyword"].astype(str).map(normalize_keyword)
    disc = disc[disc["keyword_normalized"].str.len() > 0]

    # Bring in provenance columns if present (from candidate terms upstream).
    source_url_col = "source_url" if "source_url" in disc.columns else None

    agg = {
        "keyword": ("keyword", "first"),
        "search_volume": ("search_volume", "max"),
        "cpc": ("cpc", "max"),
        "competition": ("competition", "max"),
        "competition_level": ("competition_level", _first_non_null),
        "keyword_difficulty": ("keyword_difficulty", "max"),
        "source_terms": ("source_term", _join_unique),
        "source_endpoints": ("source_endpoint", _join_unique),
        "categories": ("categories", _join_unique),
    }
    if source_url_col:
        agg["source_urls"] = (source_url_col, _join_unique)

    grouped = disc.groupby(
        ["keyword_normalized", "location_code", "language_code"], dropna=False
    ).agg(**agg).reset_index()
    if not source_url_col:
        grouped["source_urls"] = ""

    # Merge Google Ads metrics (authoritative for volume/trend) if available.
    if metrics is not None and not metrics.empty:
        m = metrics.copy()
        m["keyword_normalized"] = m["keyword"].astype(str).map(normalize_keyword)
        keep = ["keyword_normalized", "location_code", "language_code",
                "search_volume", "cpc", "competition", "trend_3m", "trend_12m",
                "monthly_searches_json", "competition_index"]
        keep = [c for c in keep if c in m.columns]
        m = m[keep].drop_duplicates(["keyword_normalized", "location_code", "language_code"])
        grouped = grouped.merge(
            m, on=["keyword_normalized", "location_code", "language_code"],
            how="left", suffixes=("", "_ads"),
        )
        # Prefer Google Ads metrics where present.
        for col in ("search_volume", "cpc", "competition"):
            ads = f"{col}_ads"
            if ads in grouped.columns:
                grouped[col] = grouped[ads].combine_first(grouped[col])
                grouped = grouped.drop(columns=[ads])
    for col in ("trend_3m", "trend_12m", "monthly_searches_json", "competition_index"):
        if col not in grouped.columns:
            grouped[col] = None

    grouped["keyword_id"] = grouped.apply(
        lambda r: _keyword_id(r["keyword_normalized"], r["location_code"], r["language_code"]),
        axis=1,
    )
    return grouped
