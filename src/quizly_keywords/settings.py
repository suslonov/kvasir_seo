"""Environment + YAML config loading and validation.

Reads `.env` (via python-dotenv) and the YAML files under `config/`. Exposes a
single `load_settings()` entry point that the scripts use.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Repo root = two levels up from this file (src/quizly_keywords/settings.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = REPO_ROOT / "outputs"


@dataclass(frozen=True)
class Market:
    key: str
    name: str
    location_code: int
    language_code: str


@dataclass
class Settings:
    login: str
    password: str
    base_url: str
    quizly_base_url: str
    default_location_code: int
    default_language_code: str
    default_limit: int
    max_api_calls_per_run: int
    markets: dict[str, Market] = field(default_factory=dict)
    default_market: str = "us-en"
    locations_cfg: dict[str, Any] = field(default_factory=dict)
    languages_cfg: dict[str, Any] = field(default_factory=dict)
    sources_cfg: dict[str, Any] = field(default_factory=dict)
    scoring_cfg: dict[str, Any] = field(default_factory=dict)

    @property
    def is_sandbox(self) -> bool:
        return "sandbox" in self.base_url

    @property
    def has_credentials(self) -> bool:
        return bool(self.login) and bool(self.password) and "your_dataforseo" not in self.login

    def market(self, key: str | None) -> Market:
        """Resolve a market by key, falling back to the default market."""
        key = key or self.default_market
        if key not in self.markets:
            raise KeyError(
                f"Unknown market '{key}'. Known markets: {', '.join(sorted(self.markets))}"
            )
        return self.markets[key]

    def ensure_dirs(self) -> None:
        for d in (RAW_DIR, PROCESSED_DIR, OUTPUTS_DIR, OUTPUTS_DIR / "charts"):
            d.mkdir(parents=True, exist_ok=True)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")

    locations_cfg = _read_yaml(CONFIG_DIR / "locations.yaml")
    markets: dict[str, Market] = {}
    for key, m in (locations_cfg.get("markets") or {}).items():
        markets[key] = Market(
            key=key,
            name=m.get("name", key),
            location_code=int(m["location_code"]),
            language_code=str(m["language_code"]),
        )

    return Settings(
        login=os.getenv("DATAFORSEO_LOGIN", ""),
        password=os.getenv("DATAFORSEO_PASSWORD", ""),
        base_url=os.getenv("DATAFORSEO_BASE_URL", "https://sandbox.dataforseo.com").rstrip("/"),
        quizly_base_url=os.getenv("QUIZLY_BASE_URL", "https://quizly.pub").rstrip("/"),
        default_location_code=int(os.getenv("DEFAULT_LOCATION_CODE", "2840")),
        default_language_code=os.getenv("DEFAULT_LANGUAGE_CODE", "en"),
        default_limit=int(os.getenv("DEFAULT_LIMIT", "1000")),
        max_api_calls_per_run=int(os.getenv("MAX_API_CALLS_PER_RUN", "200")),
        markets=markets,
        default_market=locations_cfg.get("default_market", "us-en"),
        locations_cfg=locations_cfg,
        languages_cfg=_read_yaml(CONFIG_DIR / "languages.yaml"),
        sources_cfg=_read_yaml(CONFIG_DIR / "sources.yaml"),
        scoring_cfg=_read_yaml(CONFIG_DIR / "scoring.yaml"),
    )
