"""Collect Quizly source text: crawl public pages and/or ingest a DB export.

The crawler is deliberately polite (delay, same-domain only, robots-aware) and
bounded (max_pages, max_depth). If `trafilatura` is installed it is used for
main-text extraction; otherwise we fall back to BeautifulSoup.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .settings import Settings

logger = logging.getLogger(__name__)

PAGE_COLUMNS = [
    "url", "lang", "title", "meta_description", "h1", "h2", "h3",
    "body_text", "content_type", "course_id", "reading_id", "echo_id",
    "internal_links", "created_at",
]

_ID_PARAM_RE = re.compile(r"[?&]id=(\d+)")


@dataclass
class Page:
    url: str
    lang: str = ""
    title: str = ""
    meta_description: str = ""
    h1: str = ""
    h2: str = ""
    h3: str = ""
    body_text: str = ""
    content_type: str = ""
    course_id: str = ""
    reading_id: str = ""
    echo_id: str = ""
    internal_links: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_row(self) -> dict:
        d = self.__dict__.copy()
        d["internal_links"] = "|".join(self.internal_links)
        return d


def _main_text(html: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_comments=False, favor_recall=True)
        if extracted:
            return extracted.strip()
    except ImportError:
        pass
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _classify_content_type(url: str) -> str:
    path = urlparse(url).path.lower() + "?" + (urlparse(url).query.lower())
    if "contest" in path:
        return "contest"
    if "read" in path or "book" in path:
        return "reading"
    if "echo" in path or "chat" in path:
        return "echo"
    if urlparse(url).path in ("", "/"):
        return "home"
    return "page"


def parse_html(url: str, html: str) -> Page:
    soup = BeautifulSoup(html, "lxml")
    page = Page(url=url)
    page.lang = (soup.html.get("lang") if soup.html and soup.html.has_attr("lang") else "") or ""
    if soup.title and soup.title.string:
        page.title = soup.title.string.strip()
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        page.meta_description = meta["content"].strip()
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        page.url = canonical["href"].strip()
    page.h1 = " | ".join(h.get_text(strip=True) for h in soup.find_all("h1"))
    page.h2 = " | ".join(h.get_text(strip=True) for h in soup.find_all("h2"))
    page.h3 = " | ".join(h.get_text(strip=True) for h in soup.find_all("h3"))
    page.body_text = _main_text(html)
    page.content_type = _classify_content_type(url)

    m = _ID_PARAM_RE.search(url)
    if m and page.content_type == "contest":
        page.course_id = m.group(1)
    elif m and page.content_type == "reading":
        page.reading_id = m.group(1)
    elif m and page.content_type == "echo":
        page.echo_id = m.group(1)

    domain = urlparse(url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        full = urljoin(url, a["href"])
        if urlparse(full).netloc == domain:
            links.append(full.split("#")[0])
    page.internal_links = sorted(set(links))
    return page


class QuizlyCrawler:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cfg = (settings.sources_cfg.get("quizly") or {})
        self.crawl_cfg = self.cfg.get("crawl", {})
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": self.crawl_cfg.get("user_agent", "kvasir_seo/0.1")}
        )
        self._robots: robotparser.RobotFileParser | None = None

    def _allowed(self, url: str) -> bool:
        if not self.crawl_cfg.get("respect_robots_txt", True):
            return True
        if self._robots is None:
            base = self.cfg.get("base_url", self.settings.quizly_base_url)
            self._robots = robotparser.RobotFileParser()
            self._robots.set_url(urljoin(base, "/robots.txt"))
            try:
                self._robots.read()
            except Exception:  # robots unreachable -> be permissive but log
                logger.warning("Could not read robots.txt; proceeding without it")
                self._robots.parse([])
        return self._robots.can_fetch(self.session.headers["User-Agent"], url)

    def _seed_urls(self) -> list[str]:
        urls = list(self.cfg.get("seed_urls") or [self.settings.quizly_base_url])
        probe = self.cfg.get("id_probe") or {}
        if probe.get("enabled"):
            base = self.cfg.get("base_url", self.settings.quizly_base_url)
            for pattern in self.cfg.get("url_patterns") or []:
                for i in range(int(probe["start"]), int(probe["end"]) + 1):
                    urls.append(urljoin(base, pattern.format(id=i)))
        return urls

    def crawl(self) -> pd.DataFrame:
        max_pages = int(self.crawl_cfg.get("max_pages", 200))
        max_depth = int(self.crawl_cfg.get("max_depth", 2))
        delay = float(self.crawl_cfg.get("request_delay_seconds", 1.0))
        domain = urlparse(self.cfg.get("base_url", self.settings.quizly_base_url)).netloc

        seen: set[str] = set()
        queue: list[tuple[str, int]] = [(u, 0) for u in self._seed_urls()]
        pages: list[Page] = []

        while queue and len(pages) < max_pages:
            url, depth = queue.pop(0)
            if url in seen or depth > max_depth:
                continue
            seen.add(url)
            if urlparse(url).netloc != domain:
                continue
            if not self._allowed(url):
                logger.info("robots.txt disallows %s", url)
                continue
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                    continue
                page = parse_html(url, resp.text)
            except requests.RequestException as exc:
                logger.warning("fetch failed %s: %s", url, exc)
                continue
            pages.append(page)
            logger.info("crawled [%d] %s", len(pages), url)
            for link in page.internal_links:
                if link not in seen:
                    queue.append((link, depth + 1))
            time.sleep(delay)

        rows = [p.to_row() for p in pages]
        df = pd.DataFrame(rows, columns=PAGE_COLUMNS) if rows else pd.DataFrame(columns=PAGE_COLUMNS)
        return df


def ingest_db_export(path: str) -> pd.DataFrame:
    """Load an optional Quizly DB export CSV (Source B). Preferred over crawling."""
    return pd.read_csv(path)
