#!/usr/bin/env python3
"""Stage 6: build the HTML report and CSV exports from the scored master."""
import argparse

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import storage, visualize
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", help="Market key, used for the report title only")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    market_name = settings.market(args.market).name if args.market else ""

    scored = storage.read_table(storage.processed("keyword_master.parquet"))
    paths = visualize.build_report(scored, market_name=market_name)
    print("Report written:")
    for label, path in paths.items():
        print(f"  {label}: {path}")
    print(f"\nOpen: xdg-open {paths['html']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
