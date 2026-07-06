"""Optional Source E: Google Trends Explore for rising/relative interest.

Google Ads Search Volume (stage 04) already gives absolute monthly volume. Trends
adds *relative* interest and a rising/falling signal, useful for prioritizing
timely topics. Explore accepts up to 5 keywords per call, so we batch in fives.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .dataforseo_client import CallBudgetExceeded, DataForSEOClient

logger = logging.getLogger(__name__)

TREND_COLUMNS = [
    "keyword", "trend_interest_latest", "trend_interest_avg",
    "trend_direction", "trend_slope", "trend_checked_at",
]

BATCH = 5


def _series_for_keyword(data: dict, keyword: str) -> list[float]:
    """Pull the interest-over-time values for `keyword` from an Explore result."""
    for result in DataForSEOClient.extract_results(data):
        for item in result.get("items") or []:
            if item.get("type") != "google_trends_graph":
                continue
            kw_index = None
            keywords = item.get("keywords") or []
            for i, k in enumerate(keywords):
                if str(k).lower() == keyword.lower():
                    kw_index = i
                    break
            values: list[float] = []
            for point in item.get("data") or []:
                vals = point.get("values") or []
                if kw_index is not None and kw_index < len(vals) and vals[kw_index] is not None:
                    values.append(float(vals[kw_index]))
                elif vals and vals[0] is not None:
                    values.append(float(vals[0]))
            if values:
                return values
    return []


def _summarize(values: list[float]) -> dict:
    if not values:
        return {"trend_interest_latest": None, "trend_interest_avg": None,
                "trend_direction": None, "trend_slope": None}
    latest = values[-1]
    avg = sum(values) / len(values)
    # Simple slope: last quarter mean vs first quarter mean.
    q = max(1, len(values) // 4)
    early = sum(values[:q]) / q
    late = sum(values[-q:]) / q
    slope = round(late - early, 3)
    direction = "rising" if slope > 3 else "falling" if slope < -3 else "flat"
    return {
        "trend_interest_latest": round(latest, 2),
        "trend_interest_avg": round(avg, 2),
        "trend_direction": direction,
        "trend_slope": slope,
    }


def fetch_trends(
    client: DataForSEOClient,
    keywords: list[str],
    *,
    location_code: int,
    language_code: str,
    time_range: str = "past_12_months",
) -> pd.DataFrame:
    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for start in range(0, len(keywords), BATCH):
        batch = keywords[start:start + BATCH]
        try:
            data = client.google_trends_explore(
                batch, location_code, language_code, time_range=time_range
            )
        except CallBudgetExceeded:
            logger.warning("Call budget reached during trends fetch; stopping.")
            break
        for kw in batch:
            summary = _summarize(_series_for_keyword(data, kw))
            summary["keyword"] = kw
            summary["trend_checked_at"] = now
            rows.append(summary)
    return pd.DataFrame(rows, columns=TREND_COLUMNS) if rows else pd.DataFrame(columns=TREND_COLUMNS)
