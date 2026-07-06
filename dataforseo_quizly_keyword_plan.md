# DataForSEO Keyword Research Plan for quizly.pub

## Goal

Build a small standalone repository, similar in spirit to `kvasir_marketing`, that connects to DataForSEO, collects relevant Google keyword data for `quizly.pub`, stores raw and normalized results, ranks opportunities, and visualizes them.

The key constraint is: **do not guess keywords manually as the primary source**. The system should discover candidate keywords from Quizly pages, page text, DataForSEO site/category endpoints, Google SERP-related keyword endpoints, and optional seed extraction from existing public content. Manual seeds may be allowed only as debugging or override input, not as the main pipeline.

---

## What DataForSEO can provide

Relevant DataForSEO API families:

1. **DataForSEO Labs API**
   - Keyword Ideas
   - Keyword Suggestions
   - Related Keywords
   - SERP/keyword metrics
   - Best for keyword discovery and expansion.

2. **Google Ads Keywords Data API**
   - Search Volume
   - Keywords For Site
   - Keywords For Keywords
   - Ad Traffic By Keywords
   - Google Trends Explore
   - Best for search volume, CPC, competition, and trend metrics.

3. **SERP API**
   - Optional later phase.
   - Can check actual Google SERP composition for selected keywords.
   - Useful to classify intent: informational, commercial, navigational, AI/chat, quiz/game, book/literature, history, education.

Important DataForSEO facts to account for:

- API v3 uses Basic Authentication with API login and password in request headers.
- DataForSEO recommends testing against `sandbox.dataforseo.com` before production.
- Google Ads Search Volume endpoint can process up to 1,000 keywords per request/task.
- Related Keywords endpoint can return up to thousands of related keyword ideas depending on depth.
- Keyword Suggestions returns queries containing the supplied keyword or phrase; useful after the system extracts terms from real site/content data.
- Keyword Ideas returns relevant terms by category; useful after the system has reliable seed terms or category anchors.

References:

- DataForSEO API auth: https://docs.dataforseo.com/v3/auth/
- DataForSEO Labs Related Keywords: https://docs.dataforseo.com/v3/dataforseo_labs-google-related_keywords-live/
- DataForSEO Labs Keyword Suggestions: https://docs.dataforseo.com/v3/dataforseo_labs-google-keyword_suggestions-live/
- DataForSEO Labs Keyword Ideas: https://docs.dataforseo.com/v3/dataforseo_labs-google-keyword_ideas-live/
- Google Ads Search Volume: https://docs.dataforseo.com/v3/keyword_data-google_ads-search_volume-task_post/
- Keywords Data API overview: https://docs.dataforseo.com/v3/keywords-data-overview/

---

## Repository proposal

Repository name:

```text
kvasir_seo
```

Alternative if you want to keep it under marketing:

```text
kvasir_marketing/keyword_research
```

Recommended standalone structure:

```text
kvasir_seo/
  README.md
  .env.example
  .gitignore
  requirements.txt
  pyproject.toml                 # optional, if using uv/poetry
  config/
    locations.yaml
    languages.yaml
    sources.yaml
    scoring.yaml
  data/
    raw/                         # raw DataForSEO responses, jsonl
    processed/                   # normalized parquet/csv
    reports/                     # generated csv/html reports
  notebooks/
    exploration.ipynb            # optional
  scripts/
    00_check_credentials.py
    01_collect_quizly_pages.py
    02_extract_candidate_terms.py
    03_discover_keywords.py
    04_enrich_search_volume.py
    05_score_keywords.py
    06_visualize.py
  src/
    quizly_keywords/
      __init__.py
      settings.py
      dataforseo_client.py
      quizly_site.py
      text_extract.py
      discovery.py
      volume.py
      normalize.py
      scoring.py
      visualize.py
      storage.py
  outputs/
    keyword_opportunities.html
    keyword_opportunities.csv
    keyword_clusters.csv
    charts/
      volume_vs_competition.html
      trend_heatmap.html
      keyword_clusters.html
```

---

## Setup instructions for you

### 1. Create DataForSEO account

1. Register at DataForSEO.
2. Open API dashboard.
3. Find your API login and API password.
4. Add a small balance for production testing only after sandbox tests pass.
5. Check current pricing for:
   - DataForSEO Labs endpoints
   - Google Ads Search Volume endpoint
   - SERP API, if enabled later

### 2. Create repository

```bash
mkdir kvasir_seo
cd kvasir_seo
git init
```

### 3. Create Python environment

Option A: simple venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

Option B: uv

```bash
uv venv
source .venv/bin/activate
```

### 4. Install dependencies

`requirements.txt`:

```text
requests
python-dotenv
pydantic
pandas
pyarrow
beautifulsoup4
lxml
trafilatura
pyyaml
plotly
scikit-learn
sentence-transformers
rich
```

Install:

```bash
pip install -r requirements.txt
```

Notes:

- `sentence-transformers` is optional but useful for clustering keywords semantically.
- If you want lighter setup, skip it initially and cluster by lexical rules.
- `plotly` is recommended for interactive visualization.

### 5. Create `.env`

`.env.example`:

```bash
DATAFORSEO_LOGIN=your_dataforseo_login
DATAFORSEO_PASSWORD=your_dataforseo_password
DATAFORSEO_BASE_URL=https://sandbox.dataforseo.com

QUIZLY_BASE_URL=https://quizly.pub
DEFAULT_LOCATION_CODE=2376
DEFAULT_LANGUAGE_CODE=en
DEFAULT_LIMIT=1000
```

Create local `.env`:

```bash
cp .env.example .env
```

Then edit `.env`.

Important:

- Commit `.env.example`.
- Never commit `.env`.
- Add `.env` to `.gitignore`.

`.gitignore`:

```text
.env
.venv/
__pycache__/
.ipynb_checkpoints/
data/raw/
data/processed/
outputs/
*.pyc
```

### 6. Validate credentials

Run:

```bash
python scripts/00_check_credentials.py
```

Expected result:

```text
DataForSEO auth OK
Base URL: https://sandbox.dataforseo.com
```

Only after this works, switch:

```bash
DATAFORSEO_BASE_URL=https://api.dataforseo.com
```

---

## No-guessing keyword discovery strategy

The pipeline should discover keywords from real sources instead of inventing them.

### Source A: quizly.pub public pages

Collect public URLs from:

1. `https://quizly.pub/`
2. Contest pages, for example:
   - `/contest?id=1`
   - `/contest?id=2`
3. Reading pages available from your DB or sitemap-like source.
4. Echo info pages.
5. Public chat/game pages.
6. Any public landing pages.

The crawler should extract:

- page title
- H1/H2/H3 headings
- meta description
- visible body text
- canonical URL
- language
- internal links
- contest/book/chat identifiers

Output:

```text
data/processed/quizly_pages.parquet
```

Columns:

```text
url
lang
title
meta_description
h1
h2
body_text
content_type
course_id
reading_id
echo_id
created_at
```

### Source B: database export from Quizly

Better than crawling if available.

Export from your production/staging DB:

```text
books/courses table
readings table
echo/chat table
contest table
```

Recommended export columns:

```text
entity_type
entity_id
lang
title
description
base_text_title
base_text_author
contest_title
public_url
created_at
```

Store as:

```text
data/processed/quizly_entities.csv
```

This is the preferred input because it is more complete than crawling.

### Source C: DataForSEO Keywords For Site

Use DataForSEO `Keywords For Site` for `quizly.pub` and important pages.

Purpose:

- discover what DataForSEO already associates with the domain/page
- get externally inferred keywords without manual guessing
- compare against your own extracted terms

Important caveat:

This is not Google Search Console data. It is DataForSEO/Google Ads/SEO-estimated keyword data.

### Source D: extracted terms from actual content

From Source A/B text, extract candidate terms using deterministic rules:

1. Named entities:
   - authors
   - book titles
   - historical figures
   - places
   - contest names
2. Page titles and headings.
3. Noun phrases.
4. Repeated phrases.
5. Query-like phrases from existing question suggestions on the site.

Do not ask an LLM to invent seed keywords. Use it only later for classification/labeling if needed.

Example term extraction logic:

```text
Input page title: "Best Prince Hamlet storyteller"
Extracted anchors:
- Prince Hamlet
- Hamlet
- storyteller
- Shakespeare
- tragedy of Hamlet
```

But the system should extract these from the page text or DB export, not from hardcoded assumptions.

### Source E: Google Trends Explore, optional

Use DataForSEO Google Trends Explore after you already have candidate topics.

Purpose:

- detect rising/falling interest
- prioritize timely topics
- avoid stale topics with no demand

---

## API workflow

### Stage 0: Configuration

`config/locations.yaml`:

```yaml
markets:
  - name: United States
    location_code: 2840
    language_code: en
  - name: United Kingdom
    location_code: 2826
    language_code: en
  - name: Israel
    location_code: 2376
    language_code: en
  - name: Russia
    location_code: 2643
    language_code: ru
```

Check DataForSEO location/language codes from their docs before production runs.

`config/scoring.yaml`:

```yaml
min_search_volume: 20
max_competition: 0.8
weights:
  search_volume_log: 0.35
  low_competition: 0.20
  trend_growth: 0.15
  relevance_to_quizly: 0.20
  question_intent: 0.10
negative_filters:
  adult: true
  piracy: true
  explicit_political_targeting: true
  unrelated_commercial: true
```

### Stage 1: Collect Quizly source text

Script:

```bash
python scripts/01_collect_quizly_pages.py
```

Inputs:

- `QUIZLY_BASE_URL`
- optional URL list file
- optional DB export

Outputs:

```text
data/processed/quizly_pages.parquet
data/processed/quizly_entities.csv
```

### Stage 2: Extract candidate terms

Script:

```bash
python scripts/02_extract_candidate_terms.py
```

Inputs:

```text
data/processed/quizly_pages.parquet
data/processed/quizly_entities.csv
```

Outputs:

```text
data/processed/candidate_terms.csv
```

Columns:

```text
term
source_url
source_entity_type
source_entity_id
lang
term_type
term_count
source_title
extraction_method
```

`term_type` examples:

```text
page_title
heading
book_title
author
character
historical_person
question_phrase
noun_phrase
site_keyword
```

### Stage 3: Discover keyword ideas through DataForSEO

Script:

```bash
python scripts/03_discover_keywords.py
```

For each candidate term, call selected endpoints:

1. **Keyword Suggestions**
   - Best when you have an extracted phrase and want queries containing it.
   - Good for book titles, characters, people, concepts.

2. **Related Keywords**
   - Best for broader Google-related queries.
   - Use conservative depth first to control cost.

3. **Keyword Ideas**
   - Best after grouping candidate terms by category.
   - Avoid feeding every low-quality term.

4. **Keywords For Site**
   - Run for `quizly.pub` and selected public page URLs.

Output raw responses:

```text
data/raw/dataforseo_labs_keyword_suggestions_YYYYMMDD.jsonl
data/raw/dataforseo_labs_related_keywords_YYYYMMDD.jsonl
data/raw/dataforseo_labs_keyword_ideas_YYYYMMDD.jsonl
data/raw/dataforseo_keywords_for_site_YYYYMMDD.jsonl
```

Normalized output:

```text
data/processed/discovered_keywords.parquet
```

Columns:

```text
keyword
source_term
source_endpoint
location_code
language_code
search_volume
monthly_searches
cpc
competition
competition_level
keyword_difficulty_if_available
categories
serp_info_if_available
raw_result_id
collected_at
```

### Stage 4: Enrich search volume

Script:

```bash
python scripts/04_enrich_search_volume.py
```

Why separate this stage:

- Discovery endpoints may return some metrics, but search volume endpoint gives more consistent Google Ads metrics.
- Batch all unique keywords and send them to Google Ads Search Volume endpoint.
- Respect the limit of up to 1,000 keywords per request/task.

Input:

```text
data/processed/discovered_keywords.parquet
```

Output:

```text
data/processed/keyword_metrics.parquet
```

Columns:

```text
keyword
location_code
language_code
search_volume
monthly_searches_json
latest_month_searches
trend_3m
trend_12m
cpc
competition
competition_index
low_top_of_page_bid
high_top_of_page_bid
collected_at
```

### Stage 5: Deduplicate and normalize

Script:

```bash
python scripts/05_score_keywords.py
```

Normalization rules:

- lowercase for deduplication
- trim whitespace
- normalize punctuation
- preserve original keyword form
- merge metrics by keyword + location + language
- keep all source terms and endpoints as provenance

Deduplication output:

```text
data/processed/keyword_master.parquet
```

Columns:

```text
keyword_id
keyword
keyword_normalized
language_code
location_code
search_volume
trend_3m
trend_12m
cpc
competition
competition_level
source_terms
source_urls
source_endpoints
relevance_score
intent_label
cluster_label
opportunity_score
recommended_action
```

---

## Relevance scoring for Quizly

The scoring should prioritize keywords that can lead to Quizly content, not merely high-volume generic terms.

### Relevance components

1. **Entity match**
   - keyword contains a known book title, author, character, historical person, contest title, or topic extracted from Quizly.

2. **Interaction intent**
   Strong positive signals:
   - question words: `why`, `how`, `who`, `what`, `did`, `explain`, `summary`, `quiz`, `test`, `chat`, `character`, `conversation`
   - Russian equivalents: `почему`, `как`, `кто`, `что`, `объяснение`, `кратко`, `викторина`, `тест`, `персонаж`

3. **Educational/literary/history intent**
   Positive signals:
   - summary
   - explained
   - questions and answers
   - quiz
   - characters
   - historical facts
   - biography
   - timeline
   - analysis

4. **Bad-fit filters**
   Downrank:
   - pure e-commerce
   - unrelated celebrity/news ambiguity
   - piracy/download requests
   - adult or unsafe terms
   - topics that cannot map to a public-domain/authorized base text

5. **Content availability**
   Higher score if Quizly already has:
   - matching base text
   - matching contest
   - matching chat/echo
   - matching reading page

### Opportunity score

Suggested formula:

```text
opportunity_score =
  0.35 * log_scaled_search_volume +
  0.20 * inverse_competition +
  0.15 * trend_growth_score +
  0.20 * quizly_relevance_score +
  0.10 * question_or_interaction_intent_score
```

Keep this in config so it can be tuned without code edits.

---

## Visualization requirements

The results should be visualized as an interactive HTML report and CSV exports.

### Main report

Output:

```text
outputs/keyword_opportunities.html
```

Sections:

1. Executive summary
   - total discovered keywords
   - keywords with volume
   - top languages
   - top markets
   - top clusters
   - top 20 opportunities

2. Opportunity table
   - sortable/filterable table
   - keyword
   - search volume
   - competition
   - trend 3m / 12m
   - CPC
   - relevance score
   - opportunity score
   - source term
   - suggested Quizly action

3. Scatter plot: volume vs competition
   - x-axis: competition
   - y-axis: search volume, log scale
   - point size: trend growth
   - color: cluster or intent
   - hover: keyword, source term, URL, scores

4. Trend heatmap
   - rows: top keywords
   - columns: last 12 months
   - values: monthly search volume

5. Cluster view
   - grouped by topic cluster
   - cluster size
   - aggregate volume
   - average competition
   - best keyword in cluster

6. Action report
   Suggested actions:
   - create new Quizly chat
   - create landing page
   - improve existing page title/meta
   - add FAQ block
   - create quiz/game
   - ignore / irrelevant

### Visual tools

Recommended:

- `plotly` for interactive charts
- `pandas` for table generation
- optional `dash` later if you want a local web dashboard

First version should be static HTML, not a server.

Run:

```bash
python scripts/06_visualize.py
```

Open:

```bash
xdg-open outputs/keyword_opportunities.html
```

---

## Minimal code architecture

### `src/quizly_keywords/settings.py`

Responsibilities:

- load `.env`
- validate required settings
- expose DataForSEO base URL, login, password

### `src/quizly_keywords/dataforseo_client.py`

Responsibilities:

- Basic Auth
- request wrapper
- retry with exponential backoff
- sandbox/production switch
- raw JSON logging
- cost-safe batch limits

Methods:

```python
class DataForSEOClient:
    def keyword_suggestions(self, keyword, location_code, language_code): ...
    def related_keywords(self, keyword, location_code, language_code, depth=1): ...
    def keyword_ideas(self, keywords, location_code, language_code): ...
    def search_volume(self, keywords, location_code, language_code): ...
    def keywords_for_site(self, target, location_code, language_code): ...
```

### `src/quizly_keywords/quizly_site.py`

Responsibilities:

- crawl public URLs
- parse HTML
- extract text and metadata
- optionally ingest DB export

### `src/quizly_keywords/text_extract.py`

Responsibilities:

- extract title/heading terms
- extract noun phrases
- extract entities from page text
- extract existing user-facing questions
- produce candidate terms with provenance

### `src/quizly_keywords/discovery.py`

Responsibilities:

- select candidate terms for API calls
- call DataForSEO discovery endpoints
- store raw responses
- normalize keyword rows

### `src/quizly_keywords/volume.py`

Responsibilities:

- batch unique keywords
- call Search Volume endpoint
- merge metrics

### `src/quizly_keywords/scoring.py`

Responsibilities:

- relevance rules
- trend calculations
- competition normalization
- opportunity score
- suggested action

### `src/quizly_keywords/visualize.py`

Responsibilities:

- HTML report
- Plotly charts
- CSV exports

---

## Example CLI commands

Full pipeline:

```bash
python scripts/00_check_credentials.py
python scripts/01_collect_quizly_pages.py
python scripts/02_extract_candidate_terms.py
python scripts/03_discover_keywords.py --market us-en --limit-terms 200
python scripts/04_enrich_search_volume.py --market us-en
python scripts/05_score_keywords.py
python scripts/06_visualize.py
```

Russian market:

```bash
python scripts/03_discover_keywords.py --market ru-ru --limit-terms 200
python scripts/04_enrich_search_volume.py --market ru-ru
python scripts/05_score_keywords.py --market ru-ru
python scripts/06_visualize.py --market ru-ru
```

Israel English market:

```bash
python scripts/03_discover_keywords.py --market il-en --limit-terms 200
python scripts/04_enrich_search_volume.py --market il-en
python scripts/05_score_keywords.py --market il-en
python scripts/06_visualize.py --market il-en
```

---

## Cost-control rules

Start with sandbox.

Production run phase 1:

```text
candidate terms: max 100
markets: 1
related keyword depth: 1
keyword suggestions limit: conservative
search volume batch: unique discovered keywords only
```

Production run phase 2:

```text
candidate terms: max 500
markets: 2-3
related keyword depth: 2 where useful
search volume for all deduped candidates
```

Production run phase 3:

```text
scheduled weekly/monthly runs
only refresh changed/new source entities
cache DataForSEO responses
avoid re-requesting unchanged keyword metrics too frequently
```

Cache key:

```text
endpoint + keyword/source_url + location_code + language_code + date_bucket
```

Recommended date bucket:

```text
YYYY-MM
```

---

## Suggested first implementation milestone

### Milestone 1: API connectivity and raw results

Deliverables:

```text
.env.example
scripts/00_check_credentials.py
src/quizly_keywords/dataforseo_client.py
data/raw/test_response.json
```

Done when:

- sandbox request succeeds
- production request succeeds with one small test
- raw response is saved

### Milestone 2: Quizly source extraction

Deliverables:

```text
data/processed/quizly_pages.parquet
data/processed/candidate_terms.csv
```

Done when:

- at least 50 public pages/entities processed
- candidate terms extracted with source provenance
- no manual keyword guessing required

### Milestone 3: Keyword discovery

Deliverables:

```text
data/processed/discovered_keywords.parquet
```

Done when:

- keyword suggestions/related keywords/keyword ideas run for selected candidate terms
- duplicate keywords merged
- each keyword has source term and endpoint provenance

### Milestone 4: Search volume enrichment

Deliverables:

```text
data/processed/keyword_metrics.parquet
```

Done when:

- unique keywords are batched
- search volume, CPC, competition, and monthly trends are added

### Milestone 5: Visualization

Deliverables:

```text
outputs/keyword_opportunities.html
outputs/keyword_opportunities.csv
outputs/keyword_clusters.csv
```

Done when:

- report opens locally
- table is sortable/filterable or at least clearly structured
- charts show volume/competition/trends/clusters
- each keyword includes recommended action

---

## Final output format

The final report should produce three main files:

```text
outputs/keyword_opportunities.html
outputs/keyword_opportunities.csv
outputs/keyword_clusters.csv
```

Recommended CSV columns:

```text
keyword
language_code
location_code
search_volume
trend_3m
trend_12m
competition
cpc
source_term
source_url
intent_label
cluster_label
relevance_score
opportunity_score
recommended_action
```

Example recommended actions:

```text
create_chat
create_quiz
create_landing_page
add_faq_to_existing_page
improve_title_meta
monitor_only
ignore_irrelevant
```

---

## Risks and caveats

1. DataForSEO data is not exact Google internal search logs.
2. Competitor/random-site keyword data is estimated.
3. Low-volume keywords can still be valuable for Quizly if intent is strong.
4. High-volume keywords can be useless if they are too generic or commercial.
5. Russian-language and Hebrew-language keyword data may be sparser than English.
6. DataForSEO endpoint prices and limits can change; check pricing before production runs.
7. Do not build billing assumptions into code without a config-based cost limiter.

---

## Recommended default first run

Use one market first:

```text
United States / English
```

Then add:

```text
Russia / Russian
Israel / English
Israel / Russian, if useful
United Kingdom / English
```

Run small, inspect quality, then scale.

---

## Implementation principle

The system should answer this question:

> “Given what Quizly already contains or can legitimately contain, which Google keywords have enough demand and suitable intent to justify a page, chat, quiz, FAQ block, or contest?”

Not this question:

> “What random topics could be popular?”

That distinction is important. It keeps the pipeline grounded in Quizly content and avoids manual guessing.
