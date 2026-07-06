"""Stage 3: expand candidate terms into keyword ideas via DataForSEO Labs.

Selects the most promising candidate terms, calls the discovery endpoints, and
normalizes the varied response shapes into one flat table with provenance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .dataforseo_client import CallBudgetExceeded, DataForSEOClient
from .settings import Settings

logger = logging.getLogger(__name__)

DISCOVERED_COLUMNS = [
    "keyword", "source_term", "source_endpoint", "location_code", "language_code",
    "search_volume", "cpc", "competition", "competition_level",
    "keyword_difficulty", "categories", "collected_at",
]


def select_terms(candidates: pd.DataFrame, *, limit: int) -> pd.DataFrame:
    """Pick candidate terms worth spending API calls on.

    Priority: titles/book titles/authors/characters first, then by term_count.
    Drops near-duplicates by lowercased term.
    """
    if candidates.empty:
        return candidates
    priority = {
        "book_title": 0, "author": 1, "page_title": 2, "character": 3,
        "historical_person": 3, "heading": 4, "question_phrase": 5,
        "noun_phrase": 6, "site_keyword": 6,
    }
    df = candidates.copy()
    df["_prio"] = df["term_type"].map(priority).fillna(9)
    df["_lc"] = df["term"].str.lower().str.strip()
    df = df.sort_values(["_prio", "term_count"], ascending=[True, False])
    df = df.drop_duplicates("_lc", keep="first")
    return df.drop(columns=["_prio", "_lc"]).head(limit)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_from_labs_item(item: dict, *, source_term: str, endpoint: str,
                        location_code: int, language_code: str) -> dict | None:
    """DataForSEO Labs items nest metrics under keyword_data / keyword_info."""
    kw = item.get("keyword")
    kdata = item.get("keyword_data") or item
    info = (kdata.get("keyword_info") or {}) if isinstance(kdata, dict) else {}
    if kw is None:
        kw = kdata.get("keyword") if isinstance(kdata, dict) else None
    if not kw:
        return None
    kprops = kdata.get("keyword_properties") or {}
    return {
        "keyword": kw,
        "source_term": source_term,
        "source_endpoint": endpoint,
        "location_code": location_code,
        "language_code": language_code,
        "search_volume": info.get("search_volume"),
        "cpc": info.get("cpc"),
        "competition": info.get("competition"),
        "competition_level": info.get("competition_level"),
        "keyword_difficulty": kprops.get("keyword_difficulty"),
        "categories": "|".join(str(c) for c in (info.get("categories") or [])),
        "collected_at": _now(),
    }


def _rows_from_response(data: dict, *, source_term: str, endpoint: str,
                        location_code: int, language_code: str) -> list[dict]:
    rows: list[dict] = []
    for result in DataForSEOClient.extract_results(data):
        items = result.get("items") or []
        for item in items:
            row = _row_from_labs_item(
                item, source_term=source_term, endpoint=endpoint,
                location_code=location_code, language_code=language_code,
            )
            if row:
                rows.append(row)
    return rows


def discover(
    client: DataForSEOClient,
    terms: pd.DataFrame,
    *,
    location_code: int,
    language_code: str,
    settings: Settings,
    depth: int = 1,
    per_endpoint_limit: int = 300,
    run_keywords_for_site: bool = True,
) -> pd.DataFrame:
    rows: list[dict] = []
    term_list = terms["term"].tolist()

    for term in term_list:
        try:
            sug = client.keyword_suggestions(term, location_code, language_code, limit=per_endpoint_limit)
            rows += _rows_from_response(sug, source_term=term, endpoint="keyword_suggestions",
                                        location_code=location_code, language_code=language_code)
            rel = client.related_keywords(term, location_code, language_code, depth=depth,
                                          limit=per_endpoint_limit)
            rows += _rows_from_response(rel, source_term=term, endpoint="related_keywords",
                                        location_code=location_code, language_code=language_code)
        except CallBudgetExceeded:
            logger.warning("Call budget reached during discovery; stopping term expansion.")
            break

    # Keyword Ideas: batch the terms rather than one call each.
    if term_list:
        try:
            ideas = client.keyword_ideas(term_list[:200], location_code, language_code,
                                         limit=per_endpoint_limit)
            rows += _rows_from_response(ideas, source_term="<batch>", endpoint="keyword_ideas",
                                        location_code=location_code, language_code=language_code)
        except CallBudgetExceeded:
            logger.warning("Call budget reached before keyword_ideas.")

    # Keywords For Site (Source C).
    if run_keywords_for_site:
        targets = settings.sources_cfg.get("keywords_for_site_targets") or []
        for target in targets:
            try:
                site = client.keywords_for_site(target, location_code, language_code,
                                                limit=per_endpoint_limit)
                for result in DataForSEOClient.extract_results(site):
                    for item in result.get("items") or []:
                        info = item.get("keyword_info") or item
                        kw = item.get("keyword") or info.get("keyword")
                        if not kw:
                            continue
                        rows.append({
                            "keyword": kw, "source_term": f"site:{target}",
                            "source_endpoint": "keywords_for_site",
                            "location_code": location_code, "language_code": language_code,
                            "search_volume": info.get("search_volume"),
                            "cpc": info.get("cpc"), "competition": info.get("competition"),
                            "competition_level": info.get("competition_level"),
                            "keyword_difficulty": None,
                            "categories": "|".join(str(c) for c in (info.get("categories") or [])),
                            "collected_at": _now(),
                        })
            except CallBudgetExceeded:
                logger.warning("Call budget reached during keywords_for_site.")
                break

    df = pd.DataFrame(rows, columns=DISCOVERED_COLUMNS) if rows else pd.DataFrame(columns=DISCOVERED_COLUMNS)
    return df
