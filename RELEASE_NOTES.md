# Release Notes

> ⚠️ **Historical Document** - This document reflects the codebase state at the time of completion. The metrics module structure has since been refactored (Jan 2026) from a single `metrics.py` file into 4 focused modules. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for current structure.

## [Unreleased] - 2026-01-17

### Critical Bug Fixes & Feature Improvements

#### Fixed
- **🐛 Critical: Releases not saved to cache** - Fixed bug where Jira Fix Version releases were collected and used for DORA calculations but not saved to cache, resulting in 0 releases displayed
  - Root cause: `MetricsCalculator.calculate_team_metrics()` wasn't returning `raw_releases` in metrics dictionary
  - Impact: Native Team now shows 35 releases, WebTC Team shows 4 releases
  - Deployment frequency and DORA metrics now calculate correctly

- **Assignee-only filtering for team metrics** - Changed from "assignee OR reporter" to "assignee only" for more accurate team attribution
  - Prevents inflation from issues reported by team but assigned to others
  - Critical for shared releases across multiple teams
  - Example: Native Team releases show 77% with 0 issues (correct - only counting team-assigned work)

- **CI workflow paths** - Updated GitHub Actions to check `tools/` directory after project restructuring

#### Added
- **Branch name collection for Lead Time tracking** - Added `headRefName` to PR data collection
  - Enables issue key extraction from branch names (e.g., `feature/RSC-123-add-feature`)
  - Primary: Checks PR title for issue key
  - Fallback: Checks branch name for issue key ← **NEW**
  - Supports cherry-pick workflows: feature branches → master → release branches
  - Significantly improves lead time accuracy for release/* workflows

- **Enhanced datetime error handling** - Added try/except around date comparisons with detailed logging
  - Helps diagnose timezone-related issues in release filtering
  - Provides clear error messages with type information

#### Documentation
- **CLAUDE.md**: Added comprehensive Lead Time calculation documentation
  - Two-method approach (Jira-based vs time-based)
  - Release workflow support (cherry-pick explanation)
  - DORA performance level thresholds
- **RELEASE_NOTES.md**: This entry with all recent changes
- **docs/DATA_QUALITY.md**: Updated team member validation to reflect assignee-only filtering

### Project Restructuring & Documentation

#### Changed
- **Simplified data collection**: Reduced from 15+ date ranges to 6 essential ranges (30d, 60d, 90d, 180d, 365d, previous year)
- **Removed quarterly collections**: No longer collecting Q1-Q4 ranges for current/previous years in automated collection
- **Updated dashboard config**: Removed 7d and 14d options, focused on 6 essential ranges
- **Project structure cleanup**: Moved analysis tools to `/tools/` directory, documentation to `/docs/`

#### Added
- **`/tools/` directory**: New home for analysis and verification scripts
  - `tools/analyze_releases.py` - Release and DORA metrics analysis
  - `tools/verify_collection.sh` - Quick collection verification
  - `tools/verify_jira_versions.py` - Jira version pattern testing
  - `tools/verify_scope_filter.py` - Jira scope filter testing
  - `tools/test_dora_performance.py` - DORA metrics in performance scores
  - `tools/README.md` - Complete tool documentation
- **`docs/COLLECTION_CHANGES.md`**: Documentation of collection simplification rationale
- **Documentation reorganization**: Moved `IMPLEMENTATION_GUIDE.md` and `ANALYSIS_COMMANDS.md` to `/docs/`

#### Removed
- **Temporary files**: Deleted `.swp`, `.DS_Store`, old log files
- **Test artifacts**: Deleted `htmlcov/` (26MB), `.coverage`, `test-results.xml` (regenerated as needed)
- **Release artifacts**: Deleted v1.0.0 tar.gz, zip, checksums (tracked via GitHub releases)
- **Cache backup files**: Cleaned up 45+ quarterly and unnecessary cache backups (~2-3 MB)

#### Performance
- **Collection time reduced by ~60%**: 5-10 min → 2-4 min
- **API calls reduced by ~60%**: Fewer redundant ranges
- **Disk space freed**: ~30 MB (artifacts + backups)
- **Root directory cleanup**: 49 items → ~25 items (48% reduction)

#### Files Modified
- `CLAUDE.md` - Updated collection references, tool paths, date range documentation
- `RELEASE_NOTES.md` - Added this entry
- `.gitignore` - Ensured test artifacts and temporary files are ignored

---

## v1.0.0 - 2026-01-11

### Summary

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
