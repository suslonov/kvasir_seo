#!/usr/bin/env python3
"""Optional stage (Source E): Google Trends Explore for rising/relative interest.

Batches the top-N keywords (5 per call) and merges trend_direction / interest
back into keyword_master.
"""
import argparse

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import storage, trends
from quizly_keywords.dataforseo_client import DataForSEOClient
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", help="Market key, e.g. us-en")
    parser.add_argument("--top-n", type=int, default=50, help="How many top keywords to check")
    parser.add_argument("--time-range", default="past_12_months", help="Trends time range")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    market = settings.market(args.market)

    master = storage.read_table(storage.processed("keyword_master.parquet"))
    if "passes_filters" in master.columns:
        master = master.sort_values(["passes_filters", "opportunity_score"], ascending=[False, False])
    shortlist = master["keyword"].dropna().astype(str).head(args.top_n).tolist()
    print(f"Fetching Google Trends for {len(shortlist)} keywords in {market.name}")

    client = DataForSEOClient(settings)
    trend_df = trends.fetch_trends(
        client, shortlist,
        location_code=market.location_code, language_code=market.language_code,
        time_range=args.time_range,
    )
    storage.write_table(trend_df, storage.processed("google_trends.csv"))

    merged = master.drop(columns=[c for c in trend_df.columns if c != "keyword" and c in master.columns],
                         errors="ignore")
    merged = merged.merge(trend_df, on="keyword", how="left")
    out = storage.write_table(merged, storage.processed("keyword_master.parquet"))
    print(f"Merged Google Trends into {out} ({client.calls_made} API calls)")
    if "trend_direction" in trend_df.columns:
        print(trend_df["trend_direction"].value_counts(dropna=False).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
