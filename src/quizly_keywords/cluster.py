"""Keyword clustering: lexical (default) or semantic (optional).

Semantic mode embeds keywords and groups them with agglomerative clustering.
Embedding backend, in order of preference:
  1. sentence-transformers (if installed) — true semantic embeddings.
  2. scikit-learn TF-IDF char/word n-grams — lightweight fallback, no heavy deps.
Configured via config/scoring.yaml -> clustering.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)


def lexical_label(keyword: str, entity_terms: set[str]) -> str:
    kw = keyword.lower()
    for ent in sorted(entity_terms, key=len, reverse=True):
        if ent in kw:
            return ent
    toks = [t for t in re.findall(r"\w+", kw) if len(t) > 3]
    return toks[0] if toks else "misc"


def _embed(keywords: list[str], model_name: str):
    """Return an (n, d) embedding matrix, or None if no backend is available."""
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        return model.encode(keywords, normalize_embeddings=True)
    except ImportError:
        pass
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        return vec.fit_transform(keywords).toarray()
    except ImportError:
        logger.warning("Neither sentence-transformers nor scikit-learn available; "
                       "falling back to lexical clustering.")
        return None


def _label_cluster(members: list[str], volumes: list[float], entity_terms: set[str]) -> str:
    """Name a cluster after its dominant (highest-volume) member.

    If that representative keyword matches a known entity, use the entity name;
    otherwise use the keyword itself.
    """
    rep_idx = 0
    if volumes and any(v for v in volumes):
        rep_idx = max(range(len(members)), key=lambda i: volumes[i] or 0)
    rep = members[rep_idx]
    rl = rep.lower()
    for ent in sorted(entity_terms, key=len, reverse=True):
        if ent in rl:
            return ent
    return rep


def assign_clusters(
    df: pd.DataFrame,
    *,
    method: str,
    entity_terms: set[str],
    model_name: str = "all-MiniLM-L6-v2",
    max_clusters: int = 12,
) -> pd.Series:
    keywords = df["keyword"].astype(str).tolist()
    if method != "semantic" or len(keywords) < 3:
        return pd.Series([lexical_label(k, entity_terms) for k in keywords], index=df.index)

    embeddings = _embed(keywords, model_name)
    if embeddings is None:
        return pd.Series([lexical_label(k, entity_terms) for k in keywords], index=df.index)

    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError:
        logger.warning("scikit-learn missing; using lexical clustering.")
        return pd.Series([lexical_label(k, entity_terms) for k in keywords], index=df.index)

    n_clusters = max(2, min(max_clusters, len(keywords) // 3))
    labels = AgglomerativeClustering(n_clusters=n_clusters).fit_predict(embeddings)

    volumes = pd.to_numeric(df.get("search_volume"), errors="coerce").fillna(0).tolist()
    names: dict[int, str] = {}
    for cid in set(labels):
        idx = [i for i, l in enumerate(labels) if l == cid]
        names[cid] = _label_cluster([keywords[i] for i in idx], [volumes[i] for i in idx], entity_terms)
    return pd.Series([names[l] for l in labels], index=df.index)
