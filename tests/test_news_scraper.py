"""
Tests for backend/ingestion/news_scraper.py

Covers:
- GUID derivation (stable, unique)
- HTML stripping
- Published-date parsing
- De-duplication: re-running the same feed doesn't insert duplicates
- get_unscored_articles filters correctly
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.db.models import NewsArticle, NewsSentiment, SentimentLabel
from backend.ingestion.news_scraper import (
    NewsScraper,
    _clean_html,
    _parse_published,
    _stable_guid,
)


# ── Unit helpers ──────────────────────────────────────────────────────────────

class TestStableGuid:
    def test_same_inputs_same_guid(self):
        entry = {"id": "https://example.com/article/1"}
        assert _stable_guid(entry, "et_markets") == _stable_guid(entry, "et_markets")

    def test_different_sources_different_guid(self):
        entry = {"id": "https://example.com/article/1"}
        assert _stable_guid(entry, "et_markets") != _stable_guid(entry, "moneycontrol")

    def test_falls_back_to_link(self):
        entry = {"link": "https://example.com/article/2"}
        guid = _stable_guid(entry, "test")
        assert isinstance(guid, str) and len(guid) == 64  # sha256 hex

    def test_falls_back_to_title(self):
        entry = {"title": "Fund posts gains"}
        guid = _stable_guid(entry, "test")
        assert len(guid) == 64

    def test_empty_entry_returns_hash(self):
        guid = _stable_guid({}, "test")
        assert len(guid) == 64


class TestCleanHtml:
    def test_strips_tags(self):
        assert _clean_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_none_returns_none(self):
        assert _clean_html(None) is None

    def test_empty_string_returns_none(self):
        assert _clean_html("   ") is None

    def test_no_tags_unchanged(self):
        assert _clean_html("Plain text") == "Plain text"


class TestParsePublished:
    def test_rfc2822_format(self):
        entry = {"published": "Wed, 31 Jul 2024 10:30:00 +0530"}
        dt = _parse_published(entry)
        assert dt is not None
        assert isinstance(dt, datetime)

    def test_updated_field_fallback(self):
        entry = {"updated": "Tue, 30 Jul 2024 09:00:00 +0000"}
        dt = _parse_published(entry)
        assert dt is not None

    def test_no_date_returns_none(self):
        assert _parse_published({}) is None

    def test_invalid_date_returns_none(self):
        assert _parse_published({"published": "not-a-date"}) is None


# ── Integration: deduplication ────────────────────────────────────────────────

def _make_fake_entry(guid_id: str, title: str) -> dict:
    return {
        "id":        guid_id,
        "title":     title,
        "summary":   "Summary text.",
        "link":      f"https://example.com/{guid_id}",
        "published": "Wed, 31 Jul 2024 10:00:00 +0000",
    }


FAKE_FEED_XML = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Fund A rises 2%</title>
      <link>https://example.com/1</link>
      <guid>unique-guid-001</guid>
      <pubDate>Wed, 31 Jul 2024 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Fund B launches NFO</title>
      <link>https://example.com/2</link>
      <guid>unique-guid-002</guid>
      <pubDate>Wed, 31 Jul 2024 11:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
async def test_run_feed_inserts_new_articles(db):
    import backend.ingestion.news_scraper as mod
    from tests.conftest import TestSessionLocal
    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        scraper = NewsScraper()
        with patch(
            "backend.ingestion.news_scraper._fetch_feed_text",
            new=AsyncMock(return_value=FAKE_FEED_XML),
        ):
            count = await scraper.run_feed("https://fake.rss/feed", "test_source")

        assert count == 2
        result = await db.execute(
            select(NewsArticle).where(NewsArticle.source == "test_source")
        )
        rows = result.scalars().all()
        assert len(rows) == 2
    finally:
        mod.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_run_feed_deduplicates(db):
    """Running the same feed twice should not insert duplicate articles."""
    import backend.ingestion.news_scraper as mod
    from tests.conftest import TestSessionLocal
    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        scraper = NewsScraper()
        with patch(
            "backend.ingestion.news_scraper._fetch_feed_text",
            new=AsyncMock(return_value=FAKE_FEED_XML),
        ):
            first  = await scraper.run_feed("https://fake.rss/feed", "test_dedup")
            second = await scraper.run_feed("https://fake.rss/feed", "test_dedup")

        assert first == 2
        assert second == 0
    finally:
        mod.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_get_unscored_articles(db, sample_news):
    """Articles with no sentiment rows should appear in get_unscored_articles."""
    import backend.ingestion.news_scraper as mod
    from tests.conftest import TestSessionLocal
    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        # sample_news already has a sentiment row → should NOT appear as unscored
        # Insert a new article with no sentiment
        unscored_article = NewsArticle(
            guid="unscored-guid-999",
            source="test",
            title="No sentiment yet",
        )
        db.add(unscored_article)
        await db.commit()

        scraper = NewsScraper()
        articles = await scraper.get_unscored_articles(limit=50)
        guids = [a.guid for a in articles]
        assert "unscored-guid-999" in guids
    finally:
        mod.AsyncSessionLocal = original
