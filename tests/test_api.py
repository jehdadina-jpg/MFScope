"""
Tests for backend/api/main.py (FastAPI routes)

Uses httpx AsyncClient with the app wired to the in-memory test DB.
Covers:
- GET /health
- GET /api/v1/categories
- GET /api/v1/funds
- GET /api/v1/funds/{scheme_code}
- GET /api/v1/funds/{scheme_code}/nav
- GET /api/v1/scores/top
- 404 handling
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

# All heavy fixtures (sample_scheme, sample_score, etc.) are defined in conftest.py


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(api_client: AsyncClient):
    resp = await api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "timestamp" in body


# ── Categories ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_categories_returns_list(api_client: AsyncClient, sample_scheme):
    resp = await api_client.get("/api/v1/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_categories_contains_large_cap(api_client: AsyncClient, sample_scheme):
    resp = await api_client.get("/api/v1/categories")
    categories = [c["category"] for c in resp.json()]
    assert "Large Cap" in categories


# ── Fund list ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_funds_list_returns_page(api_client: AsyncClient, sample_scheme):
    resp = await api_client.get("/api/v1/funds")
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert "items" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_funds_list_category_filter(api_client: AsyncClient, sample_scheme):
    resp = await api_client.get("/api/v1/funds?category=Large+Cap")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        assert item["category"] == "Large Cap"


@pytest.mark.asyncio
async def test_funds_list_search(api_client: AsyncClient, sample_scheme):
    resp = await api_client.get("/api/v1/funds?search=Test+AMC")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("Test" in i["amc_name"] for i in items)


@pytest.mark.asyncio
async def test_funds_list_pagination(api_client: AsyncClient, sample_scheme):
    resp = await api_client.get("/api/v1/funds?page=1&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert len(body["items"]) <= 5


@pytest.mark.asyncio
async def test_funds_list_conviction_filter(
    api_client: AsyncClient, sample_scheme, sample_score
):
    resp = await api_client.get("/api/v1/funds?conviction=Buy")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        if item["conviction"] is not None:
            assert item["conviction"] == "Buy"


# ── Fund detail ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fund_detail_returns_scheme(
    api_client: AsyncClient, sample_scheme
):
    resp = await api_client.get(f"/api/v1/funds/{sample_scheme.scheme_code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheme"]["scheme_code"] == sample_scheme.scheme_code
    assert body["scheme"]["scheme_name"] == sample_scheme.scheme_name


@pytest.mark.asyncio
async def test_fund_detail_includes_score(
    api_client: AsyncClient, sample_scheme, sample_score
):
    resp = await api_client.get(f"/api/v1/funds/{sample_scheme.scheme_code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest_score"] is not None
    assert body["latest_score"]["composite_score"] == pytest.approx(74.5)
    assert body["latest_score"]["conviction"] == "Buy"


@pytest.mark.asyncio
async def test_fund_detail_includes_nav_history(
    api_client: AsyncClient, sample_scheme, sample_nav_series
):
    resp = await api_client.get(f"/api/v1/funds/{sample_scheme.scheme_code}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nav_history"]) > 0
    # Each point has nav_date and nav
    for point in body["nav_history"][:3]:
        assert "nav_date" in point
        assert "nav" in point


@pytest.mark.asyncio
async def test_fund_detail_404_for_unknown_code(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/funds/DOESNOTEXIST999")
    assert resp.status_code == 404


# ── NAV history endpoint ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nav_history_returns_list(
    api_client: AsyncClient, sample_scheme, sample_nav_series
):
    resp = await api_client.get(f"/api/v1/funds/{sample_scheme.scheme_code}/nav?days=90")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "nav_date" in data[0]
    assert "nav" in data[0]


@pytest.mark.asyncio
async def test_nav_history_404_for_unknown(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/funds/MISSING000/nav")
    assert resp.status_code == 404


# ── Top funds ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_top_funds_returns_list(
    api_client: AsyncClient, sample_scheme, sample_score
):
    resp = await api_client.get("/api/v1/scores/top?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 5


@pytest.mark.asyncio
async def test_top_funds_category_filter(
    api_client: AsyncClient, sample_scheme, sample_score
):
    resp = await api_client.get("/api/v1/scores/top?category=Large+Cap&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert item["category"] == "Large Cap"


@pytest.mark.asyncio
async def test_top_funds_sorted_by_score(
    api_client: AsyncClient, sample_scheme, sample_score
):
    resp = await api_client.get("/api/v1/scores/top?limit=20")
    data = resp.json()
    scores = [item["composite_score"] for item in data if item["composite_score"] is not None]
    assert scores == sorted(scores, reverse=True)
