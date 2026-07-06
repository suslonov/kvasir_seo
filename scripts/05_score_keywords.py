#!/usr/bin/env python3
"""Stage 5: normalize/dedupe, then score relevance + opportunity + action."""
import argparse

import pandas as pd

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import normalize, scoring, storage
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", help="Market key (informational; scoring is language-aware)")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()

    discovered = storage.read_table(storage.processed("discovered_keywords.parquet"))

    metrics = pd.DataFrame()
    metrics_path = storage.processed("keyword_metrics.parquet")
    try:
        metrics = storage.read_table(metrics_path)
    except FileNotFoundError:
        print("No keyword_metrics found; scoring on discovery metrics only.")

    candidates = None
    try:
        candidates = storage.read_table(storage.processed("candidate_terms.csv"))
    except FileNotFoundError:
        pass

    master = normalize.merge(discovered, metrics)
    master = master.rename(columns={"keyword_normalized": "keyword_normalized"})
    if "language_code" not in master.columns:
        master["language_code"] = settings.default_language_code
    scored = scoring.score(master, settings, candidates)

    out = storage.write_table(scored, storage.processed("keyword_master.parquet"))
    passed = int(scored["passes_filters"].sum()) if "passes_filters" in scored.columns else len(scored)
    print(f"Scored {len(scored)} keywords ({passed} pass filters) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
