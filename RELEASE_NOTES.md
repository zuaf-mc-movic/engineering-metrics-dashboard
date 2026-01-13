# Release Notes - v1.0.0

## Summary

Major cleanup and documentation release preparing the Team Metrics Dashboard for production use.

## Recent Features (Jan 13, 2026)

### DORA Metrics Trend Visualizations & Homepage Improvements (Commit: d94edaf)
- **Feature:** Added weekly trend charts for all DORA metrics on team dashboards
- **New Visualizations:**
  - **Lead Time Trend**: Weekly median time from commit to production (line chart)
  - **Change Failure Rate Trend**: Weekly percentage of failed deployments (line chart)
  - **MTTR Trend**: Weekly median incident resolution time (line chart)
  - **Deployment Frequency Trend**: Already existed, now part of complete set
- **Homepage Reorganization:**
  - Team cards now organized into clear sections: GitHub, Jira, DORA metrics
  - Added color-coded DORA performance badges (Elite/High/Medium/Low)
  - Fixed Overall DORA Performance Level display on homepage
  - Visual hierarchy with section borders for better scanability
- **Implementation:**
  - Backend: Added trend calculations to `_calculate_lead_time_for_changes()`, `_calculate_change_failure_rate()`, `_calculate_mttr()` in metrics.py
  - Frontend: Three new Plotly charts in team_dashboard.html with theme-aware styling
  - Homepage: Reorganized teams_overview.html with `.metrics-section` styling
- **Testing:**
  - Added comprehensive test suite: `tests/unit/test_dora_trends.py` (13 tests, all passing)
  - Test coverage: Deployment Frequency, Lead Time, CFR, MTTR trends
  - Edge cases: Empty data, no incidents, Jira mapping, JSON serialization
- **Notes:** CFR and MTTR trends only display when incident data is available
- **Status:** All 4 DORA metrics now have weekly trend visualization

### Complete DORA Metrics - Incident Tracking (Commits: 47a64c5, aea8e79)
- **Feature:** Added incident tracking to complete all 4 DORA metrics
- **New Metrics:**
  - **Change Failure Rate (CFR)**: Percentage of deployments causing production incidents
  - **Mean Time to Recovery (MTTR)**: Median time to resolve production incidents
- **Implementation:**
  - Incident collection via Jira filters (customizable per team)
  - Automatic correlation between deployments and incidents (24-hour window)
  - Dashboard incident filter link card for easy access
  - Performance level classification (Elite, High, Medium, Low)
- **Configuration:** Requires `incidents` filter ID in team Jira config
- **Status:** All 4 DORA metrics now operational (Deployment Frequency, Lead Time, CFR, MTTR)

## Recent Bug Fixes (Jan 13, 2026)

### Fix Jira Library Bug - Issue Mapping Failures (Commit: 6451da5)
- **Issue:** Jira Python library bug caused `TypeError: argument of type 'NoneType' is not iterable` when fetching issues for Fix Versions
- **Impact:** All releases showed 0 team issues, breaking Jira-based lead time calculation
- **Root Cause:** Library bug in `jira/client.py:3686` when using `fields='key'` parameter with malformed issue data
- **Resolution:** Removed `fields='key'` parameter from `search_issues()` call, using default fields instead
- **Result:** Clean collection with proper issue mapping, Jira-based lead time now works correctly
- **Trade-off:** Slightly larger API responses, but ensures stability and accurate metrics

## Key Improvements

### ✅ Test Coverage Enhancements
- **Added 46 new tests** for critical features
  - 19 tests for performance score calculation (previously 0% coverage)
  - 27 tests for config validation (previously 0% coverage)
- All tests passing (135+ total tests)
- Comprehensive edge case coverage

### 📚 Documentation Overhaul
- **Performance Scoring System** fully documented:
  - Algorithm explanation (min-max normalization, weighted scoring)
  - Default metric weights table (PRs 20%, Reviews 20%, etc.)
  - Cycle time inversion and team size normalization explained
  - Added to README.md, CLAUDE.md, and documentation.html

- **GitHub GraphQL Queries** documented:
  - Example PR query with nested reviews
  - Repository/team query examples
  - Pagination and ordering explanations

- **Jira JQL Queries** documented:
  - Project, person, and filter queries
  - Anti-noise filtering rationale explained
  - Worklogs query documentation

- **Time Window Consistency**: Fixed inconsistencies
  - Removed incorrect claims about "flexible date ranges"
  - Clarified fixed 90-day rolling window across all metrics

- **Team Member Comparison**: Documented new feature
  - Performance rankings with 🥇🥈🥉 badges
  - Leaderboard functionality

### 🧹 Dead Code Removal (~1,350 lines)
Removed unused and deprecated code:
- **Legacy REST API collector** (461 lines) - GraphQL is now primary
- **Time period selection module** (282 lines) - Period flags removed for simplicity
- **Activity thresholds module** (221 lines) - Implemented but never integrated
- **Unused dashboard template** (387 lines) - Dead code path
- **62 tests** for removed features
- **3+ MB** of old cache backup files

### 🔧 Code Cleanup
- Removed deprecated `/api/collect/<period>` endpoint
- Removed unused config properties (time_periods, activity_thresholds)
- Cleaned up imports in collect_data.py and app.py
- Updated IMPLEMENTATION_GUIDE.md to remove obsolete references

## Files Added
- `tests/unit/test_performance_score.py` - 19 comprehensive tests
- `tests/unit/test_config.py` - 27 configuration validation tests
- `RELEASE_NOTES.md` - This file

## Files Removed
- `src/collectors/github_collector.py` - Legacy REST API collector
- `src/utils/time_periods.py` - Deprecated period selection
- `src/utils/activity_thresholds.py` - Unintegrated feature
- `src/dashboard/templates/dashboard.html` - Unused template
- `tests/unit/test_time_periods.py` - Tests for removed feature
- `tests/unit/test_activity_thresholds.py` - Tests for removed feature
- `tests/collectors/test_github_collector.py` - Misnamed test file
- `data/*.backup-*` - Old cache backups (8 files, 3+ MB)

## Files Modified
### Critical Updates:
- `README.md` - Fixed time window claims, added performance scoring docs, documented team member comparison
- `CLAUDE.md` - Added performance scoring, GraphQL/JQL query examples, updated architecture section
- `src/dashboard/templates/documentation.html` - Expanded performance scoring explanation with weights table

### Code Updates:
- `src/config.py` - Removed time_periods and activity_thresholds properties
- `src/dashboard/app.py` - Removed deprecated endpoint and legacy imports
- `collect_data.py` - Removed legacy REST API imports
- `src/models/metrics.py` - No changes (performance score was already implemented, just undocumented)

## Test Results

**Total Tests:** 135+ tests
**Coverage:** Target ≥80% (meets requirement)
**Status:** All passing ✅

**New Critical Coverage:**
- Performance score calculation: 100% (19 tests)
- Config validation: 94% (27 tests)

**Existing Strong Coverage:**
- Time periods: REMOVED (feature deprecated)
- Activity thresholds: REMOVED (feature not integrated)
- Metrics calculator: 87% (30 tests)
- GitHub GraphQL collector: 72% (12 tests)
- Jira collector: 78% (17 tests)

## Breaking Changes

None - All changes are backward compatible:
- Code removal affects only unused/deprecated features
- Documentation updates don't change behavior
- New tests don't modify existing functionality

## Migration Notes

No migration needed. The removed features were:
1. **Never used in production** (legacy REST API)
2. **Explicitly deprecated** (time period selection)
3. **Never integrated** (activity thresholds)
4. **Dead code paths** (unused template)

## Verification Checklist

- [x] All new tests pass
- [x] No imports of deleted files remain
- [x] Documentation is consistent across all files
- [x] Performance score fully documented in 3+ places
- [x] GraphQL and JQL queries documented with examples
- [x] Time window inconsistencies resolved
- [x] Dead code removed (~1,350 lines)
- [x] Cache backups cleaned up (3+ MB freed)

## What's Next

Recommended follow-up tasks (not blocking release):
1. Add dashboard route integration tests (15-20 tests)
2. Add template rendering tests (5-10 tests)
3. Update .gitignore with test artifacts (htmlcov/, .coverage, etc.)
4. Consider adding performance score customization UI

## Release Artifacts

- `test-results.xml` - JUnit XML test report
- `htmlcov/index.html` - Interactive HTML coverage report
- Coverage report available at: `open htmlcov/index.html`

## Contributors

- Team Metrics Dashboard Development Team
- Assisted by Claude Code (Anthropic)

---

**Release Date:** January 11, 2026
**Version:** 1.0.0
**Status:** Production Ready ✅
