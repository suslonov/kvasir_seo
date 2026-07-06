"""Stage 6: build the interactive HTML report and CSV exports.

Uses Plotly when available for the scatter/heatmap; degrades to plain HTML
tables otherwise so the report always renders.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .settings import OUTPUTS_DIR

REPORT_CSV_COLUMNS = [
    "keyword", "language_code", "location_code", "search_volume", "trend_3m",
    "trend_12m", "competition", "cpc", "source_terms", "source_urls",
    "intent_label", "cluster_label", "relevance_score", "opportunity_score",
    "recommended_action",
]

# Optional columns from stages 07/08; shown in the report only when present.
OPTIONAL_COLUMNS = ["serp_intent", "trend_direction"]


def _report_columns(df: pd.DataFrame) -> list[str]:
    return REPORT_CSV_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]


def _try_plotly():
    try:
        import plotly.express as px  # noqa: F401
        import plotly.graph_objects as go  # noqa: F401
        import plotly.io as pio  # noqa: F401

        return True
    except ImportError:
        return False


def _scatter_html(df: pd.DataFrame) -> str:
    import plotly.express as px

    d = df.copy()
    d["search_volume"] = pd.to_numeric(d["search_volume"], errors="coerce").fillna(0)
    d["competition"] = pd.to_numeric(d["competition"], errors="coerce").fillna(0)
    d = d[d["search_volume"] > 0]
    if d.empty:
        return "<p><em>No keywords with volume to plot.</em></p>"
    d["trend_size"] = pd.to_numeric(d.get("trend_3m"), errors="coerce").fillna(0).clip(lower=0) + 0.1
    fig = px.scatter(
        d, x="competition", y="search_volume", size="trend_size",
        color=d.get("cluster_label"), log_y=True,
        hover_data=["keyword", "source_terms", "opportunity_score", "recommended_action"],
        title="Search volume vs competition (size = 3m trend)",
    )
    fig.update_layout(height=520)
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def _heatmap_html(df: pd.DataFrame, top_n: int = 20) -> str:
    import plotly.graph_objects as go

    d = df.copy()
    d = d.sort_values("opportunity_score", ascending=False).head(top_n)
    rows, labels = [], []
    for _, r in d.iterrows():
        raw = r.get("monthly_searches_json")
        monthly = raw
        if isinstance(raw, str) and raw:
            try:
                monthly = json.loads(raw.replace("'", '"'))
            except Exception:
                monthly = None
        if isinstance(monthly, list) and monthly:
            vals = [m.get("search_volume") or 0 for m in monthly][:12][::-1]
            if any(vals):
                rows.append(vals)
                labels.append(str(r["keyword"])[:40])
    if not rows:
        return "<p><em>No monthly trend data available (run search-volume enrichment).</em></p>"
    width = max(len(r) for r in rows)
    rows = [r + [0] * (width - len(r)) for r in rows]
    fig = go.Figure(data=go.Heatmap(z=rows, y=labels, colorscale="Blues"))
    fig.update_layout(title="Monthly search volume — top keywords", height=max(300, 24 * len(labels)))
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _table_html(df: pd.DataFrame, columns: list[str], max_rows: int = 500) -> str:
    cols = [c for c in columns if c in df.columns]
    view = df[cols].head(max_rows)
    return view.to_html(index=False, classes="kw-table", border=0, escape=True)


def _summary_html(df: pd.DataFrame) -> str:
    total = len(df)
    with_vol = int((pd.to_numeric(df.get("search_volume"), errors="coerce").fillna(0) > 0).sum())
    langs = df.get("language_code")
    top_langs = ", ".join(f"{k} ({v})" for k, v in langs.value_counts().head(5).items()) if langs is not None else "-"
    clusters = df.get("cluster_label")
    top_clusters = ", ".join(f"{k}" for k in clusters.value_counts().head(8).index) if clusters is not None else "-"
    return f"""
    <ul>
      <li><b>Total keywords:</b> {total}</li>
      <li><b>With search volume:</b> {with_vol}</li>
      <li><b>Top languages:</b> {top_langs}</li>
      <li><b>Top clusters:</b> {top_clusters}</li>
    </ul>
    """


def build_report(scored: pd.DataFrame, *, market_name: str = "") -> dict[str, Path]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / "charts").mkdir(exist_ok=True)

    html_path = OUTPUTS_DIR / "keyword_opportunities.html"
    csv_path = OUTPUTS_DIR / "keyword_opportunities.csv"
    clusters_path = OUTPUTS_DIR / "keyword_clusters.csv"

    # CSV exports.
    export = scored.copy()
    for col in REPORT_CSV_COLUMNS:
        if col not in export.columns:
            export[col] = None
    export[REPORT_CSV_COLUMNS].to_csv(csv_path, index=False)

    if "cluster_label" in scored.columns and not scored.empty:
        clusters = (
            scored.assign(search_volume=pd.to_numeric(scored["search_volume"], errors="coerce"))
            .groupby("cluster_label")
            .agg(
                keywords=("keyword", "count"),
                total_volume=("search_volume", "sum"),
                avg_competition=("competition", lambda s: pd.to_numeric(s, errors="coerce").mean()),
                avg_opportunity=("opportunity_score", "mean"),
                best_keyword=("keyword", "first"),
            )
            .sort_values("total_volume", ascending=False)
            .reset_index()
        )
    else:
        clusters = pd.DataFrame(columns=["cluster_label", "keywords", "total_volume"])
    clusters.to_csv(clusters_path, index=False)

    # HTML.
    if _try_plotly() and not scored.empty:
        scatter = _scatter_html(scored)
        heatmap = _heatmap_html(scored)
    else:
        scatter = "<p><em>Install plotly for interactive charts.</em></p>"
        heatmap = ""

    top20 = scored.head(20)
    style = """
    <style>
      body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; color: #1a1a1a; }
      h1 { margin-bottom: 4px; }
      .kw-table { border-collapse: collapse; width: 100%; font-size: 13px; }
      .kw-table th, .kw-table td { border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; }
      .kw-table th { background: #f6f8fa; position: sticky; top: 0; }
      section { margin: 28px 0; }
      .muted { color: #666; }
    </style>
    """
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Quizly keyword opportunities</title>{style}</head>
<body>
  <h1>Quizly keyword opportunities</h1>
  <p class="muted">Market: {market_name or 'all'} · generated by kvasir_seo</p>

  <section><h2>1. Executive summary</h2>{_summary_html(scored)}</section>

  <section><h2>2. Top 20 opportunities</h2>
    {_table_html(top20, _report_columns(scored))}
  </section>

  <section><h2>3. Volume vs competition</h2>{scatter}</section>

  <section><h2>4. Trend heatmap</h2>{heatmap}</section>

  <section><h2>5. Clusters</h2>{_table_html(clusters, list(clusters.columns))}</section>

  <section><h2>6. Full opportunity table</h2>
    {_table_html(scored, _report_columns(scored))}
  </section>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    return {"html": html_path, "csv": csv_path, "clusters": clusters_path}
