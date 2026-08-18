"""
Tests for schema updates in Task 3.2:
- FundCardOut now includes data_quality and sharpe_ratio fields
- FundFeaturesOut now includes data_quality field
"""
from __future__ import annotations

from datetime import date

import pytest
from backend.api.schemas import DataQuality, FundCardOut, FundFeaturesOut, NAVPoint


def test_fund_card_out_has_data_quality_field():
    """Test that FundCardOut has the new data_quality field."""
    fund_card = FundCardOut(
        id=1,
        scheme_code="TEST001",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category="Large Cap",
        composite_score=75.5,
        conviction="Buy",
        return_1y=15.5,
        return_3y=12.3,
        sharpe_ratio=1.2,
        expense_ratio=0.5,
        aum_crore=1000.0,
        risk_score=50.0,
        risk_level="Medium",
        nav_sparkline=[],
        data_quality=DataQuality(
            nav_days_available=400,
            returns_valid=True,
            risk_metrics_valid=True,
            inception_date=date(2020, 1, 1)
        )
    )
    
    assert fund_card.data_quality is not None
    assert fund_card.data_quality.nav_days_available == 400
    assert fund_card.data_quality.returns_valid is True
    assert fund_card.data_quality.risk_metrics_valid is True


def test_fund_card_out_has_sharpe_ratio_field():
    """Test that FundCardOut has the new sharpe_ratio field."""
    fund_card = FundCardOut(
        id=1,
        scheme_code="TEST001",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category="Large Cap",
        sharpe_ratio=1.5,
    )
    
    assert fund_card.sharpe_ratio == 1.5


def test_fund_card_out_allows_null_data_quality():
    """Test that FundCardOut allows None for data_quality field (backward compatibility)."""
    fund_card = FundCardOut(
        id=1,
        scheme_code="TEST001",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category="Large Cap",
        data_quality=None
    )
    
    assert fund_card.data_quality is None


def test_fund_card_out_allows_null_sharpe_ratio():
    """Test that FundCardOut allows None for sharpe_ratio field."""
    fund_card = FundCardOut(
        id=1,
        scheme_code="TEST001",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category="Large Cap",
        sharpe_ratio=None
    )
    
    assert fund_card.sharpe_ratio is None


def test_fund_features_out_has_data_quality_field():
    """Test that FundFeaturesOut has the new data_quality field."""
    features = FundFeaturesOut(
        feature_date=date(2024, 1, 15),
        return_1m=2.0,
        return_3m=5.0,
        return_6m=10.0,
        return_1y=15.0,
        return_3y=12.0,
        return_5y=10.0,
        volatility_1y=14.0,
        sharpe_1y=1.2,
        sortino_1y=1.5,
        alpha_1y=2.0,
        beta_1y=0.95,
        max_drawdown_1y=-8.0,
        sentiment_7d=0.1,
        sentiment_30d=0.08,
        news_volume_7d=5.0,
        data_quality=DataQuality(
            nav_days_available=500,
            returns_valid=True,
            risk_metrics_valid=True,
            inception_date=date(2020, 1, 1)
        )
    )
    
    assert features.data_quality is not None
    assert features.data_quality.nav_days_available == 500
    assert features.data_quality.returns_valid is True
    assert features.data_quality.risk_metrics_valid is True


def test_fund_features_out_allows_null_data_quality():
    """Test that FundFeaturesOut allows None for data_quality field (backward compatibility)."""
    features = FundFeaturesOut(
        feature_date=date(2024, 1, 15),
        return_1m=None,
        return_3m=None,
        return_6m=None,
        return_1y=None,
        return_3y=None,
        return_5y=None,
        volatility_1y=None,
        sharpe_1y=None,
        sortino_1y=None,
        alpha_1y=None,
        beta_1y=None,
        max_drawdown_1y=None,
        sentiment_7d=None,
        sentiment_30d=None,
        news_volume_7d=None,
        data_quality=None
    )
    
    assert features.data_quality is None


def test_data_quality_schema():
    """Test that DataQuality schema works correctly."""
    data_quality = DataQuality(
        nav_days_available=365,
        returns_valid=True,
        risk_metrics_valid=False,
        inception_date=date(2022, 6, 15)
    )
    
    assert data_quality.nav_days_available == 365
    assert data_quality.returns_valid is True
    assert data_quality.risk_metrics_valid is False
    assert data_quality.inception_date == date(2022, 6, 15)


def test_data_quality_allows_null_inception_date():
    """Test that DataQuality allows None for inception_date."""
    data_quality = DataQuality(
        nav_days_available=365,
        returns_valid=True,
        risk_metrics_valid=True,
        inception_date=None
    )
    
    assert data_quality.inception_date is None


def test_fund_card_out_backward_compatibility():
    """Test that all existing fields are still present and work correctly."""
    fund_card = FundCardOut(
        id=1,
        scheme_code="TEST001",
        scheme_name="Test Fund",
        amc_name="Test AMC",
        category="Large Cap",
        composite_score=75.5,
        conviction="Buy",
        return_1y=15.5,
        return_3y=12.3,
        expense_ratio=0.5,
        aum_crore=1000.0,
        risk_score=50.0,
        risk_level="Medium",
        nav_sparkline=[
            NAVPoint(nav_date=date(2024, 1, 1), nav=100.0),
            NAVPoint(nav_date=date(2024, 1, 2), nav=101.0),
        ]
    )
    
    # Verify all existing fields work
    assert fund_card.id == 1
    assert fund_card.scheme_code == "TEST001"
    assert fund_card.scheme_name == "Test Fund"
    assert fund_card.amc_name == "Test AMC"
    assert fund_card.category == "Large Cap"
    assert fund_card.composite_score == 75.5
    assert fund_card.conviction == "Buy"
    assert fund_card.return_1y == 15.5
    assert fund_card.return_3y == 12.3
    assert fund_card.expense_ratio == 0.5
    assert fund_card.aum_crore == 1000.0
    assert fund_card.risk_score == 50.0
    assert fund_card.risk_level == "Medium"
    assert len(fund_card.nav_sparkline) == 2


def test_fund_features_out_backward_compatibility():
    """Test that all existing fields in FundFeaturesOut are still present and work correctly."""
    features = FundFeaturesOut(
        feature_date=date(2024, 1, 15),
        return_1m=2.0,
        return_3m=5.0,
        return_6m=10.0,
        return_1y=15.0,
        return_3y=12.0,
        return_5y=10.0,
        volatility_1y=14.0,
        sharpe_1y=1.2,
        sortino_1y=1.5,
        alpha_1y=2.0,
        beta_1y=0.95,
        max_drawdown_1y=-8.0,
        sentiment_7d=0.1,
        sentiment_30d=0.08,
        news_volume_7d=5.0,
    )
    
    # Verify all existing fields work
    assert features.feature_date == date(2024, 1, 15)
    assert features.return_1m == 2.0
    assert features.return_3m == 5.0
    assert features.return_6m == 10.0
    assert features.return_1y == 15.0
    assert features.return_3y == 12.0
    assert features.return_5y == 10.0
    assert features.volatility_1y == 14.0
    assert features.sharpe_1y == 1.2
    assert features.sortino_1y == 1.5
    assert features.alpha_1y == 2.0
    assert features.beta_1y == 0.95
    assert features.max_drawdown_1y == -8.0
    assert features.sentiment_7d == 0.1
    assert features.sentiment_30d == 0.08
    assert features.news_volume_7d == 5.0
