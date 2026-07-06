# kvasir_seo

DataForSEO-driven keyword research pipeline for **quizly.pub**.

The system discovers candidate keywords from *real* Quizly sources (crawled pages
or a DB export), expands them through DataForSEO, enriches them with Google Ads
search-volume metrics, scores them for Quizly relevance + opportunity, and
produces an interactive HTML report. It does **not** guess keywords manually as
the primary source — manual seeds are debug-only.

See [dataforseo_quizly_keyword_plan.md](dataforseo_quizly_keyword_plan.md) for the
full design rationale.

## Layout

```
config/     locations, languages, sources, scoring (all tunable, no code edits)
src/quizly_keywords/  the library
scripts/    00..06 pipeline stages
data/        raw/ (JSONL API dumps), processed/ (parquet/csv)  — gitignored
outputs/     HTML report + CSV exports                          — gitignored
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit with your DataForSEO login/password
```

`sentence-transformers` is commented out in `requirements.txt`; the pipeline
clusters lexically without it. Install it only if you want semantic clustering.

## Pipeline

```bash
python scripts/00_check_credentials.py                       # validate auth (needs .env)
python scripts/01_collect_quizly_pages.py                    # crawl quizly.pub (Source A)
python scripts/02_extract_candidate_terms.py                 # deterministic term extraction
python scripts/03_discover_keywords.py --market us-en --limit-terms 100   # DataForSEO Labs
python scripts/04_enrich_search_volume.py --market us-en     # Google Ads Search Volume
python scripts/05_score_keywords.py                          # dedupe + relevance + opportunity
python scripts/06_visualize.py                               # HTML report + CSVs
xdg-open outputs/keyword_opportunities.html
```

Stages 03 and 04 call the paid API and need credentials. Stages 01, 02, 05, 06
run offline (05/06 need the discovery output). A `Keywords For Site` run and a DB
export can substitute for crawling.

### Optional stages

```bash
python scripts/07_serp_intent.py   --market us-en --top-n 25   # live SERP intent for top keywords
python scripts/08_google_trends.py --market us-en --top-n 50   # Google Trends rising/falling
python scripts/06_visualize.py                                 # re-run to include the new columns
```

- **07 – SERP intent** (SERP API): fetches the live Google SERP for the top-N
  scored keywords and derives an intent label from SERP features
  (people-also-ask/featured-snippet → informational, shopping → commercial,
  video → video, …). One billable call per keyword, so it is capped by `--top-n`.
  Adds a `serp_intent` column.
- **08 – Google Trends** (Source E): relative interest + a rising/flat/falling
  signal for the top-N keywords (5 per call). Adds a `trend_direction` column.

Both merge back into `keyword_master` and surface in the report when present.

### Semantic clustering

`config/scoring.yaml → clustering.method` is `lexical` by default. Set it to
`semantic` to group keywords by meaning. The embedding backend is chosen
automatically:

1. `sentence-transformers` if installed (uncomment it in `requirements.txt`) —
   true semantic embeddings;
2. otherwise a scikit-learn TF-IDF fallback — lighter, no extra download.

Either way clusters are named after each group's highest-volume keyword.

### Markets

Markets are defined in [config/locations.yaml](config/locations.yaml) and selected
with `--market` (e.g. `us-en`, `ru-ru`, `il-en`). **Verify DataForSEO location/
language codes against their docs before production runs.**

### Cost control

- Start on the **sandbox** (`DATAFORSEO_BASE_URL=https://sandbox.dataforseo.com`),
  switch to `https://api.dataforseo.com` only after `00_check_credentials.py` passes.
- `MAX_API_CALLS_PER_RUN` in `.env` is a hard ceiling; discovery/enrichment stop
  gracefully when it is hit.
- `--limit-terms`, `--depth`, and `--no-site` bound spend on stage 03.
- Raw responses are cached under `data/raw/` for provenance and re-use.

## Try it offline

Generate synthetic Quizly pages and run the offline stages end to end (no API,
no network):

```bash
python scripts/dev_sample_data.py     # writes sample data/processed inputs
python scripts/02_extract_candidate_terms.py
python scripts/05_score_keywords.py
python scripts/06_visualize.py
```

## Status

Scaffolding and full pipeline code are complete. What still needs a human:

1. Create a DataForSEO account and put credentials in `.env`.
2. Confirm the crawl targets / provide a Quizly DB export (`config/sources.yaml`).
3. Verify location/language codes and current endpoint pricing.
4. Run sandbox → small production run → scale.
