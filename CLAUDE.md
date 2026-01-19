# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Team Metrics Dashboard - A Python-based metrics collection and visualization tool for tracking engineering team performance across GitHub and Jira.

**Key Technology**: Uses GitHub GraphQL API v4 for efficient data collection (50-70% fewer API calls than REST).

## Development Commands

### Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy configuration template
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml with your GitHub token, Jira credentials, and team configuration
```

### Data Collection
```bash
# Collect metrics with flexible date ranges (6 essential ranges)
python collect_data.py --date-range 90d     # Last 90 days (default)
python collect_data.py --date-range 30d     # Last 30 days
python collect_data.py --date-range 60d     # Last 60 days
python collect_data.py --date-range 180d    # Last 6 months
python collect_data.py --date-range 365d    # Last year
python collect_data.py --date-range 2025    # Previous year (for annual reviews)

# List available Jira filters (utility to find filter IDs)
python list_jira_filters.py
```

**Note**: Each collection creates a separate cache file (e.g., `metrics_cache_90d.pkl`) allowing you to switch between date ranges in the dashboard without re-collecting data.

**Automated Collection**: The `scripts/collect_data.sh` script automatically collects all 6 ranges (30d, 60d, 90d, 180d, 365d, previous year) in 2-4 minutes. See `docs/COLLECTION_CHANGES.md` for details on recent simplification from 15+ ranges.

### Performance Optimizations

The system includes multiple automatic optimizations for 5-6x faster data collection:

1. **Parallel Collection** - Teams (3 workers), repos (5 workers), persons (8 workers), Jira filters (4 workers)
2. **Connection Pooling** - Reuses HTTP connections (5-10% speedup, automatic)
3. **Repository Caching** - Caches team repo lists for 24 hours (5-15s saved, automatic)
4. **GraphQL Query Batching** - Combines PRs and Releases queries (20-40% speedup, 50% fewer API calls, automatic)

**Configuration** (`config/config.yaml`):
```yaml
parallel_collection:
  enabled: true           # Master switch (set false to troubleshoot)
  person_workers: 8
  team_workers: 3
  repo_workers: 5         # Reduce to 3-4 if hitting GitHub rate limits
  filter_workers: 4       # Reduce to 2-3 if Jira timeouts occur
```

**Cache Management**:
```bash
python scripts/clear_repo_cache.py  # Clear repo cache if team repos change
```

See implementation in `src/collectors/github_graphql_collector.py` and `src/utils/repo_cache.py`.

### Configuration Validation

Before running collection or starting the dashboard, validate your configuration:

```bash
python validate_config.py
python validate_config.py --config path/to/config.yaml
```

**Validation Checks:**
- Config file exists and is valid YAML
- Required sections present (github, jira, teams)
- GitHub token format (ghp_*, gho_*, ghs_*, github_pat_*)
- Jira server URL format (http:// or https://)
- Team structure (name, members with github/jira)
- No duplicate team names
- Dashboard config (port 1-65535, positive timeouts/cache duration)
- Performance weights (sum to 1.0, range 0.0-1.0)
- Jira filter IDs are integers

**Exit Codes:**
- `0`: Validation passed
- `1`: Validation failed with errors

**Integration:**
Use in CI/CD pipelines or pre-commit hooks to catch config errors early.

### Running the Dashboard
```bash
# Start Flask web server
python -m src.dashboard.app

# Access at http://localhost:5001
# Available routes:
#   /                                 - Main overview
#   /team/<team_name>                 - Team-specific dashboard
#   /team/<team_name>/compare         - Team member comparison
#   /person/<username>                - Individual contributor dashboard
#   /comparison                       - Cross-team comparison
```

### Automation (macOS)

**Persistent Dashboard** - Run dashboard continuously in background:
```bash
# Load service (starts dashboard, auto-restarts on failure, persists across reboots)
launchctl load ~/Library/LaunchAgents/com.team-metrics.dashboard.plist

# Check status
launchctl list | grep team-metrics

# Stop/Start
launchctl stop com.team-metrics.dashboard
launchctl start com.team-metrics.dashboard

# View logs
tail -f logs/dashboard.log
```

**Scheduled Data Collection** - Daily at 10:00 AM:
```bash
# Load scheduler
launchctl load ~/Library/LaunchAgents/com.team-metrics.collect.plist

# Trigger manually
launchctl start com.team-metrics.collect

# View logs
tail -f logs/collect_data.log
```

**Files**:
- `scripts/start_dashboard.sh` - Dashboard wrapper script
- `scripts/collect_data.sh` - Collection wrapper script
- `~/Library/LaunchAgents/com.team-metrics.dashboard.plist` - Dashboard service
- `~/Library/LaunchAgents/com.team-metrics.collect.plist` - Collection scheduler
- `logs/` - All service logs
```

### Testing
```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests (417 tests, all passing)
# Execution time: ~5 seconds
pytest

# Run with coverage report
pytest --cov

# Run specific test file
pytest tests/unit/test_jira_metrics.py -v

# Run tests matching pattern
pytest -k "test_lead_time" -v

# Generate HTML coverage report
pytest --cov --cov-report=html
open htmlcov/index.html

# Run fast tests only (exclude slow integration tests)
pytest -m "not slow"
```

**Test Organization:**
- `tests/unit/` - Pure logic and utility function tests (90%+ coverage target)
  - `test_jira_metrics.py` - 26 tests for Jira metrics processing (NEW)
  - `test_dora_metrics.py` - 39 tests for DORA metrics & trends (EXPANDED)
  - `test_dora_trends.py` - 13 tests for DORA trend calculations
  - `test_performance_score.py` - 19 tests for performance scoring
  - `test_config.py` - 27 tests for configuration validation
  - `test_metrics_calculator.py` - 30+ tests for metrics calculations
- `tests/integration/` - End-to-end workflow tests
  - `test_dora_lead_time_mapping.py` - 19 tests for PR→Jira→Release mapping (all passing)
- `tests/collectors/` - API response parsing tests (70%+ coverage target)
  - `test_jira_collector.py` - 27 tests for Jira collector (EXPANDED)
- `tests/fixtures/` - Mock data generators for consistent test data
- `tests/conftest.py` - Shared pytest fixtures

**Coverage Status:**
| Module | Target | Actual | Status |
|--------|--------|--------|--------|
| **jira_metrics.py** | **70%** | **94.44%** | **✅** |
| **dora_metrics.py** | **70%** | **75.08%** | **✅** |
| date_ranges.py | 80% | 96.39% | ✅ |
| performance_scoring.py | 85% | 97.37% | ✅ |
| metrics.py (orchestration) | 85% | 32.18% | ⚠️ |
| github_graphql_collector.py | 70% | 17.06% | ⚠️ |
| jira_collector.py | 75% | 19.17% | ⚠️ |
| **Overall Project** | **80%** | **52.96%** | **⏳** |

*Note: Overall coverage (53%) reflects well-tested business logic modules (94-97% for jira_metrics, performance_scoring, date_ranges; 75% for dora_metrics) contrasted with lower-coverage data collectors (17-19%) and orchestration (32%). All 417 tests passing.

### Analysis Tools

Located in `tools/` directory. See `tools/README.md` for complete documentation.

**Quick Verification:**
```bash
# Verify collection completed successfully
./tools/verify_collection.sh
```

Checks for:
- NoneType errors (should be 0 after bug fix)
- Releases collected per team
- Issue mapping success (non-zero counts)
- Collection completion status
- Cache file freshness

**Detailed Release Analysis:**
```bash
# Analyze all releases with DORA metrics
python tools/analyze_releases.py

# Show specific release details
python tools/analyze_releases.py "Native Team" "Live - 21/Oct/2025"
```

Shows:
- Release list with issue counts
- Production vs staging breakdown
- Issue mapping statistics
- Full DORA metrics (deployment frequency, lead time, CFR, MTTR)
- Related issues per release

**Command Reference:**
- `docs/ANALYSIS_COMMANDS.md` - Complete guide with Python snippets, log analysis commands, and verification checklist
- Includes manual cache inspection examples
- Expected results after bug fix
- Next steps for post-collection workflow

## Logging

**Dual-Mode Logging**: Automatically adapts to environment
- **Interactive** (terminal): Colorful emoji output with progress indicators
- **Background** (cron/launchd): Structured JSON logs for machine parsing

**Configuration**: `config/logging.yaml` (10MB rotation, 10 backups, gzip compression)

**Files**:
- `logs/team_metrics.log` - All activity (JSON format)
- `logs/team_metrics_error.log` - Errors/warnings only

**CLI Flags**:
```bash
python collect_data.py -v        # Verbose (DEBUG)
python collect_data.py -q        # Quiet (warnings/errors only)
python collect_data.py --log-file /path/to/log
```

**Implementation**: See `src/utils/logging/` modules. Thread-safe, auto-detects TTY, works with launchd services unchanged.

## Architecture

### Data Flow

1. **Collection Phase** (`collect_data.py`):
   - **Parallel Collection** - Uses `ThreadPoolExecutor` for concurrent data gathering:
     - Teams collected in parallel (3 workers)
     - Repositories within each team collected in parallel (5 workers)
     - Person metrics collected in parallel (8 workers)
   - `GitHubGraphQLCollector` → Fetches PRs, reviews, commits from GitHub GraphQL API
   - `JiraCollector` → Fetches team filter results from Jira REST API
   - `MetricsCalculator` → Processes raw data into metrics
   - Cache saved to `data/metrics_cache_<range>.pkl` (pickle format)

2. **Dashboard Phase** (`src/dashboard/app.py`):
   - Flask app loads cached metrics on startup
   - Renders templates with pre-calculated metrics
   - Optional: Refresh button re-runs collection using GraphQL API

### Key Components

**Collectors** (`src/collectors/`):
- `github_graphql_collector.py` - **Primary collector**, uses GraphQL API v4 for efficiency
- `jira_collector.py` - Jira REST API with Bearer token authentication

**Models** (`src/models/`):
- `metrics.py` - `MetricsCalculator` class (605 lines)
  - Core orchestration and calculation methods
  - `calculate_team_metrics()` - Team-level aggregations with Jira filters
  - `calculate_person_metrics()` - Individual contributor metrics (90-day rolling window)
  - `calculate_team_comparison()` - Cross-team comparison data
  - Inherits from `DORAMetrics` and `JiraMetrics` mixins
- `dora_metrics.py` - `DORAMetrics` mixin class (635 lines)
  - DORA four key metrics (Deployment Frequency, Lead Time, CFR, MTTR)
  - Trend analysis and historical tracking
- `performance_scoring.py` - `PerformanceScorer` static class (270 lines)
  - Composite 0-100 performance scoring
  - Normalization and weighting utilities
  - Team size adjustments
- `jira_metrics.py` - `JiraMetrics` mixin class (226 lines)
  - Jira filter processing
  - Throughput, WIP, bug tracking
  - Scope trend analysis

**Configuration** (`src/config.py`):
- `Config` class loads from `config/config.yaml`
- Multi-team support with separate GitHub/Jira member lists per team
- Each team has Jira filter IDs for custom metrics

**Dashboard** (`src/dashboard/`):
- `app.py` - Flask routes and cache management
- `templates/` - Jinja2 templates with Plotly charts
  - `teams_overview.html` - Main dashboard (2-column grid)
  - `team_dashboard.html` - Team metrics with Jira integration
  - `person_dashboard.html` - Individual contributor view
  - `comparison.html` - Side-by-side team comparison with DORA metrics
- `static/css/main.css` - Theme CSS with dark mode variables
- `static/css/hamburger.css` - Hamburger menu styles with animations
- `static/js/theme-toggle.js` - Dark/light mode switcher
- `static/js/charts.js` - Shared chart utilities and CHART_COLORS constants

### Configuration Structure

See `config/config.example.yaml` for complete template. Key sections:

```yaml
github:
  token: "ghp_..."
  organization: "your-org"

jira:
  server: "https://jira.yourcompany.com"
  username: "username"  # NOT email
  api_token: "bearer_token"

teams:
  - name: "Backend"
    members:
      - name: "John Doe"
        github: "johndoe"
        jira: "jdoe"
    jira:
      filters:
        wip: 12345
        bugs: 12346
        incidents: 12347  # For DORA metrics

dashboard:
  port: 5001
  cache_duration_minutes: 60
  jira_timeout_seconds: 120

performance_weights:  # Optional - customize via Settings page
  prs: 0.15
  deployment_frequency: 0.10
  # ... (must sum to 1.0)
```

### Performance Scoring System

**Algorithm** (`src/models/performance_scoring.py:PerformanceScorer`):
- Composite 0-100 score using min-max normalization
- 10 metrics: PRs, reviews, commits, cycle time, merge rate, Jira completed, deployment frequency, lead time, CFR, MTTR
- Configurable weights via Settings page (http://localhost:5001/settings) or `config.yaml`
- Cycle time/lead time/CFR/MTTR inverted (lower is better)
- Team size normalization for fair per-capita comparison
- MetricsCalculator delegates to PerformanceScorer.calculate_performance_score()

### GitHub GraphQL Queries

**Benefits**: 50-70% fewer API calls, separate rate limit (5000 points/hour), single query for PRs+reviews+commits

**Queries**: See `src/collectors/github_graphql_collector.py:268-298` (PR query), `:118-134` (repository query)

Uses `CREATED_AT` ordering and cursor-based pagination for consistent results.

### Jira JQL Queries

**Anti-Noise Filtering** (`jira_collector.py:60`, `:195`):
- Queries include: `created >= -90d OR resolved >= -90d OR (statusCategory != Done AND updated >= -90d)`
- Prevents bulk admin updates (label changes) from including thousands of old closed tickets
- Only captures actual work: new issues, resolved issues, and active WIP

**Filter Queries**: Uses filter IDs from team config with dynamic time constraints (line 278)

**Time Windows**: Configurable via `--date-range` parameter (default: 90 days)

### Dashboard UI Features

- **Hamburger Menu**: Team links auto-generate from config/cache
- **Theme Toggle**: Dark/light mode with localStorage persistence
- **Date Range Selector**: Preset options with URL parameter persistence
- **Export**: 8 routes (CSV/JSON for team/person/comparison/team-members)
- **Reload Button**: Shows ⏳ during operation (`reloadCache()` in `theme-toggle.js`)

## UI Architecture

**3-Tier Template Inheritance**:
1. `base.html` - Master template (hamburger menu, footer, theme toggle)
2. Abstract templates - `detail_page.html`, `landing_page.html`, `content_page.html`
3. Concrete pages - Teams overview, team dashboard, person dashboard, comparison

**Styles & Components**:
- **Theme**: CSS variables in `main.css`, `data-theme` attribute, `theme-toggle.js`
- **Charts**: Plotly.js with semantic color palette (`charts.js`), theme-aware rendering
- **Hamburger Menu**: Pure CSS (checkbox hack), responsive, styles in `hamburger.css`

**Export**: 8 endpoints in `app.py` (lines 1004-1259), CSV/JSON formats with UTF-8 encoding

## Important Implementation Details

### Jira Integration
- Uses **Bearer token** authentication (not username/password)
- SSL verification disabled (`verify_ssl=False`) for self-signed certificates
- Filter IDs are specific to each Jira instance - use `list_jira_filters.py` to discover
- Filters define team metrics (WIP, bugs, throughput, etc.)

**Jira Query Optimization (Anti-Noise Filtering):**
- Person queries filter `updated >= -90d` to only apply to non-Done tickets
- Query: `assignee = "user" AND (created >= -90d OR resolved >= -90d OR (statusCategory != Done AND updated >= -90d))`
- **Rationale**: Prevents bulk administrative updates (e.g., mass label changes) from polluting results with thousands of closed tickets
- Only captures actual work: new issues, resolved issues, and active WIP (not closed items with label updates)
- See `src/collectors/jira_collector.py:60` (project query) and `:195` (person query)

**Known Jira Library Limitations:**

*Issue Fetching Bug (Fixed in Code):*
The Jira Python library (v3.x) has a bug when using `fields='key'` parameter in `search_issues()`. When iterating over Fix Version data, the library encounters malformed issue data and throws:
```
TypeError: argument of type 'NoneType' is not iterable
  at jira/client.py:3686 in search_issues
  if k in iss.raw.get("fields", {}):
```

*Workaround (Already Implemented):*
In `src/collectors/jira_collector.py`, the `_get_issues_for_version()` method omits the `fields` parameter:

```python
# Fetch all fields instead of just 'key' to avoid library bug
issues = self.jira.search_issues(jql, maxResults=1000)
```

*Trade-off:* Fetches ~10-15 fields per issue instead of 1, slightly increasing API response size. However, this ensures stability and prevents collection failures.

*Commit:* 6451da5 (Jan 13, 2026)

### Export Functionality

**Routes** (`src/dashboard/app.py:891-997`):
- Team, Person, Comparison, Team Members (CSV & JSON for each)
- Filenames include date: `team_native_metrics_2026-01-14.csv`

**Helpers**: `flatten_dict()`, `format_value_for_csv()`, `create_csv_response()`, `create_json_response()`

**Testing**: 18 tests in `tests/dashboard/test_app.py`

### DORA Metrics: How Releases Are Counted

**Release Source**: Uses Jira Fix Versions (not GitHub Releases) for deployment tracking.

**Three-Tier Filtering** (`jira_collector.py:649-758`):
1. **Status Check**: Only released versions (not planned/future), releaseDate in past
2. **Pattern Matching**: Supports `"Live - 6/Oct/2025"`, `"Beta - 15/Jan/2026"`, `"RA_Web_2025_11_25"` formats (see `_parse_fix_version_name()` lines 760-846)
3. **Team Member Filtering**: Only issues assigned to team members (assignee field only)

**Four-Tier Filtering for Lead Time** (`collect_data.py:449-457`):
4. **Cross-Team Filtering**: Releases with zero team-assigned issues are filtered out before metrics calculation
   - Prevents teams' PRs from matching against other teams' releases in time-based fallback
   - Example: Native team (8 releases) no longer matches against WebTC team releases (25+ filtered out)
   - Improves lead time accuracy from unrealistic values (1.5 days) to realistic values (7+ days)

**Why Filtering Matters**: Without filtering, metrics inflated 2-3x. Typical realistic values: 0.5-2.0 deployments/week per team.

**See Also**:
- `docs/JIRA_FIX_VERSION_TROUBLESHOOTING.md`
- `docs/LEAD_TIME_FIX_RESULTS.md` - Cross-team filtering implementation details

### Lead Time for Changes: How It's Calculated

**Measures**: Time from code commit (PR merge) to production deployment.

**Two-Method Approach** (Jira-based preferred, time-based fallback):

#### Method 1: Jira-Based Mapping (Preferred - Most Accurate)
Flow: PR → Jira Issue → Fix Version → Deployment

1. **Extract Issue Key from PR**:
   - Searches PR title: `"[RSC-123] Add feature"` → `RSC-123`
   - Searches branch name: `feature/RSC-123-add-feature` → `RSC-123`
   - Pattern: `([A-Z]+-\d+)`

2. **Map to Fix Version**:
   - Uses `issue_to_version_map` built during collection
   - Example: `RSC-123` → `"Live - 21/Oct/2025"`

3. **Calculate Lead Time**:
   ```
   Lead Time = Fix Version Date - PR Merged Date
   ```

#### Method 2: Time-Based Fallback
When Jira mapping unavailable:
- Finds next production deployment after PR merge
- Lead Time = Next Deployment - PR Merge
- **Cross-Team Filtering**: Only searches releases where the team has assigned issues (prevents contamination from other teams' releases)

**Release Workflow Support**:
Works with cherry-pick workflows:
- Feature branches merge to `master`: `feature/RSC-456-*` → `master`
- Release branches created later: `release/Rescue-7.55-AI`
- Commits cherry-picked: `master` → `release/Rescue-7.55-AI`
- Connection tracked through Jira Fix Versions (not git history)

**Performance Levels** (DORA standard):
- **Elite**: < 24 hours (< 1 day)
- **High**: < 168 hours (< 1 week)
- **Medium**: < 720 hours (< 1 month)
- **Low**: ≥ 720 hours (≥ 1 month)

### Cache Management
- Pickle format: `{'teams': {...}, 'persons': {...}, 'comparison': {...}, 'timestamp': datetime}`
- Dashboard checks cache age (default: 60 min) before auto-refresh
- Manual refresh via button or `/api/refresh` endpoint

### Data Processing Pipeline
1. Raw data collected as lists of dicts
2. Converted to pandas DataFrames in `MetricsCalculator`
3. Aggregated into structured metrics dictionaries
4. Cached to disk
5. Loaded by Flask and passed to Jinja templates

## Debugging

**GitHub API Issues**:
```bash
# Check GraphQL rate limit
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.github.com/rate_limit
```

**Jira Authentication**:
```bash
# Test Jira connection
curl -H "Authorization: Bearer YOUR_TOKEN" -k \
  https://jira.yourcompany.com/rest/api/2/serverInfo
```

**Cache Issues**:
- Delete `data/metrics_cache.pkl` to force fresh collection
- Check Flask logs for cache load errors

## Common Modifications

**Adding a new metric**:
1. Add collection in `GitHubGraphQLCollector._fetch_*()` or `JiraCollector`
2. Add calculation in `MetricsCalculator.calculate_*_metrics()`
3. Update template to display (e.g., `team_dashboard.html`)
4. Re-run `collect_data.py` to regenerate cache

**Adding a new team**:
1. Add team block to `config/config.yaml`
2. Use `list_jira_filters.py` to find filter IDs
3. Run `collect_data.py` to collect team data
4. Team automatically appears in dashboard

## Date Ranges

**Recommended Ranges (Automated Collection)**:
- Days: `30d`, `60d`, `90d`, `180d`, `365d`
- Years: `2025` (previous year for annual reviews)

**Also Supported** (manual collection only):
- Quarters: `Q1-2025`, `Q2-2024`, `Q3-2023`, `Q4-2026`
- Any year: `2024`, `2025`, `2023`
- Custom: `YYYY-MM-DD:YYYY-MM-DD` (e.g., `2024-01-01:2024-12-31`)

**Cache Files**: Each range creates separate cache (`metrics_cache_90d.pkl`), allowing switching without re-collection.

**Dashboard Selector**: Preset options in hamburger menu, persists via `?range=` URL parameter.

**Implementation**: See `src/utils/date_ranges.py` for parsing utilities.

**Note**: Automated collection via `scripts/collect_data.sh` only collects the 6 recommended ranges for faster performance (2-4 min vs 5-10 min). See `docs/COLLECTION_CHANGES.md` for rationale.
