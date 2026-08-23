"""
Sentiment Pipeline
==================
Scores news articles using either FinBERT (preferred) or VADER (lightweight
fallback).  The backend is selected via the SENTIMENT_BACKEND env var.

FinBERT  — ProsusAI/finbert on HuggingFace; returns positive/negative/neutral
            probabilities.  Loaded lazily so startup is fast.
VADER    — Rule-based lexicon model; instant, no GPU needed, less accurate for
            financial text but good enough for MVP.

Entity linking
--------------
Each article title + summary is matched against known:
  • Scheme names (exact substring, case-insensitive)
  • AMC names
  • Sector keywords → maps to a FundCategory

This lets us store per-scheme and per-category sentiment rows in
NewsSentiment, enabling rolling sentiment signals in the feature builder.

Public interface
----------------
    pipeline = SentimentPipeline()
    await pipeline.score_pending_articles(limit=200)
    result = pipeline.score_text("Adani Ports fund NAV falls 3%")
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select

from backend.config import settings
from backend.db.models import NewsArticle, NewsSentiment, Scheme, SentimentLabel
from backend.db.session import AsyncSessionLocal


# ── Sector keyword → category mapping ────────────────────────────────────────

_SECTOR_MAP: list[tuple[re.Pattern, str]] = [
    # Category strings must match the canonical vocabulary the schemes are
    # actually stored under — a tag that matches no scheme produces sentiment
    # rows that the feature builder can never join to.
    (re.compile(r"defen[cs]e|military|army|hal|drdo|bharat forge", re.I),
     "Sectoral - Defence"),
    (re.compile(r"psu|bhel|ongc|coal india|ntpc|power grid|public sector", re.I),
     "Sectoral - PSU"),
    (re.compile(r"bank|banking|nbfc|hdfc bank|icici bank|axis bank|"
                r"financial service|bfsi", re.I),
     "Sectoral - Banking & Financial"),
    (re.compile(r"pharma|drug|cipla|sun pharma|divi|healthcare|hospital", re.I),
     "Sectoral - Pharma & Healthcare"),
    (re.compile(r"it|infosys|tcs|wipro|hcl tech|tech mahindra|software", re.I),
     "Sectoral - Technology"),
    (re.compile(r"infra|infrastructure|larsen|l&t|highway|cement|steel", re.I),
     "Sectoral - Infrastructure"),
    (re.compile(r"fmcg|consumer|hindustan unilever|nestle|itc|dabur", re.I),
     "Sectoral - Consumption"),
    (re.compile(r"energy|oil|natural gas|bpcl|ioc|petroleum", re.I),
     "Sectoral - Energy & Resources"),
    (re.compile(r"auto|automobile|maruti|tata motors|manufactur", re.I),
     "Sectoral - Manufacturing & Auto"),
    (re.compile(r"nifty 50|sensex|large.?cap|bluechip", re.I), "Large Cap"),
    (re.compile(r"mid.?cap", re.I), "Mid Cap"),
    (re.compile(r"small.?cap", re.I), "Small Cap"),
    (re.compile(r"flexi.?cap", re.I), "Flexi Cap"),
    (re.compile(r"elss|tax sav|80c", re.I), "ELSS"),
    (re.compile(r"gilt|g-?sec|government bond|treasury", re.I), "Gilt"),
    (re.compile(r"liquid fund|overnight fund|money market", re.I), "Liquid"),
    (re.compile(r"gold", re.I), "Gold"),
    (re.compile(r"silver", re.I), "Silver"),
]


def _detect_categories(text: str) -> list[str]:
    """Return list of category values that the text likely refers to."""
    found: list[str] = []
    for pattern, cat in _SECTOR_MAP:
        if pattern.search(text):
            found.append(cat)
    return list(dict.fromkeys(found))  # deduplicate, preserve order


# ── VADER backend ─────────────────────────────────────────────────────────────

class _VADERBackend:
    def __init__(self) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._analyzer = SentimentIntensityAnalyzer()
        logger.info("VADER sentiment backend loaded.")

    def score(self, text: str) -> dict[str, float]:
        scores = self._analyzer.polarity_scores(text)
        compound: float = scores["compound"]
        if compound >= 0.05:
            label = SentimentLabel.POSITIVE.value
        elif compound <= -0.05:
            label = SentimentLabel.NEGATIVE.value
        else:
            label = SentimentLabel.NEUTRAL.value
        return {
            "label": label,
            "positive": scores["pos"],
            "negative": scores["neg"],
            "neutral": scores["neu"],
            "compound": compound,
        }


# ── FinBERT backend ───────────────────────────────────────────────────────────

class _FinBERTBackend:
    def __init__(self) -> None:
        import torch
        from transformers import pipeline as hf_pipeline

        device = 0 if torch.cuda.is_available() else -1
        logger.info(f"Loading FinBERT ({settings.sentiment_model}) on device={device} …")
        self._pipe = hf_pipeline(
            "text-classification",
            model=settings.sentiment_model,
            top_k=None,          # return all 3 labels
            device=device,
            truncation=True,
            max_length=512,
        )
        logger.info("FinBERT loaded.")

    def score(self, text: str) -> dict[str, float]:
        # Truncate to 512 chars to keep inference fast on CPU
        result: list[list[dict]] = self._pipe(text[:512])
        scores_raw: list[dict] = result[0] if isinstance(result[0], list) else result
        # Build lookup: label → score
        by_label = {item["label"].lower(): item["score"] for item in scores_raw}
        pos = by_label.get("positive", 0.0)
        neg = by_label.get("negative", 0.0)
        neu = by_label.get("neutral", 0.0)
        # Compound: positive − negative (in [-1, 1])
        compound = pos - neg
        if pos >= neg and pos >= neu:
            label = SentimentLabel.POSITIVE.value
        elif neg > pos and neg >= neu:
            label = SentimentLabel.NEGATIVE.value
        else:
            label = SentimentLabel.NEUTRAL.value
        return {
            "label": label,
            "positive": pos,
            "negative": neg,
            "neutral": neu,
            "compound": compound,
        }


# ── Pipeline ──────────────────────────────────────────────────────────────────

class SentimentPipeline:
    """
    Orchestrates sentiment scoring for NewsArticle rows.

    The underlying NLP model is loaded lazily on first call to `score_text`,
    so importing this class is cheap.
    """

    _backend: _VADERBackend | _FinBERTBackend | None = None

    def _get_backend(self) -> _VADERBackend | _FinBERTBackend:
        if self._backend is None:
            if settings.sentiment_backend.lower() == "vader":
                SentimentPipeline._backend = _VADERBackend()
            else:
                try:
                    SentimentPipeline._backend = _FinBERTBackend()
                except Exception as exc:
                    logger.warning(f"FinBERT load failed ({exc}); falling back to VADER.")
                    SentimentPipeline._backend = _VADERBackend()
        return self._backend  # type: ignore[return-value]

    def score_text(self, text: str) -> dict[str, float]:
        """Score a single text string. Returns label + probability scores."""
        return self._get_backend().score(text)

    # ── Batch processing ──────────────────────────────────────────────────────

    async def score_pending_articles(self, limit: int = 200) -> int:
        """
        Find articles without sentiment rows, score them, and persist results.
        Also performs entity linking to schemes and categories.
        Returns the number of articles scored.
        """
        from backend.ingestion.news_scraper import NewsScraper

        scraper = NewsScraper()
        articles = await scraper.get_unscored_articles(limit=limit)
        if not articles:
            logger.info("No unscored articles found.")
            return 0

        logger.info(f"Scoring {len(articles)} articles …")

        # Load scheme name lookup once
        scheme_lookup = await self._load_scheme_lookup()

        # Run NLP in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        scored = 0

        async with AsyncSessionLocal() as session:
            for article in articles:
                text = f"{article.title} {article.summary or ''}"
                try:
                    scores = await loop.run_in_executor(None, self.score_text, text)
                except Exception as exc:
                    logger.warning(f"Scoring failed for article {article.id}: {exc}")
                    continue

                # Determine linked scheme ids
                linked_scheme_ids = self._match_schemes(text, scheme_lookup)
                # Determine linked categories
                linked_categories = _detect_categories(text)

                sentiment_rows: list[NewsSentiment] = []

                if linked_scheme_ids:
                    for scheme_id in linked_scheme_ids:
                        sentiment_rows.append(NewsSentiment(
                            article_id=article.id,
                            scheme_id=scheme_id,
                            category=None,
                            sentiment_label=scores["label"],
                            positive_score=scores["positive"],
                            negative_score=scores["negative"],
                            neutral_score=scores["neutral"],
                            compound_score=scores["compound"],
                            model_used=settings.sentiment_backend,
                        ))
                elif linked_categories:
                    # No specific fund matched — store at category level
                    for cat in linked_categories:
                        sentiment_rows.append(NewsSentiment(
                            article_id=article.id,
                            scheme_id=None,
                            category=cat,
                            sentiment_label=scores["label"],
                            positive_score=scores["positive"],
                            negative_score=scores["negative"],
                            neutral_score=scores["neutral"],
                            compound_score=scores["compound"],
                            model_used=settings.sentiment_backend,
                        ))
                else:
                    # Generic market article — store without scheme/category link
                    sentiment_rows.append(NewsSentiment(
                        article_id=article.id,
                        scheme_id=None,
                        category=None,
                        sentiment_label=scores["label"],
                        positive_score=scores["positive"],
                        negative_score=scores["negative"],
                        neutral_score=scores["neutral"],
                        compound_score=scores["compound"],
                        model_used=settings.sentiment_backend,
                    ))

                session.add_all(sentiment_rows)
                scored += 1

            await session.commit()

        logger.info(f"Sentiment scoring complete: {scored} articles processed.")
        return scored

    async def _load_scheme_lookup(self) -> dict[str, int]:
        """
        Return a {lowercased_scheme_name: scheme_id} lookup dict.
        Used for entity linking article text → fund.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Scheme.id, Scheme.scheme_name, Scheme.amc_name)
                .where(Scheme.is_active == True)
            )
            rows = result.all()

        lookup: dict[str, int] = {}
        for row in rows:
            scheme_id, name, amc = row
            # Store key words from the scheme name (AMC name + first meaningful word)
            # We avoid super-short tokens to prevent false positives
            for token in [name, amc]:
                key = token.lower().strip()
                if len(key) >= 6:
                    lookup[key] = scheme_id
        return lookup

    def _match_schemes(self, text: str, lookup: dict[str, int]) -> list[int]:
        """Return scheme ids whose names appear as substrings in text."""
        text_lower = text.lower()
        matched: set[int] = set()
        for name_key, scheme_id in lookup.items():
            if name_key in text_lower:
                matched.add(scheme_id)
        return list(matched)
