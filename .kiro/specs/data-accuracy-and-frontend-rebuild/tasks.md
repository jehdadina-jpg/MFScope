# Implementation Plan: Data Accuracy and Frontend Rebuild

## Overview

This implementation rebuilds MFScope's feature calculation system with strict data validation to ensure metrics are only calculated from sufficient historical data, and enhances the frontend with professional-grade visualizations, ML insights showcase, and comprehensive data quality indicators. The plan follows 10 phases sequenced to minimize dependencies and enable early validation of core changes.

## Tasks

### Phase 1: Backend Validation Foundation

- [x] 1.1 Add validation constants and helper functions to feature_builder.py
  - Define minimum required days constants (MIN_DAYS_1M = 35, MIN_DAYS_3M = 95, MIN_DAYS_6M = 185, MIN_DAYS_1Y = 370, MIN_DAYS_3Y = 1100, MIN_DAYS_5Y = 1850)
  - Implement `_validate_nav_length(series: pd.Series, required_days: int) -> bool` helper function
  - Implement `_trailing_return_validated(series: pd.Series, days: int, min_required: int) -> float | None` function
  - Add validation helper for risk metrics: `_risk_metrics_validated(nav_1y: pd.Series) -> bool`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ]* 1.2 Write property tests for validation logic
  - **Property 1: Return Validation Threshold Compliance** - For any NAV series and return period, validate NULL returned when insufficient data
  - **Property 2: Risk Metric Validation Threshold Compliance** - For any NAV series < 370 days, all risk metrics return NULL
  - Use hypothesis library with minimum 100 iterations per property
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 1.3 Integrate validation into feature calculation pipeline
  - Modify `build_features()` method to call validation functions before each metric calculation
  - Update return calculations (r1m, r3m, r6m, r1y, r3y, r5y) to use `_trailing_return_validated()`
  - Update risk metric calculations (volatility, Sharpe, Sortino, MDD, alpha, beta) with validation check
  - Ensure NULL is stored in database when validation fails
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 1.4 Add validation failure logging
  - Add debug-level logging when validation fails with scheme_code, metric name, available days, required days
  - Use structured logging format for easy parsing
  - _Requirements: 14.1, 14.2_

- [ ]* 1.5 Write unit tests for validation integration
  - Test feature calculation with insufficient data returns NULL for returns
  - Test feature calculation with insufficient data returns NULL for risk metrics
  - Test feature calculation with sufficient data returns calculated values
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 1.6 Checkpoint - Run validation tests and verify logging
  - Ensure all property tests pass
  - Ensure all unit tests pass
  - Verify debug logging appears correctly
  - Ask the user if questions arise

### Phase 2: Database Schema Update

- [x] 2.1 Create Alembic migration for inception_date field
  - Add nullable `inception_date` column of type Date to `scheme` table
  - Add index on `inception_date` for query performance
  - _Requirements: 3.1_

- [x] 2.2 Write data migration script to populate inception_date
  - For each scheme, query earliest NAV date from `nav_record` table
  - Update `scheme.inception_date` with earliest NAV date
  - Log schemes where inception_date cannot be determined
  - _Requirements: 3.1_

- [x] 2.3 Update Scheme model in backend/db/models.py
  - Add `inception_date: Mapped[date | None] = mapped_column(Date, index=True)` field
  - Update model documentation
  - _Requirements: 3.1_

- [x] 2.4 Test migration on staging database
  - Run migration up and down to verify reversibility
  - Verify inception dates populated correctly
  - Check query performance with index
  - _Requirements: 3.1_

- [x] 2.5 Checkpoint - Database migration validation complete
  - Ensure all schemes have inception_date populated
  - Ensure migration is reversible
  - Ask the user if questions arise

### Phase 3: API Schema Enhancement

- [x] 3.1 Add DataQuality schema to backend/api/schemas.py
  - Create `DataQuality(BaseModel)` with fields: nav_days_available (int), returns_valid (bool), risk_metrics_valid (bool), inception_date (date | None)
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 3.2 Update FundCardOut and FundFeaturesOut schemas
  - Add `data_quality: DataQuality | None = None` field to FundCardOut
  - Add `data_quality: DataQuality | None = None` field to FundFeaturesOut
  - Add `sharpe_ratio: float | None` field to FundCardOut
  - Ensure all existing fields remain unchanged for backward compatibility
  - _Requirements: 4.1, 5.3, 15.1, 15.2_

- [x] 3.3 Implement _compute_data_quality() helper in backend/api/main.py
  - Create function that accepts scheme_id, scheme object, and nav_count
  - Calculate returns_valid as nav_count >= 370
  - Calculate risk_metrics_valid as nav_count >= 370
  - Return DataQuality object with all fields
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ]* 3.4 Write property tests for data quality calculation
  - **Property 3: Data Quality Object Correctness** - For any fund, data_quality flags match actual NAV history length
  - Use hypothesis to generate various nav_count values
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 3.5 Integrate data_quality into /api/v1/funds endpoint
  - Query nav_count for each scheme in the fund list
  - Call _compute_data_quality() for each fund
  - Include data_quality in FundCardOut response
  - _Requirements: 4.1_

- [x] 3.6 Integrate data_quality into /api/v1/funds/{scheme_code} endpoint
  - Query nav_count for the scheme
  - Call _compute_data_quality() for the fund
  - Include data_quality in FundFeaturesOut response
  - _Requirements: 4.1_

- [ ]* 3.7 Write API integration tests for data quality
  - Test /api/v1/funds returns data_quality for all funds
  - Test /api/v1/funds/{scheme_code} returns data_quality
  - Test backward compatibility: all existing fields present
  - **Property 7: API Backward Compatibility** - All existing fields present, new fields added, nulls explicit
  - _Requirements: 4.1, 15.1, 15.2, 15.3, 15.4_

- [x] 3.8 Checkpoint - API schema changes complete
  - Ensure all API endpoints return data_quality
  - Ensure backward compatibility maintained
  - Ask the user if questions arise

### Phase 4: Frontend Foundation Components

- [x] 4.1 Create InsufficientDataTooltip component
  - Create frontend/src/components/InsufficientDataTooltip.tsx
  - Accept props: metric (string), requiredDays (number), availableDays (number), inceptionDate (Date | undefined)
  - Render "N/A" text with tooltip
  - Tooltip shows: "{metric} requires {requiredDays} days of data"
  - Tooltip shows: "Fund has {availableDays} days available"
  - If inception date available, show: "Fund launched on {inceptionDate}"
  - Use consistent styling and accessibility (ARIA labels)
  - _Requirements: 10.1, 10.2, 10.4, 10.5_

- [ ]* 4.2 Write unit tests for InsufficientDataTooltip
  - Test component renders "N/A" text
  - Test tooltip appears on hover
  - Test tooltip content includes metric name, required days, available days
  - Test inception date display when provided
  - **Property 4: Frontend Null Metric Display** - For any null metric, "N/A" with tooltip appears
  - _Requirements: 10.1, 10.2, 10.4, 10.5_

- [x] 4.3 Create RiskGauge component
  - Create frontend/src/components/RiskGauge.tsx
  - Accept props: level (string | null), score (number | null), size ('sm' | 'md' | 'lg')
  - Render radial gauge visualization with color-coding (green=Low, yellow=Medium, red=High)
  - Show numeric score on hover
  - Fall back to "N/A" if data unavailable
  - Use accessible color contrast meeting WCAG AA
  - _Requirements: 5.4, 12.1_

- [ ]* 4.4 Write unit tests for RiskGauge
  - Test component renders gauge for valid data
  - Test component renders "N/A" for null data
  - Test color-coding matches risk level
  - Test tooltip shows numeric score
  - _Requirements: 5.4, 12.1_

- [x] 4.5 Create utility functions for data quality checks
  - Create frontend/src/utils/dataQuality.ts
  - Implement `isMetricAvailable(value: number | null): boolean`
  - Implement `getRequiredDays(metric: string): number` mapping metric names to required days
  - Implement `formatMetricValue(value: number | null, format: string): string` with null handling
  - _Requirements: 10.1, 10.2_

- [ ]* 4.6 Write unit tests for data quality utility functions
  - Test isMetricAvailable returns correct boolean
  - Test getRequiredDays returns correct thresholds
  - Test formatMetricValue handles null correctly
  - _Requirements: 10.1, 10.2_

- [x] 4.7 Checkpoint - Foundation components complete
  - Ensure all components render correctly
  - Ensure all tests pass
  - Ask the user if questions arise

### Phase 5: Enhanced FundCard Component

- [ ] 5.1 Update FundCard component to display Sharpe ratio
  - Modify frontend/src/components/FundCard.tsx
  - Add Sharpe ratio to metrics grid with visual prominence (highlighted styling)
  - Use InsufficientDataTooltip if Sharpe ratio is null
  - _Requirements: 5.3_

- [ ] 5.2 Add data quality indicators to FundCard
  - Check `fund.data_quality?.returns_valid` flag
  - Display InsufficientDataBadge component when returns_valid is false
  - Add visual styling to distinguish cards with insufficient data
  - _Requirements: 4.1, 5.2, 10.1_

- [ ] 5.3 Integrate InsufficientDataTooltip for all null metrics
  - Replace empty displays with InsufficientDataTooltip for return_1y, return_3y, return_5y
  - Replace empty displays with InsufficientDataTooltip for sharpe_ratio, volatility
  - Pass data_quality information to tooltips
  - _Requirements: 10.1, 10.2, 10.4, 10.5_

- [ ] 5.4 Add category comparison display
  - Accept categoryAverage prop in FundCard
  - Create CategoryComparison sub-component showing fund return vs category average
  - Show visual indicator (arrow up/down) when fund outperforms/underperforms
  - _Requirements: 5.5, 9.4_

- [ ]* 5.5 Write property tests for FundCard null handling
  - **Property 4: Frontend Null Metric Display** - For any null metric, "N/A" with tooltip appears
  - Use fast-check to generate FundCardProps with various null combinations
  - Assert "N/A" renders for null values
  - Assert tooltips contain correct information
  - _Requirements: 10.1, 10.2, 10.5_

- [ ] 5.6 Enhance sparkline size and styling
  - Increase PerformanceChart dimensions in FundCard
  - Add trend indicators (arrow, color coding)
  - Handle insufficient sparkline data (< 10 points) with message
  - _Requirements: 5.6, 10.3_

- [ ]* 5.7 Write unit tests for sparkline insufficient data handling
  - **Property 12: Sparkline Insufficient Data Handling** - For sparkline data < 10 points, show message instead of rendering
  - Test sparkline renders for sufficient data
  - Test message displays for insufficient data
  - _Requirements: 10.3_

- [ ]* 5.8 Write snapshot tests for FundCard variants
  - Test FundCard with all data available
  - Test FundCard with some metrics null
  - Test FundCard with insufficient data badge
  - Test FundCard with category comparison
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 5.9 Checkpoint - FundCard enhancements complete
  - Ensure FundCard displays all new features correctly
  - Ensure null handling works consistently
  - Ensure all tests pass
  - Ask the user if questions arise

### Phase 6: Advanced Visualization Components

- [ ] 6.1 Create PerformanceChart component with timeframe selector
  - Create frontend/src/components/PerformanceChart.tsx
  - Accept props: navHistory (NAVPoint[]), timeframe ('1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y'), benchmark (NAVPoint[] | undefined), movingAverages (object | undefined), showTrend (boolean)
  - Implement Recharts line chart with minimum 600px width
  - Add timeframe selector buttons
  - Add tooltip with precise values, dates, and percentage changes
  - _Requirements: 6.1, 11.1, 11.5_

- [ ] 6.2 Implement benchmark overlay functionality
  - Add benchmark line overlay when benchmark prop provided
  - Use distinct color for benchmark line
  - Add legend distinguishing fund and benchmark
  - _Requirements: 6.3, 11.4_

- [ ]* 6.3 Write property test for benchmark conditional rendering
  - **Property 10: Benchmark Overlay Conditional Rendering** - Benchmark overlay presence matches data availability
  - Use fast-check to generate scenarios with/without benchmark data
  - Assert overlay renders only when benchmark provided
  - _Requirements: 6.3, 11.4_

- [ ] 6.4 Add moving average overlays to PerformanceChart
  - Implement MA50 and MA200 calculation if not provided
  - Render moving average lines with distinct styling (dashed, lighter color)
  - Add legend for moving averages
  - _Requirements: 11.3_

- [ ] 6.5 Create PeerComparisonChart scatter plot component
  - Create frontend/src/components/PeerComparisonChart.tsx
  - Accept props: fund (object with return1y, risk, name), peers (array), categoryAverage (object)
  - Implement Recharts scatter plot with X-axis: Risk, Y-axis: Return
  - Highlight target fund with distinct color and larger size
  - Show category average as reference point
  - Add quadrant lines indicating risk/return zones
  - _Requirements: 6.2_

- [ ]* 6.6 Write unit tests for PeerComparisonChart
  - Test scatter plot renders with fund and peers
  - Test target fund highlighted correctly
  - Test category average displayed
  - _Requirements: 6.2_

- [ ] 6.7 Create MLInsightsPanel component
  - Create frontend/src/components/MLInsightsPanel.tsx
  - Accept props: score (FundScore), componentScores (object with returns, consistency, cost, sentiment, stability), shapValues (Record<string, number> | undefined)
  - Render composite score breakdown (stacked bar or radial chart)
  - Display component scores with labels
  - Show SHAP values in plain language if available
  - Add risk assessment explanation section
  - Add sentiment impact visualization
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ]* 6.8 Write unit tests for MLInsightsPanel
  - Test composite score breakdown renders
  - Test component scores display correctly
  - Test SHAP values section appears when provided
  - _Requirements: 8.1, 8.2, 8.3_

- [ ] 6.9 Checkpoint - Visualization components complete
  - Ensure all chart components render correctly
  - Ensure interactive features work (timeframe selector, tooltips)
  - Ensure all tests pass
  - Ask the user if questions arise

### Phase 7: Enhanced Filtering and Sorting

- [ ] 7.1 Add risk level filter UI and state
  - Add risk level filter dropdown to HomePage (Low/Medium/High options)
  - Add state: `const [riskFilter, setRiskFilter] = useState<string | null>(null)`
  - Update API query to include risk_level parameter when filter active
  - _Requirements: 7.1_

- [ ] 7.2 Add performance filter UI and state
  - Add performance filter buttons (All/Outperformers/Underperformers)
  - Add state: `const [performanceFilter, setPerformanceFilter] = useState<'all' | 'outperformers' | 'underperformers'>('all')`
  - Update API query to include performance parameter when filter active
  - _Requirements: 7.2_

- [ ] 7.3 Add manager tenure and AUM bucket filters
  - Add manager tenure dropdown filter (1Y+, 3Y+, 5Y+ options)
  - Add AUM bucket filter (Small/Medium/Large options)
  - Add states: `const [managerTenure, setManagerTenure] = useState<string | null>(null)` and `const [aumBucket, setAumBucket] = useState<string | null>(null)`
  - Update API query to include manager_tenure_min and aum_bucket parameters
  - _Requirements: 7.3, 7.4_

- [ ] 7.4 Update backend API endpoints to support new filters
  - Modify /api/v1/funds endpoint to accept risk_level, performance, manager_tenure_min, aum_bucket query parameters
  - Implement filtering logic in database query
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ]* 7.5 Write property tests for filter correctness
  - **Property 6: Filter Correctness** - For any applied filter, results contain only matching funds
  - Use fast-check to generate filter combinations
  - Assert no false positives or false negatives
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 7.6 Implement null-safe sorting for all metrics
  - Update sorting logic to place NULL values last in sort order (ascending and descending)
  - Apply to all sortable columns (returns, risk metrics, AUM, etc.)
  - _Requirements: 7.5_

- [ ]* 7.7 Write property tests for null-safe sorting
  - **Property 5: Null-Safe Sorting** - For any metric sort, nulls appear last
  - Use fast-check to generate fund lists with null combinations
  - Assert nulls always last regardless of sort direction
  - _Requirements: 7.5_

- [ ] 7.8 Checkpoint - Filtering and sorting complete
  - Ensure all filters work correctly
  - Ensure sorting handles nulls properly
  - Ensure all tests pass
  - Ask the user if questions arise

### Phase 8: Fund Detail Page Enhancement

- [ ] 8.1 Integrate PerformanceChart into fund detail page
  - Import PerformanceChart component
  - Fetch NAV history for fund and benchmark (if applicable)
  - Render PerformanceChart with timeframe selector
  - Add benchmark overlay if benchmark data available
  - Add moving average overlays
  - _Requirements: 6.1, 6.3, 11.1, 11.3, 11.4_

- [ ]* 8.2 Write property test for category performance highlighting
  - **Property 11: Category Performance Highlighting** - Highlighting matches fund vs category performance
  - Use fast-check to generate fund and category return combinations
  - Assert positive indicator when fund > category
  - Assert negative indicator when fund < category
  - _Requirements: 9.4_

- [ ] 8.3 Add PeerComparisonChart section to detail page
  - Fetch category peer data from API
  - Render PeerComparisonChart with fund, peers, and category average
  - Add section heading and description
  - _Requirements: 6.2, 9.1_

- [ ] 8.4 Add MLInsightsPanel section to detail page
  - Fetch ML score breakdown and SHAP values from API (if available)
  - Render MLInsightsPanel with composite score and component scores
  - Add section heading explaining ML-driven insights
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 8.5 Add category peer comparison section
  - Display fund rank within category with percentile indicator
  - Show category average metrics (returns, risk, expense ratio)
  - Highlight outperformance/underperformance vs category
  - Display distribution of scores within category (histogram or box plot)
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 8.6 Add inception date display to detail page
  - Fetch inception_date from fund data
  - Display inception date prominently with label "Fund Launched"
  - Use clear date formatting
  - _Requirements: 3.2_

- [ ] 8.7 Add risk visualization breakdown section
  - Create risk breakdown grid showing volatility, drawdown, Sharpe ratio
  - Display risk gauge component
  - Show maximum drawdown with timeline visualization
  - Compare fund risk metrics to category average
  - Handle unavailable risk metrics with "N/A" and tooltips
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ]* 8.8 Write integration tests for fund detail page
  - Test performance chart renders with timeframes
  - Test peer comparison chart renders
  - Test ML insights panel renders
  - Test category comparison section renders
  - Test inception date displays
  - Test risk breakdown renders
  - _Requirements: 6.1, 6.2, 8.1, 9.1, 12.1_

- [ ] 8.9 Checkpoint - Fund detail page enhancements complete
  - Ensure all sections render correctly
  - Ensure data quality indicators work
  - Ensure all tests pass
  - Ask the user if questions arise

### Phase 9: Admin Features and Monitoring

- [ ] 9.1 Create /api/v1/admin/validation-stats endpoint
  - Create admin router in backend if not exists
  - Implement endpoint returning validation statistics JSON
  - Response includes: last_feature_run timestamp, total_schemes_processed, validation_failures object (by metric), validation_failure_rate
  - _Requirements: 14.4_

- [ ] 9.2 Add validation statistics aggregation logic
  - Query feature calculation logs or database for validation failure counts
  - Aggregate failures by metric type (return_1m, return_3m, etc.)
  - Calculate validation failure rate
  - _Requirements: 14.3_

- [ ]* 9.3 Write property test for statistics aggregation
  - **Property 9: Validation Statistics Aggregation** - Sum of failures per metric equals count of schemes that failed
  - Use hypothesis to generate validation failure scenarios
  - Assert aggregation correctness
  - _Requirements: 14.3_

- [ ] 9.4 Add warning threshold logging for validation failures
  - Define threshold (e.g., 40% validation failure rate)
  - Log warning when threshold exceeded during feature calculation
  - Include context: total schemes, failures by metric, timestamp
  - _Requirements: 14.5_

- [ ]* 9.5 Write unit tests for admin endpoint
  - Test endpoint returns correct structure
  - Test endpoint requires authentication/authorization
  - Test validation statistics accuracy
  - _Requirements: 14.4_

- [ ] 9.6 Checkpoint - Admin features complete
  - Ensure admin endpoint works correctly
  - Ensure logging configured properly
  - Ensure all tests pass
  - Ask the user if questions arise

### Phase 10: Testing, Polish, and Documentation

- [ ] 10.1 Run full property-based test suite
  - Run all property tests (Properties 1-12) with 100+ iterations
  - Fix any failing properties
  - Document any discovered edge cases
  - _Requirements: All validation and display requirements_

- [ ]* 10.2 Write integration tests for data refresh workflow
  - Test data refresh triggers feature recalculation
  - Test cache invalidation after refresh
  - Test API returns updated metrics after refresh
  - Test frontend shows loading indicator during refresh
  - Test frontend displays success message after refresh
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ]* 10.3 Perform manual QA on all new features
  - Test fund card with various data quality scenarios
  - Test fund detail page with all visualization components
  - Test filters and sorting with null values
  - Test responsive design on mobile and tablet
  - Test accessibility with screen reader
  - Test keyboard navigation
  - _Requirements: All UI requirements_

- [ ]* 10.4 Performance testing and optimization
  - Measure feature calculation time before/after validation changes (target: < 5% overhead)
  - Measure API response times for fund list and detail endpoints
  - Test frontend rendering with 1000+ fund cards
  - Optimize any components with > 100ms render time
  - Ensure filter/sort operations complete in < 100ms
  - _Requirements: Design performance goals_

- [ ]* 10.5 Accessibility testing
  - Verify all interactive elements have proper ARIA labels
  - Verify all charts have aria-describedby for screen readers
  - Verify all tooltips are keyboard accessible
  - Verify color contrast meets WCAG AA standards for risk indicators
  - Verify "N/A" indicators distinguishable by non-color cues
  - Test keyboard navigation through all filters and components
  - _Requirements: Design accessibility section_

- [ ]* 10.6 Cross-browser testing
  - Test on Chrome, Firefox, Safari, Edge
  - Verify chart rendering consistency
  - Verify tooltip behavior
  - Verify filter/sort behavior
  - _Requirements: Frontend compatibility_

- [ ] 10.7 Update developer documentation
  - Document validation thresholds and rationale in code comments
  - Document buffer day calculations
  - Update API documentation with new fields (data_quality, inception_date)
  - Provide migration guide for existing API clients
  - Document all new frontend components with usage examples
  - Document data quality utility functions
  - _Requirements: 15.1, 15.2_

- [ ] 10.8 Update user-facing documentation
  - Write help text explaining why some metrics show "N/A"
  - Document minimum data requirements for each metric
  - Create guide explaining new filter options
  - Add tooltips/help icons next to new UI elements
  - _Requirements: 10.1, 10.5_

- [ ] 10.9 Create deployment runbook
  - Document pre-deployment checklist (staging tests, performance baseline)
  - Document deployment sequence (backend → migration → feature rebuild → API → frontend)
  - Document rollback procedures
  - Document monitoring checklist (validation rates, API response times, error rates)
  - _Requirements: Design deployment strategy_

- [x] 10.10 Final checkpoint - Production readiness review
  - All property tests passing with 100+ iterations
  - All integration tests passing
  - Performance metrics within targets
  - Accessibility compliance verified
  - Documentation complete
  - Deployment runbook ready
  - Obtain stakeholder approval for production deployment

## Notes

- Tasks marked with `*` are optional test and polish tasks that can be skipped for faster MVP deployment
- All validation and display logic tasks are REQUIRED to ensure data accuracy
- Property-based tests (marked with "Property X:") directly validate correctness properties from the design document
- Each task references specific requirements for traceability
- The implementation sequence ensures backend validation is complete before frontend work begins
- Database migration must complete before API enhancements
- Frontend foundation components must be built before integrating into FundCard and detail pages
- Testing and polish phase can run in parallel with final feature development

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "2.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3"] },
    { "id": 4, "tasks": ["3.4", "3.5", "3.6"] },
    { "id": 5, "tasks": ["3.7", "4.1", "4.3", "4.5"] },
    { "id": 6, "tasks": ["4.2", "4.4", "4.6"] },
    { "id": 7, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.6"] },
    { "id": 8, "tasks": ["5.5", "5.7", "5.8", "6.1"] },
    { "id": 9, "tasks": ["6.2", "6.4", "6.5", "6.7"] },
    { "id": 10, "tasks": ["6.3", "6.6", "6.8", "7.1", "7.2", "7.3"] },
    { "id": 11, "tasks": ["7.4"] },
    { "id": 12, "tasks": ["7.5", "7.6"] },
    { "id": 13, "tasks": ["7.7", "8.1"] },
    { "id": 14, "tasks": ["8.3", "8.4", "8.5", "8.6", "8.7"] },
    { "id": 15, "tasks": ["8.2", "8.8", "9.1", "9.2"] },
    { "id": 16, "tasks": ["9.3", "9.4", "9.5"] },
    { "id": 17, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5", "10.6"] },
    { "id": 18, "tasks": ["10.7", "10.8"] },
    { "id": 19, "tasks": ["10.9"] }
  ]
}
```
