"""
News Ingestion — RSS Feed Client
=================================
Pulls financial news from RSS feeds published by ET Markets, Moneycontrol,
LiveMint, and Business Standard.  RSS feeds are explicitly published for
consumption and are the ToS-safe route — we store headline + summary + link
only (no full article text redistribution).

Public interface
----------------
    scraper = NewsScraper()
    await scraper.run_all()          # pull all configured feeds
    await scraper.run_feed(url, source_name)
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
from loguru import logger
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import settings
from backend.db.models import NewsArticle
from backend.db.session import AsyncSessionLocal


# ── Configured feeds ──────────────────────────────────────────────────────────

FEEDS: list[dict[str, str]] = [
    {"source": "et_markets",        "url": settings.et_markets_rss},
    {"source": "moneycontrol",      "url": settings.moneycontrol_rss},
    {"source": "livemint",          "url": settings.livemint_rss},
    {"source": "business_standard", "url": settings.business_standard_rss},
]

# Keywords used to tag articles as potentially relevant to mutual funds
_MF_KEYWORDS: re.Pattern = re.compile(
    r"mutual fund|mf|nav|sip|amfi|sebi|amc|nfo|scheme|folio"
    r"|nifty|sensex|equity|debt fund|hybrid fund|elss|index fund",
    re.I,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stable_guid(entry: Any, source: str) -> str:
    """Derive a stable, unique ID for a feed entry regardless of feed quirks."""
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(f"{source}:{raw}".encode()).hexdigest()


def _parse_published(entry: Any) -> datetime | None:
    """Parse published / updated datetime from a feedparser entry."""
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass
    # feedparser may also populate published_parsed (time.struct_time)
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=None)
    return None


def _clean_html(text: str | None) -> str | None:
    """Strip HTML tags from summary text."""
    if not text:
        return None
    return re.sub(r"<[^>]+>", "", text).strip() or None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _fetch_feed_text(url: str) -> str:
    """Download RSS feed content, respecting a polite User-Agent."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        resp = await client.get(
            url,
            headers={"User-Agent": "MFScope-Research/0.1 (educational; RSS reader)"},
        )
        resp.raise_for_status()
        return resp.text


# ── Main scraper ──────────────────────────────────────────────────────────────

class NewsScraper:
    """
    Pulls RSS feeds and persists new NewsArticle rows.
    Deduplicates on `guid` so re-running is always safe.
    """

    async def run_all(self) -> dict[str, int]:
        """
        Pull every configured RSS feed concurrently.
        Returns a dict {source: new_articles_count}.
        """
        tasks = [self.run_feed(f["url"], f["source"]) for f in FEEDS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        summary: dict[str, int] = {}
        for feed, result in zip(FEEDS, results):
            if isinstance(result, Exception):
                logger.error(f"Feed {feed['source']} failed: {result}")
                summary[feed["source"]] = 0
            else:
                summary[feed["source"]] = result  # type: ignore[assignment]
        return summary

    async def run_feed(self, url: str, source: str) -> int:
        """
        Pull a single RSS feed URL and persist new articles.
        Returns the count of newly inserted articles.
        """
        logger.info(f"Pulling RSS feed: {source} ({url})")
        try:
            raw = await _fetch_feed_text(url)
        except Exception as exc:
            logger.error(f"Failed to fetch {source}: {exc}")
            return 0

        feed = feedparser.parse(raw)
        entries = feed.get("entries", [])
        logger.info(f"{source}: {len(entries)} entries in feed")

        inserted = 0
        async with AsyncSessionLocal() as session:
            for entry in entries:
                guid = _stable_guid(entry, source)

                # Skip if already stored
                exists = await session.scalar(
                    select(NewsArticle.id).where(NewsArticle.guid == guid)
                )
                if exists:
                    continue

                title: str = entry.get("title", "").strip()
                summary = _clean_html(
                    entry.get("summary") or entry.get("description")
                )
                url_link: str | None = entry.get("link")
                published_at = _parse_published(entry)

                # Only store articles with a meaningful title
                if not title:
                    continue

                article = NewsArticle(
                    guid=guid,
                    source=source,
                    title=title,
                    summary=summary,
                    url=url_link,
                    published_at=published_at,
                )
                session.add(article)
                inserted += 1

            await session.commit()

        logger.info(f"{source}: {inserted} new articles inserted.")
        return inserted

    # ── Utility: fetch unscored articles ──────────────────────────────────────

    async def get_unscored_articles(self, limit: int = 200) -> list[NewsArticle]:
        """
        Return articles that have no associated NewsSentiment rows yet.
        Used by the NLP pipeline to know what still needs scoring.
        """
        from backend.db.models import NewsSentiment
        async with AsyncSessionLocal() as session:
            # Subquery: article ids that already have a sentiment row
            scored_subq = select(NewsSentiment.article_id).distinct().subquery()
            stmt = (
                select(NewsArticle)
                .where(NewsArticle.id.not_in(select(scored_subq.c.article_id)))
                .order_by(NewsArticle.published_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
