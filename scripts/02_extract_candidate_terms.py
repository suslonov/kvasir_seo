#!/usr/bin/env python3
"""Stage 2: extract candidate terms (with provenance) from Quizly sources."""
import argparse

import pandas as pd

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import storage, text_extract
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    frames = []

    try:
        pages = storage.read_table(storage.processed("quizly_pages.parquet"))
        frames.append(text_extract.extract_from_pages(pages))
        print(f"Pages: {len(pages)} rows")
    except FileNotFoundError:
        print("No quizly_pages found (run 01 first, or provide a DB export).")

    entities_csv = storage.processed("quizly_entities.csv")
    if entities_csv.exists():
        entities = pd.read_csv(entities_csv)
        frames.append(text_extract.extract_from_entities(entities))
        print(f"Entities: {len(entities)} rows")

    if not frames:
        print("No sources available; nothing to extract.")
        return 1

    candidates = pd.concat(frames, ignore_index=True)
    candidates = candidates.drop_duplicates(subset=["term", "term_type", "source_url"])
    out = storage.write_table(candidates, storage.processed("candidate_terms.csv"))
    print(f"Extracted {len(candidates)} candidate terms -> {out}")
    print(candidates["term_type"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
