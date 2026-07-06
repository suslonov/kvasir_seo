#!/usr/bin/env python3
"""Stage 3: expand candidate terms into keyword ideas via DataForSEO Labs."""
import argparse

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import discovery, storage
from quizly_keywords.dataforseo_client import DataForSEOClient
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", help="Market key, e.g. us-en (see config/locations.yaml)")
    parser.add_argument("--limit-terms", type=int, default=100, help="Max candidate terms to expand")
    parser.add_argument("--depth", type=int, default=1, help="Related-keywords depth")
    parser.add_argument("--no-site", action="store_true", help="Skip Keywords For Site")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    market = settings.market(args.market)

    candidates = storage.read_table(storage.processed("candidate_terms.csv"))
    selected = discovery.select_terms(candidates, limit=args.limit_terms)
    print(f"Selected {len(selected)} of {len(candidates)} candidate terms for {market.name}")

    client = DataForSEOClient(settings)
    discovered = discovery.discover(
        client, selected,
        location_code=market.location_code, language_code=market.language_code,
        settings=settings, depth=args.depth, run_keywords_for_site=not args.no_site,
    )
    out = storage.write_table(discovered, storage.processed("discovered_keywords.parquet"))
    print(f"Discovered {len(discovered)} keyword rows ({client.calls_made} API calls) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
