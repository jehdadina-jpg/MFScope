# Task 1.4 Implementation Summary: Add Validation Failure Logging

## Overview
Enhanced the validation failure logging in the Feature Builder to include scheme_code and use a structured logging format for easy parsing and monitoring.

## Changes Made

### 1. Enhanced `_trailing_return_validated` Function
**File**: `backend/features/feature_builder.py`

**Changes**:
- Added `scheme_code` and `metric_name` parameters
- Replaced simple debug log with structured logging using `logger.debug()` with `extra` parameter
- Logs now include:
  - `validation_type`: "return"
  - `scheme_code`: The fund's scheme code (or "UNKNOWN" if None)
  - `metric`: The specific metric name (e.g., "return_1y", "return_3m")
  - `available_days`: Actual number of NAV data points
  - `required_days`: Minimum required data points for this metric
  - `validation_result`: "FAIL"

### 2. Updated Call Sites in `build_features` Method
**File**: `backend/features/feature_builder.py`

**Changes**:
- Updated all 6 return calculation calls to pass `scheme.scheme_code` and metric name:
  - `return_1m`: passes "return_1m"
  - `return_3m`: passes "return_3m"
  - `return_6m`: passes "return_6m"
  - `return_1y`: passes "return_1y"
  - `return_3y`: passes "return_3y"
  - `return_5y`: passes "return_5y"

### 3. Enhanced Risk Metrics Validation Logging
**File**: `backend/features/feature_builder.py`

**Changes**:
- Updated risk metrics validation failure logging to use structured format
- Logs now include:
  - `validation_type`: "risk_metrics"
  - `scheme_code`: The fund's scheme code
  - `metrics`: List of all risk metrics that failed (volatility_1y, sharpe_1y, sortino_1y, alpha_1y, beta_1y, max_drawdown_1y)
  - `available_days`: Actual number of NAV data points in 1Y window
  - `required_days`: Minimum required (370 days)
  - `validation_result`: "FAIL"

### 4. Added Unit Tests
**File**: `tests/test_feature_builder.py`

**New Test Class**: `TestValidationLogging`

**Tests Added**:
- `test_insufficient_data_returns_none`: Verifies validation returns None for insufficient data
- `test_sufficient_data_returns_value`: Verifies validation returns calculated value for sufficient data
- `test_validation_with_none_scheme_code`: Verifies graceful handling of None scheme_code
- `test_validation_multiple_metrics`: Verifies validation works correctly for different metric periods

All tests pass successfully.

## Example Log Output

### Return Validation Failure
```json
{
  "text": "Validation failed for trailing return",
  "record": {
    "extra": {
      "validation_type": "return",
      "scheme_code": "HDFC001",
      "metric": "return_1y",
      "available_days": 200,
      "required_days": 370,
      "validation_result": "FAIL"
    },
    "level": {"name": "DEBUG"},
    "function": "_trailing_return_validated",
    "line": 76
  }
}
```

### Risk Metrics Validation Failure
```json
{
  "text": "Validation failed for risk metrics",
  "record": {
    "extra": {
      "validation_type": "risk_metrics",
      "scheme_code": "ICICI002",
      "metrics": ["volatility_1y", "sharpe_1y", "sortino_1y", "alpha_1y", "beta_1y", "max_drawdown_1y"],
      "available_days": 200,
      "required_days": 370,
      "validation_result": "FAIL"
    },
    "level": {"name": "DEBUG"}
  }
}
```

## Benefits

### 1. Easy Parsing
The structured JSON format allows log aggregation tools (e.g., ELK Stack, Datadog, Splunk) to:
- Parse logs automatically without regex patterns
- Query by specific fields (scheme_code, metric, validation_type)
- Create dashboards showing validation failure rates by metric type

### 2. Monitoring and Alerting
With structured logs, you can:
- Set up alerts when validation failures exceed a threshold
- Track which schemes consistently have insufficient data
- Monitor data quality trends over time
- Identify which metrics have the highest failure rates

### 3. Debugging and Support
- Quickly identify which funds have data quality issues
- Filter logs by scheme_code to investigate specific fund issues
- Understand why a particular metric is showing N/A in the UI

### 4. Compliance and Auditing
- Structured logs provide clear audit trails
- Easy to demonstrate that metrics were not calculated from insufficient data
- Can generate reports showing data quality across the entire fund universe

## Requirements Satisfied

✅ **Requirement 14.1**: WHEN a return calculation is skipped due to insufficient data, THE Feature_Builder SHALL log the scheme_code and required days

✅ **Requirement 14.2**: WHEN a risk metric calculation is skipped due to insufficient data, THE Feature_Builder SHALL log the scheme_code and required days

## Testing

All tests pass:
```bash
$ python -m pytest tests/test_feature_builder.py::TestValidationLogging -v
=============== 4 passed in 1.07s ===============
```

## Next Steps

This implementation provides the foundation for:
- Task 9.2: Validation statistics aggregation logic (can query structured logs)
- Task 9.4: Warning threshold logging (can count validation failures by type)
- Future monitoring dashboards showing data quality metrics
