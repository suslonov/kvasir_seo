#!/usr/bin/env python3
"""Write synthetic Quizly pages + discovered keywords for offline testing.

Lets you run stages 02, 05, 06 without hitting the network or the DataForSEO API.
"""
from datetime import datetime, timezone

import pandas as pd

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import storage
from quizly_keywords.settings import load_settings

NOW = datetime.now(timezone.utc).isoformat()

SAMPLE_PAGES = [
    {
        "url": "https://quizly.pub/contest?id=1", "lang": "en",
        "title": "Hamlet quiz — test yourself on Shakespeare's tragedy",
        "meta_description": "A quiz about Prince Hamlet, Ophelia and the tragedy of Hamlet by William Shakespeare.",
        "h1": "Hamlet Quiz", "h2": "Prince Hamlet | Ophelia", "h3": "",
        "body_text": "Prince Hamlet is the protagonist. \"Hamlet\" is a tragedy by William Shakespeare. "
                     "Why did Hamlet delay his revenge? Who killed King Hamlet?",
        "content_type": "contest", "course_id": "1", "reading_id": "", "echo_id": "",
        "internal_links": "https://quizly.pub/contest?id=2", "created_at": NOW,
    },
    {
        "url": "https://quizly.pub/contest?id=2", "lang": "en",
        "title": "Chat with Sherlock Holmes",
        "meta_description": "Have a conversation with the character Sherlock Holmes from Arthur Conan Doyle's stories.",
        "h1": "Sherlock Holmes chat", "h2": "Detective conversation", "h3": "",
        "body_text": "Sherlock Holmes is a detective created by Arthur Conan Doyle. "
                     "How does Sherlock Holmes solve mysteries? What is deduction?",
        "content_type": "contest", "course_id": "2", "reading_id": "", "echo_id": "",
        "internal_links": "", "created_at": NOW,
    },
    {
        "url": "https://quizly.pub/read?id=5", "lang": "en",
        "title": "The Great Gatsby summary and characters",
        "meta_description": "Summary of The Great Gatsby by F. Scott Fitzgerald with main characters explained.",
        "h1": "The Great Gatsby", "h2": "Jay Gatsby | Daisy Buchanan", "h3": "Summary",
        "body_text": "\"The Great Gatsby\" is a novel by F. Scott Fitzgerald. Jay Gatsby loves Daisy Buchanan. "
                     "What is the meaning of the green light? Explain the ending of The Great Gatsby.",
        "content_type": "reading", "course_id": "", "reading_id": "5", "echo_id": "",
        "internal_links": "", "created_at": NOW,
    },
]

# A stand-in for a DataForSEO discovery response (Stage 3 output).
SAMPLE_DISCOVERED = [
    ("hamlet quiz", "Hamlet Quiz", "keyword_suggestions", 2840, "en", 2400, 0.12, 0.18, "LOW"),
    ("hamlet summary", "Hamlet", "related_keywords", 2840, "en", 8100, 0.05, 0.09, "LOW"),
    ("why did hamlet delay revenge", "Hamlet", "keyword_suggestions", 2840, "en", 320, 0.02, 0.04, "LOW"),
    ("sherlock holmes chat", "Sherlock Holmes", "keyword_suggestions", 2840, "en", 590, 0.20, 0.30, "LOW"),
    ("sherlock holmes deduction", "Sherlock Holmes", "related_keywords", 2840, "en", 480, 0.10, 0.22, "LOW"),
    ("the great gatsby summary", "The Great Gatsby", "keyword_suggestions", 2840, "en", 40500, 0.30, 0.45, "MEDIUM"),
    ("great gatsby characters", "The Great Gatsby", "related_keywords", 2840, "en", 12100, 0.25, 0.35, "MEDIUM"),
    ("buy the great gatsby cheap", "The Great Gatsby", "keyword_ideas", 2840, "en", 1600, 0.80, 0.95, "HIGH"),
    ("great gatsby free pdf download", "The Great Gatsby", "keyword_ideas", 2840, "en", 5400, 0.70, 0.88, "HIGH"),
    ("quiz games online", "site:quizly.pub", "keywords_for_site", 2840, "en", 27100, 0.55, 0.60, "MEDIUM"),
]

DISCOVERED_COLS = [
    "keyword", "source_term", "source_endpoint", "location_code", "language_code",
    "search_volume", "cpc", "competition", "competition_level",
]


def main() -> int:
    settings = load_settings()
    settings.ensure_dirs()

    pages = pd.DataFrame(SAMPLE_PAGES)
    p = storage.write_table(pages, storage.processed("quizly_pages.parquet"))
    print(f"Wrote {len(pages)} sample pages -> {p}")

    disc = pd.DataFrame(SAMPLE_DISCOVERED, columns=DISCOVERED_COLS)
    disc["keyword_difficulty"] = None
    disc["categories"] = ""
    disc["collected_at"] = NOW
    d = storage.write_table(disc, storage.processed("discovered_keywords.parquet"))
    print(f"Wrote {len(disc)} sample discovered keywords -> {d}")
    print("\nNow run: 02_extract_candidate_terms.py, 05_score_keywords.py, 06_visualize.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
