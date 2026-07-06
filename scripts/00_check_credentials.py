#!/usr/bin/env python3
"""Validate DataForSEO credentials and base URL."""
import _bootstrap  # noqa: F401
_bootstrap.setup_logging()

from quizly_keywords.dataforseo_client import DataForSEOClient, DataForSEOError
from quizly_keywords.settings import load_settings


def main() -> int:
    settings = load_settings()
    settings.ensure_dirs()
    if not settings.has_credentials:
        print("DataForSEO credentials are not set.")
        print("Edit .env and set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD.")
        return 1
    try:
        client = DataForSEOClient(settings)
        client.ping()
    except (DataForSEOError, Exception) as exc:  # noqa: BLE001
        print(f"DataForSEO auth FAILED: {exc}")
        return 1
    print("DataForSEO auth OK")
    print(f"Base URL: {settings.base_url}")
    print(f"Mode: {'sandbox' if settings.is_sandbox else 'PRODUCTION'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
