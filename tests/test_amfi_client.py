"""
Tests for backend/ingestion/amfi_client.py

Covers:
- NAVAll.txt parsing  (unit — no network)
- Category inference from scheme name
- Plan / option type inference
- DB upsert logic (integration with in-memory SQLite)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.db.models import NAVRecord, Scheme
from backend.ingestion.amfi_client import (
    AMFIClient,
    _infer_category,
    _infer_option,
    _infer_plan,
    _parse_nav_date,
)


# ── Unit: parsing helpers ─────────────────────────────────────────────────────

class TestParseNavDate:
    def test_dd_mon_yyyy(self):
        assert _parse_nav_date("31-Jul-2024") == date(2024, 7, 31)

    def test_dd_slash_mm_slash_yyyy(self):
        assert _parse_nav_date("15/08/2024") == date(2024, 8, 15)

    def test_iso_format(self):
        assert _parse_nav_date("2024-01-05") == date(2024, 1, 5)

    def test_leading_trailing_whitespace(self):
        assert _parse_nav_date("  31-Jul-2024  ") == date(2024, 7, 31)

    def test_invalid_returns_none(self):
        assert _parse_nav_date("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert _parse_nav_date("") is None


class TestInferCategory:
    def test_large_cap(self):
        from backend.db.models import FundCategory
        assert _infer_category("HDFC Large Cap Fund - Direct Growth") == FundCategory.LARGE_CAP

    def test_mid_cap(self):
        from backend.db.models import FundCategory
        assert _infer_category("Axis Mid Cap Fund - Regular Growth") == FundCategory.MID_CAP

    def test_defense_sector(self):
        from backend.db.models import FundCategory
        assert _infer_category("SBI Defense Fund") == FundCategory.DEFENSE

    def test_elss(self):
        from backend.db.models import FundCategory
        assert _infer_category("Mirae Asset Tax Saver Fund") == FundCategory.ELSS

    def test_liquid(self):
        from backend.db.models import FundCategory
        assert _infer_category("Nippon India Liquid Fund") == FundCategory.LIQUID

    def test_unknown_falls_back_to_other(self):
        from backend.db.models import FundCategory
        assert _infer_category("XYZ Unknown Scheme 2024") == FundCategory.OTHER


class TestInferPlanOption:
    def test_direct_plan(self):
        assert _infer_plan("SBI Bluechip Fund - Direct Growth") == "Direct"

    def test_regular_plan(self):
        assert _infer_plan("SBI Bluechip Fund - Regular Growth") == "Regular"

    def test_growth_option(self):
        assert _infer_option("HDFC Top 100 Fund - Direct Growth") == "Growth"

    def test_idcw_option(self):
        assert _infer_option("HDFC Top 100 Fund - IDCW Payout") == "Dividend"


# ── Unit: NAVAll.txt parser ───────────────────────────────────────────────────

NAV_ALL_SAMPLE = """\
Open Ended Schemes(Equity Scheme - Large Cap Fund)
Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
119551;INF209K01YX2;INF209K01YY0;Aditya Birla Sun Life Large Cap Fund - Direct Growth;98.7654;31-Jul-2024
119552;INF209K01ZA0;INF209K01ZB8;Aditya Birla Sun Life Large Cap Fund - Regular Growth;92.1234;31-Jul-2024
;;;;;Not a valid row
JUNK;JUNK;JUNK;JUNK;NAV;Date
"""


class TestParseNavAll:
    def test_parses_valid_rows(self):
        client = AMFIClient()
        records = client._parse_nav_all(NAV_ALL_SAMPLE)
        assert len(records) == 2

    def test_scheme_code_extracted(self):
        client = AMFIClient()
        records = client._parse_nav_all(NAV_ALL_SAMPLE)
        assert records[0]["scheme_code"] == "119551"

    def test_nav_value_parsed(self):
        client = AMFIClient()
        records = client._parse_nav_all(NAV_ALL_SAMPLE)
        assert records[0]["nav"] == pytest.approx(98.7654)

    def test_date_parsed(self):
        client = AMFIClient()
        records = client._parse_nav_all(NAV_ALL_SAMPLE)
        assert records[0]["nav_date"] == date(2024, 7, 31)

    def test_isin_extracted(self):
        client = AMFIClient()
        records = client._parse_nav_all(NAV_ALL_SAMPLE)
        assert records[0]["isin_growth"] == "INF209K01YX2"

    def test_invalid_rows_skipped(self):
        client = AMFIClient()
        records = client._parse_nav_all(NAV_ALL_SAMPLE)
        # Only 2 valid numeric-code rows
        assert all(r["scheme_code"].isdigit() for r in records)

    def test_empty_content_returns_empty_list(self):
        client = AMFIClient()
        assert client._parse_nav_all("") == []


# ── Integration: DB upsert ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_creates_scheme_and_nav(db):
    """_upsert_nav_records should create a Scheme + NAVRecord if they don't exist."""
    from tests.conftest import TestSessionLocal
    # Monkey-patch AsyncSessionLocal in the module under test
    import backend.ingestion.amfi_client as mod
    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        client = AMFIClient()
        records = [
            {
                "scheme_code": "888001",
                "isin_growth": "INF000K00001",
                "isin_div": None,
                "scheme_name": "Test Fund - Direct Growth",
                "nav": 55.1234,
                "nav_date": date(2024, 7, 31),
            }
        ]
        count = await client._upsert_nav_records(records)
        assert count == 1

        # Verify in DB
        scheme = await db.scalar(select(Scheme).where(Scheme.scheme_code == "888001"))
        assert scheme is not None
        nav_row = await db.scalar(
            select(NAVRecord).where(NAVRecord.scheme_id == scheme.id)
        )
        assert nav_row is not None
        assert float(nav_row.nav) == pytest.approx(55.1234)
    finally:
        mod.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_upsert_is_idempotent(db):
    """Running the same upsert twice should not duplicate NAVRecord rows."""
    import backend.ingestion.amfi_client as mod
    from tests.conftest import TestSessionLocal
    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        client = AMFIClient()
        records = [
            {
                "scheme_code": "888002",
                "isin_growth": None,
                "isin_div": None,
                "scheme_name": "Idempotent Test Fund",
                "nav": 100.0,
                "nav_date": date(2024, 8, 1),
            }
        ]
        first  = await client._upsert_nav_records(records)
        second = await client._upsert_nav_records(records)
        assert first == 1
        assert second == 0  # already exists, no new row
    finally:
        mod.AsyncSessionLocal = original
