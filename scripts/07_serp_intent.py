#!/usr/bin/env python3
"""Optional stage: classify intent from live Google SERPs for top keywords.

One billable SERP call per keyword, so it runs only on the top-N by opportunity.
Merges serp_intent / serp_features back into keyword_master.
"""
import argparse

import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords import serp, storage
from quizly_keywords.dataforseo_client import DataForSEOClient
from quizly_keywords.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", help="Market key, e.g. us-en")
    parser.add_argument("--top-n", type=int, default=25, help="How many top keywords to check")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    market = settings.market(args.market)

    master = storage.read_table(storage.processed("keyword_master.parquet"))
    if "passes_filters" in master.columns:
        master = master.sort_values(["passes_filters", "opportunity_score"], ascending=[False, False])
    shortlist = master["keyword"].dropna().astype(str).head(args.top_n).tolist()
    print(f"Checking SERP intent for {len(shortlist)} keywords in {market.name}")

    client = DataForSEOClient(settings)
    serp_df = serp.classify_intent(
        client, shortlist,
        location_code=market.location_code, language_code=market.language_code,
    )
    storage.write_table(serp_df, storage.processed("serp_intent.csv"))

    merged = master.drop(columns=[c for c in ("serp_intent", "serp_features", "serp_top_domains")
                                  if c in master.columns], errors="ignore")
    merged = merged.merge(serp_df, on="keyword", how="left")
    out = storage.write_table(merged, storage.processed("keyword_master.parquet"))
    print(f"Merged SERP intent into {out} ({client.calls_made} API calls)")
    print(serp_df["serp_intent"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
