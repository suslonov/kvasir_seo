"""Deterministic candidate-term extraction from Quizly page/entity text.

No LLM invention of seed keywords: terms come from titles, headings, capitalized
entity spans, quoted titles, question-like phrases, and repeated noun-ish phrases.
Every emitted term carries provenance (source url/entity + extraction method).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

CANDIDATE_COLUMNS = [
    "term", "source_url", "source_entity_type", "source_entity_id", "lang",
    "term_type", "term_count", "source_title", "extraction_method",
]

# Sequence of Capitalized words -> likely a proper noun / title / character.
_ENTITY_RE = re.compile(r"\b([A-Z][\w'’]+(?:\s+(?:of|the|and|de|van|von)?\s*[A-Z][\w'’]+){0,4})\b")
# Text inside quotes -> likely a book/work title.
_QUOTED_RE = re.compile(r"[\"“«]([^\"”»]{3,80})[\"”»]")
_QUESTION_RE = re.compile(
    r"\b((?:why|how|who|what|when|where|did|is|was|почему|как|кто|что|когда|где)\b[^.?!]{5,80}\??)",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[\w'’]+", re.UNICODE)


@dataclass
class Term:
    term: str
    source_url: str = ""
    source_entity_type: str = ""
    source_entity_id: str = ""
    lang: str = ""
    term_type: str = ""
    term_count: int = 1
    source_title: str = ""
    extraction_method: str = ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _dedupe_keep_max(terms: list[Term]) -> list[Term]:
    """Collapse identical (lowercased) terms, summing counts, keeping richest row."""
    best: dict[tuple[str, str], Term] = {}
    for t in terms:
        key = (t.term.lower(), t.term_type)
        if key in best:
            best[key].term_count += t.term_count
        else:
            best[key] = t
    return list(best.values())


def extract_from_text(
    text: str,
    *,
    lang: str = "",
    source_url: str = "",
    source_title: str = "",
    entity_type: str = "",
    entity_id: str = "",
    min_len: int = 3,
) -> list[Term]:
    text = _clean(text)
    out: list[Term] = []

    def add(term: str, term_type: str, method: str) -> None:
        term = _clean(term)
        if len(term) < min_len or len(term) > 90:
            return
        out.append(
            Term(
                term=term, source_url=source_url, source_entity_type=entity_type,
                source_entity_id=str(entity_id), lang=lang, term_type=term_type,
                source_title=source_title, extraction_method=method,
            )
        )

    for m in _QUOTED_RE.finditer(text):
        add(m.group(1), "book_title", "quoted_span")
    for m in _QUESTION_RE.finditer(text):
        add(m.group(1), "question_phrase", "question_regex")
    entity_counts = Counter(m.group(1) for m in _ENTITY_RE.finditer(text))
    for ent, cnt in entity_counts.items():
        # Skip single very short tokens that are just sentence starts.
        if len(ent.split()) == 1 and len(ent) < 4:
            continue
        t = Term(
            term=ent, source_url=source_url, source_entity_type=entity_type,
            source_entity_id=str(entity_id), lang=lang, term_type="character",
            term_count=cnt, source_title=source_title, extraction_method="capitalized_span",
        )
        out.append(t)
    return out


def extract_from_pages(pages: pd.DataFrame) -> pd.DataFrame:
    terms: list[Term] = []
    for _, row in pages.iterrows():
        lang = str(row.get("lang", "") or "")[:2]
        url = str(row.get("url", "") or "")
        title = str(row.get("title", "") or "")
        etype = str(row.get("content_type", "") or "")
        # Titles and headings are high-signal.
        if title:
            terms.append(Term(term=title, source_url=url, lang=lang, term_type="page_title",
                              source_title=title, extraction_method="title", source_entity_type=etype))
        for col, ttype in (("h1", "heading"), ("h2", "heading"), ("h3", "heading")):
            val = str(row.get(col, "") or "")
            for part in val.split(" | "):
                part = part.strip()
                if part:
                    terms.append(Term(term=part, source_url=url, lang=lang, term_type=ttype,
                                      source_title=title, extraction_method=col,
                                      source_entity_type=etype))
        body = " ".join(str(row.get(c, "") or "") for c in ("meta_description", "body_text"))
        terms.extend(
            extract_from_text(
                body, lang=lang, source_url=url, source_title=title,
                entity_type=etype,
            )
        )
    terms = _dedupe_keep_max(terms)
    rows = [t.__dict__ for t in terms]
    df = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS) if rows else pd.DataFrame(columns=CANDIDATE_COLUMNS)
    return df


def extract_from_entities(entities: pd.DataFrame) -> pd.DataFrame:
    """Extract candidate terms from a Quizly DB export (Source B)."""
    terms: list[Term] = []
    for _, row in entities.iterrows():
        lang = str(row.get("lang", "") or "")[:2]
        etype = str(row.get("entity_type", "") or "")
        eid = str(row.get("entity_id", "") or "")
        url = str(row.get("public_url", "") or "")
        for col, ttype in (
            ("title", "page_title"),
            ("base_text_title", "book_title"),
            ("base_text_author", "author"),
            ("contest_title", "page_title"),
        ):
            val = _clean(str(row.get(col, "") or ""))
            if val:
                terms.append(Term(term=val, source_url=url, source_entity_type=etype,
                                  source_entity_id=eid, lang=lang, term_type=ttype,
                                  source_title=str(row.get("title", "") or ""),
                                  extraction_method=f"db:{col}"))
        desc = _clean(str(row.get("description", "") or ""))
        if desc:
            terms.extend(extract_from_text(desc, lang=lang, source_url=url,
                                           entity_type=etype, entity_id=eid))
    terms = _dedupe_keep_max(terms)
    rows = [t.__dict__ for t in terms]
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS) if rows else pd.DataFrame(columns=CANDIDATE_COLUMNS)
