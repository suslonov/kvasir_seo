#!/usr/bin/env python3
"""Stage 1: crawl quizly.pub public pages and/or ingest a DB export."""
import argparse

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import quizly_site, storage
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-crawl", action="store_true", help="Skip crawling (use DB export only)")
    parser.add_argument("--db-export", help="Path to a Quizly DB export CSV (Source B)")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()

    if not args.no_crawl:
        crawler = quizly_site.QuizlyCrawler(settings)
        pages = crawler.crawl()
        out = storage.write_table(pages, storage.processed("quizly_pages.parquet"))
        print(f"Crawled {len(pages)} pages -> {out}")

    db_path = args.db_export or (settings.sources_cfg.get("db_export") or {}).get("path")
    if db_path:
        entities = quizly_site.ingest_db_export(db_path)
        out = storage.write_table(entities, storage.processed("quizly_entities.csv"))
        print(f"Ingested {len(entities)} entities -> {out}")
    else:
        print("No DB export configured (Source B skipped).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
