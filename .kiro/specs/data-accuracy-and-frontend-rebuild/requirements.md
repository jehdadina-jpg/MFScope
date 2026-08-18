# Requirements Document

## Introduction

This specification addresses critical data accuracy issues in the MFScope mutual fund analysis platform and rebuilds the frontend with professional visualizations and insights. The system currently calculates trailing returns from insufficient data, producing misleading metrics. For example, a fund with only 1 year of NAV data incorrectly generates a 5-year return figure. The frontend also lacks proper data validation, risk visualization, and comparative insights that would showcase the platform's ML/AI capabilities.

The system SHALL provide accurate financial metrics with strict validation, never displaying metrics calculated from insufficient historical data. The frontend SHALL present fund data with professional-grade visualizations, comprehensive risk assessments, category comparisons, and clear ML-driven insights.

## Glossary

- **NAV**: Net Asset Value - the per-unit price of a mutual fund on a given date
- **Trailing Return**: Annualized percentage return calculated over a specific historical period (e.g., 1-month, 1-year, 5-year)
- **Risk Metric**: Statistical measures of fund volatility and risk (Sharpe ratio, Sortino ratio, alpha, beta, max drawdown, volatility)
- **Feature Builder**: Backend component (`backend/features/feature_builder.py`) that calculates all fund metrics and features
- **Fund Card**: UI component displaying a fund's summary information in the grid view
- **Fund Detail Page**: UI page showing comprehensive analysis of a single fund
- **Data Quality Indicator**: UI element showing whether a metric was calculated from sufficient data or marked as unavailable
- **Inception Date**: The date when a mutual fund was first launched
- **Buffer Days**: Additional days beyond the minimum period to account for market holidays and missing data points
- **Composite Score**: ML-generated 0-100 score representing overall fund attractiveness
- **SHAP Values**: Machine learning explainability values showing which features contributed to a score
- **Risk Level**: Categorical assessment (Low/Medium/High) of fund risk
- **Category**: Fund classification (Large Cap, Mid Cap, Small Cap, etc.)
- **Benchmark**: Market index used for comparison (Nifty 50, Sensex, etc.)

## Requirements

### Requirement 1: Data Validation for Return Calculations

**User Story:** As a system, I want to validate NAV history length before calculating returns, so that I only produce metrics from sufficient data

#### Acceptance Criteria

1. WHEN calculating a 1-month return, IF THE NAV history has fewer than 35 days of data, THEN THE Feature_Builder SHALL return NULL for the 1-month return
2. WHEN calculating a 3-month return, IF THE NAV history has fewer than 95 days of data, THEN THE Feature_Builder SHALL return NULL for the 3-month return
3. WHEN calculating a 6-month return, IF THE NAV history has fewer than 185 days of data, THEN THE Feature_Builder SHALL return NULL for the 6-month return
4. WHEN calculating a 1-year return, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for the 1-year return
5. WHEN calculating a 3-year return, IF THE NAV history has fewer than 1100 days of data, THEN THE Feature_Builder SHALL return NULL for the 3-year return
6. WHEN calculating a 5-year return, IF THE NAV history has fewer than 1850 days of data, THEN THE Feature_Builder SHALL return NULL for the 5-year return

### Requirement 2: Data Validation for Risk Metrics

**User Story:** As a system, I want to validate NAV history length before calculating risk metrics, so that statistical measures are reliable

#### Acceptance Criteria

1. WHEN calculating volatility, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for volatility
2. WHEN calculating Sharpe ratio, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for Sharpe ratio
3. WHEN calculating Sortino ratio, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for Sortino ratio
4. WHEN calculating alpha, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for alpha
5. WHEN calculating beta, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for beta
6. WHEN calculating maximum drawdown, IF THE NAV history has fewer than 370 days of data, THEN THE Feature_Builder SHALL return NULL for maximum drawdown

### Requirement 3: Fund Inception Date Tracking

**User Story:** As a user, I want to see when a fund was launched, so that I can assess fund maturity and data availability

#### Acceptance Criteria

1. THE Scheme model SHALL have an inception_date field storing the fund's launch date
2. WHEN displaying fund details, THE Frontend SHALL show the inception date with clear formatting
3. WHEN a fund has insufficient data for a metric, THE Frontend SHALL display the inception date to explain why the metric is unavailable

### Requirement 4: API Data Quality Response

**User Story:** As a frontend developer, I want the API to indicate data quality, so that the UI can display appropriate indicators

#### Acceptance Criteria

1. WHEN the API returns fund features, THE API SHALL include a data_quality object with flags for each metric category
2. THE data_quality object SHALL indicate whether returns are from sufficient data
3. THE data_quality object SHALL indicate whether risk metrics are from sufficient data
4. THE data_quality object SHALL indicate the number of days of NAV history available

### Requirement 5: Enhanced Fund Card UI

**User Story:** As a user, I want fund cards to display comprehensive information with visual hierarchy, so that I can quickly assess fund quality

#### Acceptance Criteria

1. WHEN displaying a fund card, THE Frontend SHALL show composite score with prominent visual styling
2. WHEN a metric is unavailable, THE Frontend SHALL display "N/A" or "Insufficient data" instead of empty space
3. THE Frontend SHALL display Sharpe ratio with visual prominence as a key risk-adjusted metric
4. THE Frontend SHALL show risk level (Low/Medium/High) with color-coded indicators
5. THE Frontend SHALL display category performance comparison (fund vs category average)
6. THE Frontend SHALL include larger performance charts with visible trend information

### Requirement 6: Advanced Data Visualizations

**User Story:** As a user, I want powerful data visualizations, so that I can understand fund performance and risk at a glance

#### Acceptance Criteria

1. WHEN displaying fund detail page, THE Frontend SHALL show performance charts with multiple timeframe options (1M, 3M, 6M, 1Y, 3Y, 5Y)
2. THE Frontend SHALL display a risk-return scatter plot comparing the fund to category peers
3. THE Frontend SHALL overlay category benchmark performance on the main chart
4. THE Frontend SHALL show trend indicators (momentum, moving average crossovers) visually
5. WHEN displaying risk metrics, THE Frontend SHALL show a visual risk breakdown with gauge or radial charts

### Requirement 7: Enhanced Filtering and Sorting

**User Story:** As a user, I want powerful filters and sorting options, so that I can find funds matching my criteria

#### Acceptance Criteria

1. THE Frontend SHALL provide risk level filtering (Low/Medium/High)
2. THE Frontend SHALL provide performance filtering (outperformers vs category)
3. THE Frontend SHALL provide manager tenure filtering options
4. THE Frontend SHALL provide AUM size bucket filtering options
5. WHEN sorting by any metric, THE Frontend SHALL handle NULL values by placing them last in the sort order

### Requirement 8: ML Insights Showcase

**User Story:** As a user, I want to see how ML drives fund scores, so that I trust the recommendations

#### Acceptance Criteria

1. WHEN displaying fund detail page, THE Frontend SHALL show composite score calculation breakdown by component (returns, consistency, cost, sentiment, stability)
2. THE Frontend SHALL display SHAP values in plain language explaining which factors drive the score
3. THE Frontend SHALL show risk assessment explanation with contributing factors
4. THE Frontend SHALL visualize sentiment impact with trend and volume indicators
5. WHEN a score changes over time, THE Frontend SHALL display a historical conviction timeline

### Requirement 9: Category Peer Comparison

**User Story:** As a user, I want to compare a fund to its category peers, so that I can assess relative performance

#### Acceptance Criteria

1. WHEN displaying fund detail page, THE Frontend SHALL show a category peer comparison section
2. THE Frontend SHALL display fund rank within category with visual percentile indicator
3. THE Frontend SHALL show category average metrics (returns, risk, expense ratio)
4. THE Frontend SHALL highlight when the fund outperforms or underperforms the category average
5. THE Frontend SHALL display the distribution of scores within the category

### Requirement 10: Proper "N/A" Handling Throughout UI

**User Story:** As a user, I want clear indication when data is insufficient, so that I don't misinterpret missing metrics

#### Acceptance Criteria

1. WHEN a return metric is NULL, THE Frontend SHALL display "N/A" with a tooltip explaining insufficient data
2. WHEN a risk metric is NULL, THE Frontend SHALL display "N/A" with a tooltip explaining insufficient data
3. WHEN displaying sparklines, IF THE NAV history is too short, THE Frontend SHALL show a message indicating insufficient history
4. THE Frontend SHALL use consistent styling for all "N/A" indicators across all components
5. WHEN hovering over "N/A", THE Frontend SHALL show the inception date and required data period

### Requirement 11: Performance Chart Enhancements

**User Story:** As a user, I want detailed performance charts, so that I can analyze fund behavior over time

#### Acceptance Criteria

1. THE Frontend SHALL display performance charts with larger dimensions (minimum 600px width)
2. THE Frontend SHALL allow toggling between line chart and candlestick chart views
3. THE Frontend SHALL overlay moving averages (50-day, 200-day) on the chart
4. WHEN benchmark data is available, THE Frontend SHALL overlay benchmark performance for comparison
5. THE Frontend SHALL display tooltips with precise values, dates, and percentage changes on hover

### Requirement 12: Risk Visualization Enhancement

**User Story:** As a user, I want comprehensive risk visualization, so that I can assess fund risk profile

#### Acceptance Criteria

1. THE Frontend SHALL display a risk gauge showing risk level (Low/Medium/High) with color coding
2. THE Frontend SHALL show a breakdown of risk components (volatility, drawdown, Sharpe ratio) in a visual grid
3. THE Frontend SHALL display maximum drawdown with a visual timeline showing when it occurred
4. THE Frontend SHALL compare fund risk metrics to category average risk metrics
5. WHEN risk metrics are unavailable, THE Frontend SHALL clearly indicate insufficient data

### Requirement 13: Data Refresh and Cache Invalidation

**User Story:** As a user, I want fresh data after triggering refresh, so that I see updated metrics immediately

#### Acceptance Criteria

1. WHEN a user triggers data refresh, THE System SHALL recalculate all features using the updated validation rules
2. THE System SHALL invalidate cached feature data for affected schemes
3. WHEN feature recalculation completes, THE API SHALL return updated metrics reflecting the new validation rules
4. THE Frontend SHALL show a loading indicator during recalculation
5. THE Frontend SHALL display a success message when fresh data is available

### Requirement 14: Validation Error Logging

**User Story:** As a developer, I want to log validation failures, so that I can monitor data quality issues

#### Acceptance Criteria

1. WHEN a return calculation is skipped due to insufficient data, THE Feature_Builder SHALL log the scheme_code and required days
2. WHEN a risk metric calculation is skipped due to insufficient data, THE Feature_Builder SHALL log the scheme_code and required days
3. THE System SHALL aggregate validation failure counts by metric type
4. THE System SHALL expose validation statistics via an admin endpoint
5. WHEN validation failures exceed a threshold, THE System SHALL log a warning message

### Requirement 15: Backward Compatibility

**User Story:** As a developer, I want the API to remain compatible, so that existing integrations continue working

#### Acceptance Criteria

1. WHEN returning fund features, THE API SHALL maintain all existing response fields
2. THE API SHALL add new fields (data_quality, inception_date) without removing existing fields
3. WHEN a metric is NULL, THE API SHALL return explicit null values (not omit the field)
4. THE API SHALL preserve response structure for fund cards, fund details, and category summaries
5. THE API SHALL maintain backward compatibility with the existing schema version
