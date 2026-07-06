"""Optional SERP phase: classify keyword intent from live Google SERP features.

For a shortlist of high-opportunity keywords, fetch the organic SERP and derive
an intent label from the element types present (people-also-ask / featured
snippet => informational, shopping => commercial, video => video, etc.). This is
one billable call per keyword, so it is run only on the top-N after scoring.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .dataforseo_client import CallBudgetExceeded, DataForSEOClient

logger = logging.getLogger(__name__)

SERP_COLUMNS = [
    "keyword", "serp_intent", "serp_features", "serp_top_domains", "serp_checked_at",
]

# Map SERP element types to an intent signal.
_INFORMATIONAL = {"people_also_ask", "featured_snippet", "answer_box", "knowledge_graph"}
_COMMERCIAL = {"shopping", "product_information", "commercial_units", "paid"}
_VIDEO = {"video", "youtube"}
_LOCAL = {"local_pack", "map", "hotels_pack"}


def _classify(feature_types: set[str]) -> str:
    if feature_types & _COMMERCIAL:
        return "commercial"
    if feature_types & _INFORMATIONAL:
        return "informational"
    if feature_types & _VIDEO:
        return "video"
    if feature_types & _LOCAL:
        return "local"
    return "navigational_or_mixed"


def _parse_serp(data: dict) -> tuple[set[str], list[str]]:
    feature_types: set[str] = set()
    domains: list[str] = []
    for result in DataForSEOClient.extract_results(data):
        for item in result.get("items") or []:
            itype = item.get("type")
            if itype:
                feature_types.add(itype)
            if itype == "organic" and item.get("domain"):
                domains.append(item["domain"])
    return feature_types, domains[:5]


def classify_intent(
    client: DataForSEOClient,
    keywords: list[str],
    *,
    location_code: int,
    language_code: str,
    depth: int = 10,
) -> pd.DataFrame:
    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for kw in keywords:
        try:
            data = client.serp_organic(kw, location_code, language_code, depth=depth)
        except CallBudgetExceeded:
            logger.warning("Call budget reached during SERP classification; stopping.")
            break
        features, domains = _parse_serp(data)
        rows.append({
            "keyword": kw,
            "serp_intent": _classify(features),
            "serp_features": "|".join(sorted(features)),
            "serp_top_domains": "|".join(domains),
            "serp_checked_at": now,
        })
    return pd.DataFrame(rows, columns=SERP_COLUMNS) if rows else pd.DataFrame(columns=SERP_COLUMNS)
