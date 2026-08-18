"""
Tests for backend/nlp/sentiment.py

Covers:
- VADER backend: positive / negative / neutral classification
- Sector keyword → category detection
- Scheme entity matching
- score_pending_articles end-to-end (mocked NLP model)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.nlp.sentiment import (
    SentimentPipeline,
    _VADERBackend,
    _detect_categories,
)


# ── Unit: VADER backend ───────────────────────────────────────────────────────

class TestVADERBackend:
    def setup_method(self):
        self.backend = _VADERBackend()

    def test_positive_text(self):
        result = self.backend.score("Excellent returns and strong performance this quarter!")
        assert result["label"] == "positive"
        assert result["compound"] > 0.05

    def test_negative_text(self):
        result = self.backend.score("Fund collapsed, massive losses, redemption pressure.")
        assert result["label"] == "negative"
        assert result["compound"] < -0.05

    def test_neutral_text(self):
        result = self.backend.score("The fund NAV was updated today.")
        assert result["label"] in ("neutral", "positive", "negative")
        # Key: all scores sum to ≈ 1
        total = result["positive"] + result["negative"] + result["neutral"]
        assert total == pytest.approx(1.0, abs=0.01)

    def test_returns_required_keys(self):
        result = self.backend.score("test")
        for key in ("label", "positive", "negative", "neutral", "compound"):
            assert key in result

    def test_compound_in_range(self):
        result = self.backend.score("Mixed signals in the market today.")
        assert -1.0 <= result["compound"] <= 1.0


# ── Unit: category detection ──────────────────────────────────────────────────

class TestDetectCategories:
    def test_defense_detected(self):
        cats = _detect_categories("HAL and Bharat Forge defense sector outlook")
        assert any("Defense" in c for c in cats)

    def test_banking_detected(self):
        cats = _detect_categories("HDFC Bank NPA rises, banking sector under pressure")
        assert any("Banking" in c for c in cats)

    def test_pharma_detected(self):
        cats = _detect_categories("Cipla reports strong pharma quarterly results")
        assert any("Pharma" in c for c in cats)

    def test_multiple_categories(self):
        cats = _detect_categories("Banking and pharma both rally after RBI announcement")
        assert len(cats) >= 2

    def test_no_match_returns_empty(self):
        cats = _detect_categories("Weather forecast for tomorrow in Mumbai")
        assert cats == []

    def test_deduplicates(self):
        cats = _detect_categories("HDFC Bank HDFC Bank banking banking")
        # should only appear once
        assert len(cats) == len(set(cats))


# ── Unit: SentimentPipeline VADER mode ───────────────────────────────────────

class TestSentimentPipelineVADER:
    def setup_method(self):
        self.pipeline = SentimentPipeline()
        # Force VADER backend for tests (no GPU / HuggingFace download needed)
        self.pipeline._backend = _VADERBackend()

    def test_score_text_returns_dict(self):
        result = self.pipeline.score_text("Fund performs well in volatile market.")
        assert isinstance(result, dict)
        assert "label" in result
        assert "compound" in result

    def test_score_text_empty_string(self):
        result = self.pipeline.score_text("")
        assert result["label"] in ("positive", "negative", "neutral")


# ── Integration: score_pending_articles ──────────────────────────────────────

@pytest.mark.asyncio
async def test_score_pending_articles_scores_unscored(db, sample_news):
    """
    score_pending_articles should assign a NewsSentiment row to any
    article that has none yet.
    """
    import backend.nlp.sentiment as mod
    from backend.db.models import NewsArticle, NewsSentiment
    from sqlalchemy import select
    from tests.conftest import TestSessionLocal

    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    # Add a second article with no sentiment
    unscored = NewsArticle(
        guid="pending-article-001",
        source="et_markets",
        title="Nifty 50 large cap funds see inflows",
    )
    db.add(unscored)
    await db.commit()

    # Patch the scraper's get_unscored_articles to return only our new article
    with patch(
        "backend.ingestion.news_scraper.NewsScraper.get_unscored_articles",
        return_value=[unscored],
    ):
        pipeline = SentimentPipeline()
        pipeline._backend = _VADERBackend()  # avoid HuggingFace download

        try:
            scored = await pipeline.score_pending_articles(limit=10)
            assert scored == 1

            rows = await db.execute(
                select(NewsSentiment).where(NewsSentiment.article_id == unscored.id)
            )
            sentiment_rows = rows.scalars().all()
            assert len(sentiment_rows) >= 1
        finally:
            mod.AsyncSessionLocal = original
