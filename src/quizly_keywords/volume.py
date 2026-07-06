"""Stage 4: enrich unique keywords with Google Ads Search Volume metrics.

Batches unique keywords (<=1000 per request) and merges monthly-search trends.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .dataforseo_client import CallBudgetExceeded, DataForSEOClient

logger = logging.getLogger(__name__)

METRIC_COLUMNS = [
    "keyword", "location_code", "language_code", "search_volume",
    "monthly_searches_json", "latest_month_searches", "trend_3m", "trend_12m",
    "cpc", "competition", "competition_index", "low_top_of_page_bid",
    "high_top_of_page_bid", "collected_at",
]

BATCH_SIZE = 1000


def _trend(monthly: list[dict], months: int) -> float | None:
    """Percent change of latest month vs the month `months` ago (0..)."""
    if not monthly or len(monthly) <= months:
        return None
    vals = [m.get("search_volume") or 0 for m in monthly]
    latest = vals[0] if vals else 0
    past = vals[months] if len(vals) > months else 0
    if not past:
        return None
    return round((latest - past) / past, 4)


def _row_from_item(item: dict, location_code: int, language_code: str) -> dict:
    monthly = item.get("monthly_searches") or []
    # DataForSEO returns newest-last; normalize to newest-first for trend math.
    monthly_sorted = sorted(
        monthly, key=lambda m: (m.get("year", 0), m.get("month", 0)), reverse=True
    )
    latest = monthly_sorted[0].get("search_volume") if monthly_sorted else None
    return {
        "keyword": item.get("keyword"),
        "location_code": location_code,
        "language_code": language_code,
        "search_volume": item.get("search_volume"),
        "monthly_searches_json": monthly_sorted,
        "latest_month_searches": latest,
        "trend_3m": _trend(monthly_sorted, 3),
        "trend_12m": _trend(monthly_sorted, 12),
        "cpc": item.get("cpc"),
        "competition": item.get("competition"),
        "competition_index": item.get("competition_index"),
        "low_top_of_page_bid": item.get("low_top_of_page_bid"),
        "high_top_of_page_bid": item.get("high_top_of_page_bid"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def enrich(
    client: DataForSEOClient,
    discovered: pd.DataFrame,
    *,
    location_code: int,
    language_code: str,
) -> pd.DataFrame:
    keywords = (
        discovered["keyword"].dropna().astype(str).str.strip()
        .loc[lambda s: s.str.len() > 0].drop_duplicates().tolist()
    )
    rows: list[dict] = []
    for start in range(0, len(keywords), BATCH_SIZE):
        batch = keywords[start:start + BATCH_SIZE]
        try:
            data = client.search_volume(batch, location_code, language_code)
        except CallBudgetExceeded:
            logger.warning("Call budget reached during search volume enrichment.")
            break
        for result in DataForSEOClient.extract_results(data):
            items = result.get("items") if isinstance(result, dict) and "items" in result else [result]
            for item in items or []:
                if item and item.get("keyword"):
                    rows.append(_row_from_item(item, location_code, language_code))
    df = pd.DataFrame(rows, columns=METRIC_COLUMNS) if rows else pd.DataFrame(columns=METRIC_COLUMNS)
    return df
