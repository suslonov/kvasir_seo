#!/usr/bin/env python3
"""Stage 4: enrich discovered keywords with Google Ads Search Volume metrics."""
import argparse

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import storage, volume
from quizly_keywords.dataforseo_client import DataForSEOClient
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", help="Market key, e.g. us-en")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    market = settings.market(args.market)

    discovered = storage.read_table(storage.processed("discovered_keywords.parquet"))
    client = DataForSEOClient(settings)
    metrics = volume.enrich(
        client, discovered,
        location_code=market.location_code, language_code=market.language_code,
    )
    out = storage.write_table(metrics, storage.processed("keyword_metrics.parquet"))
    print(f"Enriched {len(metrics)} keywords ({client.calls_made} API calls) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
