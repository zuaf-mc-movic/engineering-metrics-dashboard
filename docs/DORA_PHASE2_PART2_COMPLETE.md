# Phase 2 DORA Metrics - Part 2: DORA Metrics Calculation

## Status: ✅ COMPLETE (Initial Implementation)

## Implementation Date
January 11, 2026

## Summary
Successfully implemented DORA (DevOps Research and Assessment) four key metrics calculation in the MetricsCalculator class. The first two metrics (Deployment Frequency and Lead Time for Changes) are fully functional with production release data. The remaining two metrics (Change Failure Rate and MTTR) have placeholder implementations ready for incident tracking data (Phase 2B).

## Changes Made

### 1. Metrics Calculator (`src/models/metrics.py`)

**New Primary Method:**
- `calculate_dora_metrics(start_date, end_date, incidents_df)` - Main DORA calculation orchestrator
  - Calculates all four DORA metrics
  - Determines overall performance level (Elite/High/Medium/Low)
  - Returns complete DORA metrics dictionary
  - Lines: 165-237

**Supporting Methods:**
- `_calculate_deployment_frequency()` - Counts production releases per time period
  - Elite: >= 1 deployment/day
  - High: >= 1 deployment/week
  - Medium: >= 1 deployment/month
  - Low: < 1 deployment/month
  - Includes weekly trend data
  - Lines: 239-301

- `_calculate_lead_time_for_changes()` - PR merge to production deployment time
  - Maps each merged PR to next production release
  - Calculates median, p95, and average lead times
  - Elite: < 24 hours
  - High: < 1 week (168 hours)
  - Medium: < 1 month (720 hours)
  - Low: >= 1 month
  - Lines: 303-400

- `_calculate_change_failure_rate()` - % of deployments causing incidents
  - Placeholder implementation (awaiting incident data)
  - Counts total production deployments
  - Returns 'unknown' level with note
  - Lines: 402-451

- `_calculate_mttr()` - Mean time to restore from incidents
  - Placeholder implementation (awaiting incident data)
  - Returns 'unknown' level with note
  - Lines: 453-476

- `_calculate_dora_performance_level()` - Overall performance classification
  - Aggregates individual metric levels
  - Elite: 3+ elite metrics
  - High: 2+ elite OR 3+ high/elite combined
  - Medium: <= 1 low metric
  - Low: 2+ low metrics
  - Lines: 478-514

**Updated Methods:**
- `calculate_deployment_metrics()` - Enhanced to use releases DataFrame instead of empty deployments
  - Now supports production/staging filtering
  - Lines: 125-163

- `calculate_team_metrics()` - Now includes DORA metrics in return value
  - Creates temporary calculator with releases for team
  - Adds 'dora' key to returned metrics
  - Lines: 772-794

### 2. DORA Metrics Data Structure

```python
{
    'deployment_frequency': {
        'total_deployments': 45,
        'per_day': 0.5,
        'per_week': 3.5,
        'per_month': 15.0,
        'level': 'high',
        'badge_class': 'high',
        'trend': {
            '2025-W01': 3,
            '2025-W02': 4,
            ...
        }
    },
    'lead_time': {
        'median_hours': 48.5,
        'median_days': 2.0,
        'p95_hours': 120.0,
        'p95_days': 5.0,
        'average_hours': 55.2,
        'average_days': 2.3,
        'sample_size': 107,
        'level': 'high',
        'badge_class': 'high'
    },
    'change_failure_rate': {
        'rate_percent': None,
        'failed_deployments': None,
        'total_deployments': 45,
        'level': 'unknown',
        'badge_class': 'low',
        'note': 'Incident correlation not yet implemented'
    },
    'mttr': {
        'median_hours': None,
        'median_days': None,
        'average_hours': None,
        'sample_size': 0,
        'level': 'unknown',
        'badge_class': 'low',
        'note': 'Incident data not yet implemented'
    },
    'dora_level': {
        'level': 'High',
        'description': 'Strong performance across all DORA metrics.',
        'breakdown': {
            'elite': 0,
            'high': 2,
            'medium': 0,
            'low': 0
        }
    },
    'measurement_period': {
        'start_date': '2025-10-13T00:00:00+00:00',
        'end_date': '2026-01-11T23:59:59+00:00',
        'days': 90
    }
}
```

### 3. Test Suite (`tests/unit/test_dora_metrics.py`)

**Created comprehensive test coverage:**

**Deployment Frequency Tests (6 tests):**
- Elite level classification (>= 1/day)
- High level classification (>= 1/week)
- Medium level classification (>= 1/month)
- Low level classification (< 1/month)
- Production-only filtering
- No releases edge case

**Lead Time Tests (5 tests):**
- Elite level classification (< 24 hours)
- High level classification (< 1 week)
- PR to release mapping logic
- Unmerged PR filtering
- No releases edge case

**Change Failure Rate Tests (1 test):**
- Placeholder validation

**MTTR Tests (1 test):**
- Placeholder validation

**DORA Level Tests (2 tests):**
- Elite classification logic
- Breakdown structure validation

**Measurement Period Tests (2 tests):**
- Data-driven date range calculation
- Explicit date range handling

**Test Results:**
```
17 tests collected
17 passed (100%)
Test duration: 0.44 seconds
Coverage: 30% of metrics.py (125+ new lines covered)
```

## DORA Performance Thresholds

Based on DORA State of DevOps research benchmarks:

| Level | Deployment Frequency | Lead Time | Change Failure Rate | MTTR |
|-------|---------------------|-----------|---------------------|------|
| **Elite** | Multiple deploys/day | < 1 day | < 15% | < 1 hour |
| **High** | Weekly - Monthly | < 1 week | < 15% | < 1 day |
| **Medium** | Monthly - Bi-monthly | 1 week - 1 month | 16-30% | < 1 week |
| **Low** | < Monthly | > 1 month | > 30% | > 1 week |

## Implementation Details

### Deployment Frequency Calculation
1. Filters releases to production environment only
2. Counts releases within measurement period
3. Calculates per-day, per-week, per-month rates
4. Generates weekly trend data for charts
5. Classifies based on DORA thresholds

### Lead Time Calculation
1. Filters to merged PRs and production releases
2. For each merged PR:
   - Finds next production release after merge
   - Calculates time difference in hours
3. Computes median, p95, and average
4. Classifies based on median lead time

### Metric Integration
- DORA metrics are calculated at team level (not person level)
- Releases are team-wide (not filtered to individuals)
- PRs are filtered to team members for lead time calculation
- Results included in team_metrics['dora'] dictionary

## What's Working

✅ **Deployment Frequency** - Fully functional
- Counts production releases
- Classifies Elite/High/Medium/Low
- Provides trend data

✅ **Lead Time for Changes** - Fully functional
- Maps PRs to deployments
- Calculates median/p95/average
- Handles edge cases (no releases, unmerged PRs)

⏳ **Change Failure Rate** - Placeholder ready
- Counts production deployments
- Returns 'unknown' level
- Note indicates feature not yet implemented

⏳ **MTTR** - Placeholder ready
- Returns 'unknown' level
- Note indicates feature not yet implemented

✅ **Overall DORA Level** - Functional
- Aggregates metric levels
- Provides performance classification
- Includes breakdown by metric

## Verification Steps

To verify DORA metrics are working:

```bash
# 1. Run data collection (includes releases)
python collect_data.py

# 2. Check DORA metrics in cache
python3 << 'EOF'
import pickle
with open('data/metrics_cache_90d.pkl', 'rb') as f:
    cache = pickle.load(f)

# Check team DORA metrics
for team_name, team_data in cache['teams'].items():
    dora = team_data.get('dora', {})
    print(f"\n{team_name} DORA Metrics:")
    print(f"  Deployment Frequency: {dora.get('deployment_frequency', {}).get('level', 'N/A')}")
    print(f"  Lead Time: {dora.get('lead_time', {}).get('level', 'N/A')}")
    print(f"  Overall: {dora.get('dora_level', {}).get('level', 'N/A')}")
EOF

# 3. Run all DORA tests
pytest tests/unit/test_dora_metrics.py -v
pytest tests/unit/test_release_collection.py -v

# 4. Check test coverage
pytest tests/unit/test_dora_metrics.py --cov=src.models.metrics --cov-report=term-missing
```

## Next Steps (Phase 2B - NOT INCLUDED)

Future work to complete full DORA metrics:

1. **Jira Incident Collection**:
   - Add incident filter to Jira collector
   - Extract incident creation/resolution times
   - Correlate incidents to deployments (24-hour window)

2. **Change Failure Rate Implementation**:
   - Replace placeholder in `_calculate_change_failure_rate()`
   - Map incidents to deployment tags
   - Calculate % of deployments with incidents

3. **MTTR Implementation**:
   - Replace placeholder in `_calculate_mttr()`
   - Calculate incident cycle times
   - Compute median resolution time

4. **Dashboard Visualization** (Phase 2 Part 4):
   - Add DORA metrics section to team_dashboard.html
   - Create metric cards for all 4 metrics
   - Add performance level badge
   - Include deployment frequency trend chart

## Files Modified

1. `src/models/metrics.py` (+352 lines)
   - Added DORA calculation methods
   - Updated deployment metrics
   - Integrated into team metrics

2. `tests/unit/test_dora_metrics.py` (+479 lines, new file)
   - 17 comprehensive tests
   - All performance levels tested
   - Edge cases covered

3. `docs/DORA_PHASE2_PART2_COMPLETE.md` (this file, new)

## Integration Notes

**Backwards Compatibility**: ✅ Fully backwards compatible
- DORA metrics automatically calculated for all teams
- No breaking changes to existing code
- Gracefully handles missing release data

**Performance Impact**: Minimal
- Lead time calculation is O(n*m) where n=PRs, m=releases
- Typically < 100 PRs * < 50 releases = < 5000 comparisons
- Runs in < 1 second for typical team

**Data Requirements**:
- Requires releases from Part 1 (GitHub release collection)
- Works with any number of releases (0 to thousands)
- Gracefully handles missing data (returns 'low' or 'unknown')

## Test Coverage Summary

```
Total tests: 31 (14 release + 17 DORA)
Status: 100% passing
Coverage: 30% of metrics.py (up from 0% for DORA methods)
New code: 352 lines
Test code: 479 lines
```

## Known Limitations

1. **Change Failure Rate**: Requires incident data (Phase 2B)
2. **MTTR**: Requires incident data (Phase 2B)
3. **Lead Time Accuracy**: Assumes next deployment includes the PR (reasonable approximation)
4. **Dashboard**: DORA metrics not yet displayed (Phase 2 Part 4)

## Success Criteria

✅ Deployment frequency calculated from production releases
✅ Lead time calculated from PR merge to deployment
✅ All four DORA metrics have data structures
✅ Performance level classification working
✅ 17 unit tests passing (100% success rate)
✅ Integrated into team metrics pipeline
⏳ CFR/MTTR placeholders ready for incident data
⏳ Dashboard visualization (next phase)

## References

- DORA State of DevOps Report: https://dora.dev/
- Four Key Metrics: https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance
- Phase 2 Full Plan: `/Users/zmaros/.claude/plans/declarative-wiggling-squid.md`
