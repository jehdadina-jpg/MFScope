"""
Tests for _compute_data_quality helper function in backend/api/main.py

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

Tests the data quality computation logic:
- Returns valid flag calculation based on NAV count thresholds
- Risk metrics valid flag calculation
- Proper inception_date propagation
- DataQuality object structure
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.api.main import _compute_data_quality
from backend.api.schemas import DataQuality
from backend.db.models import Scheme, FundCategory


# ── Unit Tests for _compute_data_quality ─────────────────────────────────────

def test_compute_data_quality_sufficient_data():
    """Test with sufficient NAV data (>= 370 days)."""
    scheme = Scheme(
        scheme_code="TEST001",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2020, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=1,
        scheme=scheme,
        nav_count=400
    )
    
    assert isinstance(result, DataQuality)
    assert result.nav_days_available == 400
    assert result.returns_valid is True
    assert result.risk_metrics_valid is True
    assert result.inception_date == date(2020, 1, 1)


def test_compute_data_quality_exactly_minimum():
    """Test with exactly 370 days (boundary case)."""
    scheme = Scheme(
        scheme_code="TEST002",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2023, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=2,
        scheme=scheme,
        nav_count=370
    )
    
    assert result.nav_days_available == 370
    assert result.returns_valid is True
    assert result.risk_metrics_valid is True
    assert result.inception_date == date(2023, 1, 1)


def test_compute_data_quality_insufficient_data():
    """Test with insufficient NAV data (< 370 days)."""
    scheme = Scheme(
        scheme_code="TEST003",
        scheme_name="Young Fund",
        amc_name="Test AMC",
        category=FundCategory.MID_CAP.value,
        inception_date=date(2023, 6, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=3,
        scheme=scheme,
        nav_count=200
    )
    
    assert result.nav_days_available == 200
    assert result.returns_valid is False
    assert result.risk_metrics_valid is False
    assert result.inception_date == date(2023, 6, 1)


def test_compute_data_quality_very_young_fund():
    """Test with very young fund (< 100 days)."""
    scheme = Scheme(
        scheme_code="TEST004",
        scheme_name="New Fund",
        amc_name="Test AMC",
        category=FundCategory.SMALL_CAP.value,
        inception_date=date.today() - timedelta(days=50),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=4,
        scheme=scheme,
        nav_count=50
    )
    
    assert result.nav_days_available == 50
    assert result.returns_valid is False
    assert result.risk_metrics_valid is False


def test_compute_data_quality_no_inception_date():
    """Test with scheme that has no inception_date."""
    scheme = Scheme(
        scheme_code="TEST005",
        scheme_name="Fund Without Inception",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=None,
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=5,
        scheme=scheme,
        nav_count=500
    )
    
    assert result.nav_days_available == 500
    assert result.returns_valid is True
    assert result.risk_metrics_valid is True
    assert result.inception_date is None


def test_compute_data_quality_zero_nav():
    """Test with zero NAV records."""
    scheme = Scheme(
        scheme_code="TEST006",
        scheme_name="Empty Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2024, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=6,
        scheme=scheme,
        nav_count=0
    )
    
    assert result.nav_days_available == 0
    assert result.returns_valid is False
    assert result.risk_metrics_valid is False
    assert result.inception_date == date(2024, 1, 1)


def test_compute_data_quality_boundary_minus_one():
    """Test with 369 days (one day below threshold)."""
    scheme = Scheme(
        scheme_code="TEST007",
        scheme_name="Almost There Fund",
        amc_name="Test AMC",
        category=FundCategory.FLEXI_CAP.value,
        inception_date=date(2023, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=7,
        scheme=scheme,
        nav_count=369
    )
    
    assert result.nav_days_available == 369
    assert result.returns_valid is False
    assert result.risk_metrics_valid is False


def test_compute_data_quality_large_nav_count():
    """Test with very large NAV count (mature fund)."""
    scheme = Scheme(
        scheme_code="TEST008",
        scheme_name="Mature Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2010, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=8,
        scheme=scheme,
        nav_count=3650  # ~10 years
    )
    
    assert result.nav_days_available == 3650
    assert result.returns_valid is True
    assert result.risk_metrics_valid is True
    assert result.inception_date == date(2010, 1, 1)


# ── Property-Based Tests ──────────────────────────────────────────────────────

@pytest.mark.parametrize("nav_count", [0, 100, 200, 300, 369, 370, 371, 500, 1000, 2000])
def test_compute_data_quality_threshold_consistency(nav_count):
    """
    **Feature: data-accuracy-and-frontend-rebuild, Property 3**
    
    Property: For any NAV count, returns_valid and risk_metrics_valid
    should BOTH be True if and only if nav_count >= 370.
    """
    scheme = Scheme(
        scheme_code="PROP_TEST",
        scheme_name="Property Test Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2020, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=999,
        scheme=scheme,
        nav_count=nav_count
    )
    
    # Both flags should match the threshold
    expected_valid = nav_count >= 370
    assert result.returns_valid == expected_valid, \
        f"returns_valid should be {expected_valid} for nav_count={nav_count}"
    assert result.risk_metrics_valid == expected_valid, \
        f"risk_metrics_valid should be {expected_valid} for nav_count={nav_count}"
    
    # NAV count should match input
    assert result.nav_days_available == nav_count


@pytest.mark.parametrize("inception_date", [
    date(2020, 1, 1),
    date(2023, 6, 15),
    date(2024, 1, 1),
    None,
])
def test_compute_data_quality_inception_date_propagation(inception_date):
    """
    Property: The inception_date in the returned DataQuality object
    should always match the scheme's inception_date.
    """
    scheme = Scheme(
        scheme_code="PROP_TEST",
        scheme_name="Property Test Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=inception_date,
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=999,
        scheme=scheme,
        nav_count=400
    )
    
    assert result.inception_date == inception_date, \
        "inception_date should be propagated correctly"


# ── Edge Cases ────────────────────────────────────────────────────────────────

def test_compute_data_quality_negative_nav_count_invalid():
    """Test that negative nav_count is handled (though shouldn't occur in practice)."""
    scheme = Scheme(
        scheme_code="TEST_NEG",
        scheme_name="Edge Case Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2020, 1, 1),
        is_active=True,
    )
    
    # This is an edge case that shouldn't happen but tests robustness
    result = _compute_data_quality(
        scheme_id=999,
        scheme=scheme,
        nav_count=-1
    )
    
    # Negative count should fail validation
    assert result.returns_valid is False
    assert result.risk_metrics_valid is False


def test_compute_data_quality_returns_correct_type():
    """Verify the function returns a DataQuality object."""
    scheme = Scheme(
        scheme_code="TEST_TYPE",
        scheme_name="Type Test Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        inception_date=date(2020, 1, 1),
        is_active=True,
    )
    
    result = _compute_data_quality(
        scheme_id=1,
        scheme=scheme,
        nav_count=400
    )
    
    assert isinstance(result, DataQuality)
    assert hasattr(result, 'nav_days_available')
    assert hasattr(result, 'returns_valid')
    assert hasattr(result, 'risk_metrics_valid')
    assert hasattr(result, 'inception_date')
