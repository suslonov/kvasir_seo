"""Stage 5b: relevance, intent, clustering, opportunity score, and action.

All weights/thresholds come from config/scoring.yaml and config/languages.yaml,
so behavior is tunable without code edits.
"""
from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

from . import cluster
from .settings import Settings


def _lang_signals(settings: Settings, lang: str) -> dict[str, list[str]]:
    langs = settings.languages_cfg.get("languages", {})
    cfg = langs.get(lang) or langs.get("en") or {}
    return {
        "question_words": [w.lower() for w in cfg.get("question_words", [])],
        "intent_signals": [w.lower() for w in cfg.get("intent_signals", [])],
    }


def _entity_terms(candidates: pd.DataFrame) -> set[str]:
    """Known Quizly entities used for relevance/content-availability matching."""
    if candidates is None or candidates.empty:
        return set()
    mask = candidates["term_type"].isin(
        ["book_title", "author", "character", "historical_person", "page_title"]
    )
    terms = candidates.loc[mask, "term"].dropna().astype(str)
    return {t.lower().strip() for t in terms if len(t.strip()) >= 3}


def _log_scaled_volume(vol: float | None, vmax: float) -> float:
    if not vol or vol <= 0 or vmax <= 0:
        return 0.0
    return math.log1p(vol) / math.log1p(vmax)


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def _question_intent(keyword: str, signals: dict[str, list[str]]) -> float:
    kw = keyword.lower()
    tokens = re.findall(r"\w+", kw)
    score = 0.0
    if tokens and tokens[0] in signals["question_words"]:
        score += 0.6
    elif _matches_any(kw, signals["question_words"]):
        score += 0.3
    if _matches_any(kw, signals["intent_signals"]):
        score += 0.4
    return min(score, 1.0)


def _relevance(keyword: str, entity_terms: set[str], signals: dict[str, list[str]]) -> tuple[float, bool]:
    kw = keyword.lower()
    entity_hit = any(ent in kw for ent in entity_terms) if entity_terms else False
    score = 0.0
    if entity_hit:
        score += 0.6
    if _matches_any(kw, signals["intent_signals"]):
        score += 0.3
    if _matches_any(kw, signals["question_words"]):
        score += 0.1
    return min(score, 1.0), entity_hit


def _intent_label(keyword: str, signals: dict[str, list[str]]) -> str:
    kw = keyword.lower()
    if _matches_any(kw, ["quiz", "test", "викторина", "тест"]):
        return "quiz_game"
    if _matches_any(kw, ["chat", "conversation", "разговор", "character", "персонаж"]):
        return "chat_character"
    if _matches_any(kw, ["summary", "explained", "analysis", "краткое", "анализ", "содержание"]):
        return "educational"
    if tokens_first_is_question(kw, signals):
        return "informational"
    if _matches_any(kw, ["buy", "price", "cheap", "download", "купить", "скачать"]):
        return "commercial"
    return "other"


def tokens_first_is_question(kw: str, signals: dict[str, list[str]]) -> bool:
    toks = re.findall(r"\w+", kw)
    return bool(toks) and toks[0] in signals["question_words"]


def _negative_penalty(keyword: str, scoring_cfg: dict[str, Any]) -> tuple[float, bool]:
    """Return (multiplier, dropped). dropped=True means drop entirely."""
    kw = keyword.lower()
    neg = scoring_cfg.get("negative_filters", {})
    patterns = scoring_cfg.get("negative_patterns", {})
    for cat, enabled in neg.items():
        if not enabled:
            continue
        pats = patterns.get(cat, [])
        if _matches_any(kw, pats):
            # Adult/piracy => drop; commercial/political => heavy downrank.
            if cat in ("adult", "piracy"):
                return 0.0, True
            return 0.3, False
    return 1.0, False


def _choose_action(row: dict, scoring_cfg: dict[str, Any]) -> str:
    ctx = {
        "opportunity_score": row["opportunity_score"],
        "relevance_score": row["relevance_score"],
        "question_intent_score": row["question_intent_score"],
        "search_volume": row.get("search_volume") or 0,
        "content_available": row["content_available"],
        "True": True,
        "False": False,
    }
    for rule in scoring_cfg.get("actions", []):
        expr = rule.get("when", "False")
        try:
            if eval(expr, {"__builtins__": {}}, ctx):  # noqa: S307 - trusted config
                return rule["action"]
        except Exception:
            continue
    return "monitor_only"


def score(
    master: pd.DataFrame,
    settings: Settings,
    candidates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    scoring_cfg = settings.scoring_cfg
    weights = scoring_cfg.get("weights", {})
    filters = scoring_cfg.get("filters", {})
    entity_terms = _entity_terms(candidates) if candidates is not None else set()

    if master.empty:
        for col in ("relevance_score", "question_intent_score", "opportunity_score",
                    "intent_label", "cluster_label", "recommended_action", "content_available"):
            master[col] = []
        return master

    df = master.copy()
    df["search_volume"] = pd.to_numeric(df.get("search_volume"), errors="coerce")
    df["competition"] = pd.to_numeric(df.get("competition"), errors="coerce")
    df["trend_3m"] = pd.to_numeric(df.get("trend_3m"), errors="coerce")
    vmax = float(df["search_volume"].max() or 0)

    records = []
    for _, r in df.iterrows():
        keyword = str(r.get("keyword", "") or "")
        lang = str(r.get("language_code", settings.default_language_code) or "en")[:2]
        signals = _lang_signals(settings, lang)

        rel, entity_hit = _relevance(keyword, entity_terms, signals)
        qintent = _question_intent(keyword, signals)
        vol = r["search_volume"] if pd.notna(r["search_volume"]) else 0
        comp = r["competition"] if pd.notna(r["competition"]) else 0.0
        trend = r["trend_3m"] if pd.notna(r["trend_3m"]) else 0.0

        vol_score = _log_scaled_volume(vol, vmax)
        comp_score = 1.0 - min(max(comp, 0.0), 1.0)
        trend_score = max(min((trend or 0.0), 1.0), 0.0)

        opp = (
            weights.get("search_volume_log", 0.35) * vol_score
            + weights.get("low_competition", 0.20) * comp_score
            + weights.get("trend_growth", 0.15) * trend_score
            + weights.get("relevance_to_quizly", 0.20) * rel
            + weights.get("question_intent", 0.10) * qintent
        )
        mult, dropped = _negative_penalty(keyword, scoring_cfg)
        opp *= mult

        rec = r.to_dict()
        rec.update({
            "relevance_score": round(rel, 4),
            "question_intent_score": round(qintent, 4),
            "opportunity_score": round(opp, 4),
            "intent_label": _intent_label(keyword, signals),
            "cluster_label": cluster.lexical_label(keyword, entity_terms),
            "content_available": bool(entity_hit),
            "_dropped": dropped,
        })
        rec["recommended_action"] = "ignore_irrelevant" if dropped else _choose_action(rec, scoring_cfg)
        records.append(rec)

    out = pd.DataFrame(records)

    # Optional semantic clustering overrides the lexical cluster_label.
    clustering_cfg = scoring_cfg.get("clustering", {}) or {}
    if clustering_cfg.get("method") == "semantic":
        out["cluster_label"] = cluster.assign_clusters(
            out,
            method="semantic",
            entity_terms=entity_terms,
            model_name=clustering_cfg.get("model", "all-MiniLM-L6-v2"),
            max_clusters=int(clustering_cfg.get("max_clusters", 12)),
        )

    # Apply hard filters (keep dropped rows labeled but sorted to the bottom).
    min_vol = filters.get("min_search_volume", 0)
    max_comp = filters.get("max_competition", 1.0)
    out["passes_filters"] = (
        (out["search_volume"].fillna(0) >= min_vol)
        & (out["competition"].fillna(0) <= max_comp)
        & (~out["_dropped"])
    )
    out = out.drop(columns=["_dropped"])
    out = out.sort_values(["passes_filters", "opportunity_score"], ascending=[False, False])
    return out.reset_index(drop=True)
