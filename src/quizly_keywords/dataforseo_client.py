"""Thin, cost-aware wrapper around the DataForSEO API v3.

Covers the endpoints the plan uses:
  - DataForSEO Labs: Keyword Suggestions, Related Keywords, Keyword Ideas
  - Keywords Data (Google Ads): Search Volume (live), Keywords For Site (live)

Design notes:
  - Basic Auth with login/password from settings.
  - Every response is logged raw to data/raw/*.jsonl for provenance/debugging.
  - A per-run call budget (MAX_API_CALLS_PER_RUN) guards against runaway spend.
  - Retries with exponential backoff on transient errors.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Sequence

import requests

from .settings import Settings
from .storage import append_jsonl, raw, today_stamp

logger = logging.getLogger(__name__)


class CallBudgetExceeded(RuntimeError):
    """Raised when a run would exceed MAX_API_CALLS_PER_RUN."""


class DataForSEOError(RuntimeError):
    pass


class DataForSEOClient:
    def __init__(self, settings: Settings, *, timeout: int = 60, max_retries: int = 3):
        if not settings.has_credentials:
            raise DataForSEOError(
                "DataForSEO credentials are not set. Fill DATAFORSEO_LOGIN / "
                "DATAFORSEO_PASSWORD in .env before calling the API."
            )
        self.settings = settings
        self.timeout = timeout
        self.max_retries = max_retries
        self._calls_made = 0
        self._session = requests.Session()
        self._session.auth = (settings.login, settings.password)
        self._session.headers.update({"Content-Type": "application/json"})

    # -- low-level -------------------------------------------------------
    @property
    def calls_made(self) -> int:
        return self._calls_made

    def _budget_check(self) -> None:
        if self._calls_made >= self.settings.max_api_calls_per_run:
            raise CallBudgetExceeded(
                f"Reached MAX_API_CALLS_PER_RUN={self.settings.max_api_calls_per_run}. "
                "Raise the limit in .env if this is intentional."
            )

    def _post(self, endpoint: str, payload: list[dict[str, Any]], *, raw_log: str) -> dict[str, Any]:
        """POST a task array to `endpoint` and return the parsed JSON body."""
        self._budget_check()
        url = f"{self.settings.base_url}{endpoint}"
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout)
                self._calls_made += 1
                if resp.status_code >= 500:
                    raise DataForSEOError(f"HTTP {resp.status_code} from {endpoint}")
                data = resp.json()
                self._log_raw(raw_log, endpoint, payload, data)
                status = data.get("status_code")
                # 20000 = ok. Task-level errors are surfaced per-task by callers.
                if status not in (None, 20000):
                    raise DataForSEOError(
                        f"{endpoint} status_code={status} message={data.get('status_message')}"
                    )
                return data
            except (requests.RequestException, DataForSEOError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    backoff = 2 ** attempt
                    logger.warning("Call to %s failed (%s); retrying in %ss", endpoint, exc, backoff)
                    time.sleep(backoff)
        raise DataForSEOError(f"{endpoint} failed after {self.max_retries} attempts: {last_exc}")

    def _log_raw(self, raw_log: str, endpoint: str, payload: Any, data: Any) -> None:
        path: Path = raw(f"{raw_log}_{today_stamp()}.jsonl")
        append_jsonl(path, [{"endpoint": endpoint, "request": payload, "response": data}])

    @staticmethod
    def extract_results(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten DataForSEO's tasks[].result[] structure into a list."""
        results: list[dict[str, Any]] = []
        for task in data.get("tasks") or []:
            if task.get("status_code") not in (20000, None):
                logger.warning("task error %s: %s", task.get("status_code"), task.get("status_message"))
                continue
            for res in task.get("result") or []:
                results.append(res)
        return results

    # -- DataForSEO Labs -------------------------------------------------
    def keyword_suggestions(
        self, keyword: str, location_code: int, language_code: str, *, limit: int = 300
    ) -> dict[str, Any]:
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "include_serp_info": False,
                "limit": limit,
            }
        ]
        return self._post(
            "/v3/dataforseo_labs/google/keyword_suggestions/live",
            payload,
            raw_log="dataforseo_labs_keyword_suggestions",
        )

    def related_keywords(
        self, keyword: str, location_code: int, language_code: str, *, depth: int = 1, limit: int = 300
    ) -> dict[str, Any]:
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "depth": depth,
                "limit": limit,
            }
        ]
        return self._post(
            "/v3/dataforseo_labs/google/related_keywords/live",
            payload,
            raw_log="dataforseo_labs_related_keywords",
        )

    def keyword_ideas(
        self, keywords: Sequence[str], location_code: int, language_code: str, *, limit: int = 300
    ) -> dict[str, Any]:
        payload = [
            {
                "keywords": list(keywords),
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
            }
        ]
        return self._post(
            "/v3/dataforseo_labs/google/keyword_ideas/live",
            payload,
            raw_log="dataforseo_labs_keyword_ideas",
        )

    # -- Keywords Data (Google Ads) -------------------------------------
    def search_volume(
        self, keywords: Sequence[str], location_code: int, language_code: str
    ) -> dict[str, Any]:
        kws = list(keywords)
        if len(kws) > 1000:
            raise DataForSEOError("Search Volume accepts at most 1000 keywords per request.")
        payload = [
            {
                "keywords": kws,
                "location_code": location_code,
                "language_code": language_code,
            }
        ]
        return self._post(
            "/v3/keywords_data/google_ads/search_volume/live",
            payload,
            raw_log="google_ads_search_volume",
        )

    def keywords_for_site(
        self, target: str, location_code: int, language_code: str, *, limit: int = 300
    ) -> dict[str, Any]:
        payload = [
            {
                "target": target,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
            }
        ]
        return self._post(
            "/v3/keywords_data/google_ads/keywords_for_site/live",
            payload,
            raw_log="google_ads_keywords_for_site",
        )

    # -- SERP API (optional intent phase) -------------------------------
    def serp_organic(
        self, keyword: str, location_code: int, language_code: str, *, depth: int = 10
    ) -> dict[str, Any]:
        """Live Google organic SERP for one keyword (used to classify intent)."""
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "depth": depth,
            }
        ]
        return self._post(
            "/v3/serp/google/organic/live/advanced",
            payload,
            raw_log="serp_google_organic",
        )

    # -- Google Trends (optional) ---------------------------------------
    def google_trends_explore(
        self,
        keywords: Sequence[str],
        location_code: int,
        language_code: str,
        *,
        time_range: str = "past_12_months",
    ) -> dict[str, Any]:
        """Google Trends Explore for up to 5 keywords (relative interest/rising)."""
        kws = list(keywords)
        if len(kws) > 5:
            raise DataForSEOError("Google Trends Explore accepts at most 5 keywords per request.")
        payload = [
            {
                "keywords": kws,
                "location_code": location_code,
                "language_code": language_code,
                "time_range": time_range,
            }
        ]
        return self._post(
            "/v3/keywords_data/google_trends/explore/live",
            payload,
            raw_log="google_trends_explore",
        )

    # -- health check ----------------------------------------------------
    def ping(self) -> dict[str, Any]:
        """Cheap authenticated GET to confirm credentials/base URL work."""
        self._budget_check()
        url = f"{self.settings.base_url}/v3/appendix/user_data"
        resp = self._session.get(url, timeout=self.timeout)
        self._calls_made += 1
        resp.raise_for_status()
        return resp.json()
