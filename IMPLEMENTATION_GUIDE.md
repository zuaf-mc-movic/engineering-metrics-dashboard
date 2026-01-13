# Team Metrics Implementation Guide

## What Was Implemented

This implementation adds comprehensive team and person-level metrics tracking for both GitHub and Jira, using **GraphQL API** for efficient GitHub data collection and **Bearer token authentication** for self-hosted Jira.

### Architecture Overview

#### GraphQL API for GitHub
The system uses GitHub's **GraphQL API v4** instead of REST API for data collection:

**Benefits:**
- **Separate rate limit**: 5000 points/hour (independent from REST API's 5000 requests/hour)
- **Efficient queries**: Fetch PRs, reviews, and commits in single requests
- **Fewer API calls**: 50-70% reduction compared to REST API
- **Better pagination**: Built-in cursor-based pagination
- **Faster collection**: Reduced API round-trips

**Implementation:**
- `GitHubGraphQLCollector` in `src/collectors/github_graphql_collector.py`
- Used by both `collect_data.py` (offline collection) and dashboard refresh
- Replaces the legacy `GitHubCollector` (REST API) for all collection operations

**Key Methods:**
- `_get_team_repositories()` - Fetch team repos via GraphQL
- `_collect_repository_metrics()` - Collect PRs, reviews in one query
- `_collect_commits_graphql()` - Fetch commits with pagination
- `collect_person_metrics()` - Person-level data collection

#### Jira Bearer Token Authentication
For self-hosted Jira instances, the system uses **Bearer token authentication**:

**Configuration:**
- `username` field (NOT `email`) in config
- Bearer token in `api_token` field
- SSL verification automatically disabled (`verify_ssl=False`)

**Implementation:**
- `JiraCollector` in `src/collectors/jira_collector.py` (line 14)
- Authorization header: `Authorization: Bearer {token}`
- Supports self-signed certificates (SSL bypass)

**Authentication Test:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" -k https://jira.yourcompany.com/rest/api/2/serverInfo
```

### New Features

1. **Multi-Team Support**
   - Separate dashboards for Native and WebTC teams
   - Team-specific GitHub and Jira metrics
   - Side-by-side team comparison view

2. **Jira Filter Integration**
   - Support for collecting metrics via Jira filter IDs
   - Throughput tracking (completed items over 12 weeks)
   - WIP statistics with age distribution
   - Flagged/blocked issues tracking
   - Created vs Resolved bug tracking

3. **Person-Level Metrics**
   - Individual GitHub activity (PRs, reviews, commits)
   - Person-specific Jira issue completion
   - Time period filtering support
   - Clickable team member cards

4. **Enhanced Dashboard**
   - Team dashboards with member activity grids
   - Person dashboards with detailed metrics
   - Team comparison with side-by-side charts
   - Jira filter results visualization

5. **Flexible Date Range Support**
   - Multiple date range formats (30d, 90d, Q1-2025, 2024, custom)
   - Separate cache files per date range
   - Dashboard date range selector with persistence
   - Consistent filtering across GitHub and Jira metrics

### Date Range Architecture

The system supports flexible date ranges through a comprehensive architecture:

**Date Range Formats Supported:**
- **Days**: `30d`, `60d`, `90d`, `180d`, `365d`
- **Quarters**: `Q1-2025`, `Q2-2024`, `Q3-2023`, `Q4-2026`
- **Years**: `2024`, `2025`, `2023`
- **Custom**: `YYYY-MM-DD:YYYY-MM-DD` (e.g., `2024-01-01:2024-12-31`)

**Implementation Components:**

1. **Date Range Utilities** (`src/utils/date_ranges.py`):
   - `parse_date_range(range_str)` - Converts range string to start/end dates
   - `get_cache_filename(range_key)` - Returns cache filename for range
   - `get_preset_ranges()` - Lists available preset ranges
   - `get_available_ranges()` - Discovers existing cache files

2. **Data Collection** (`collect_data.py`):
   - `--date-range` CLI parameter accepts any supported format
   - Creates separate cache file per range: `metrics_cache_{range_key}.pkl`
   - Adds `date_range` metadata to cache with description and bounds
   - Example: `python collect_data.py --date-range Q1-2025`

3. **Dashboard Integration** (`src/dashboard/app.py`):
   - Context processor injects `current_range` and `available_ranges` globally
   - Routes check `?range=` query parameter and reload appropriate cache
   - Cache management: `load_cache_from_file(range_key)` function
   - JavaScript preserves range parameter across navigation

4. **UI Components** (`src/dashboard/templates/base.html`):
   - Date range selector in hamburger menu
   - Dropdown populated from discovered cache files
   - Selection persists via `?range=` URL parameter
   - JavaScript auto-appends range to all internal links

5. **GitHub Collection Filtering** (`src/collectors/github_graphql_collector.py`):
   - PRs filtered by creation date: `if pr_created < self.since_date: continue`
   - Reviews filtered by submission date: `if submitted < self.since_date: continue`
   - Consistent date filtering ensures accurate PR:review ratios
   - Pagination limit: 10 pages per repo (500 PRs max)

6. **Jira Collection Filtering** (`src/collectors/jira_collector.py`):
   - Project queries add time constraint: `(created >= -Nd OR resolved >= -Nd)`
   - Person queries filter by activity: `(created >= -Nd OR resolved >= -Nd OR (statusCategory != Done AND updated >= -Nd))`
   - Prevents noise from bulk administrative updates on closed issues

   **Jira Library Limitation:**
   The `_get_issues_for_version()` method uses default fields instead of `fields='key'` to work around a bug in the Jira Python library. While this fetches more data than strictly necessary, it prevents collection failures when the library encounters malformed issue data. See [Jira Fix Version Troubleshooting](docs/JIRA_FIX_VERSION_TROUBLESHOOTING.md#issue-8-internal-library-error-when-fetching-version-issues) for details.

**Cache File Naming Convention:**
- `metrics_cache_30d.pkl` - 30-day data
- `metrics_cache_90d.pkl` - 90-day data (default)
- `metrics_cache_Q1-2025.pkl` - Q1 2025 data
- `metrics_cache_2024.pkl` - Full year 2024
- `metrics_cache_2024-01-01_2024-12-31.pkl` - Custom range

**Cache Metadata Structure:**
```python
{
    'range_key': '90d',
    'date_range': {
        'description': 'Last 90 days',
        'start_date': datetime(2024, 10, 13),
        'end_date': datetime(2026, 1, 11)
    },
    'teams': {...},
    'persons': {...},
    'comparison': {...},
    'timestamp': datetime.now()
}
```

## Setup Instructions

### Step 1: Discover Your Jira Filter IDs

First, you need to find the filter IDs for your Jira filters.

1. Make sure your `config/config.yaml` has your Jira credentials:
   ```yaml
   jira:
     server: "https://your-jira-instance.com"
     username: "your_jira_username"  # Use username, NOT email
     api_token: "your_bearer_token"  # Bearer token for authentication
     project_keys:
       - "YOUR_PROJECT"
   ```

   **Note:** For self-hosted Jira, use `username` (not `email`) and a Bearer token.

2. Run the filter discovery script:
   ```bash
   python list_jira_filters.py
   ```

3. Search for your team-specific filters:
   ```bash
   python list_jira_filters.py "Rescue Native"
   python list_jira_filters.py "Rescue WebTC"
   ```

4. Copy the filter IDs from the output.

### Step 2: Update Configuration

Update your `config/config.yaml` with the team configurations and filter IDs:

```yaml
github:
  token: "your_github_token"
  organization: "your-org-name"  # e.g., "goto"
  days_back: 90

jira:
  server: "https://your-jira-instance.com"
  username: "your_jira_username"  # Use username, NOT email
  api_token: "your_bearer_token"  # Bearer token for authentication
  project_keys:
    - "YOUR_PROJECT_KEY"

teams:
  - name: "Native"
    display_name: "Native Team"
    github:
      team_slug: "itsg-rescue-native"
      members:
        - "daniella-b"
        - "bigfoot-goto"
        - "lcsanky"
        - "goto-balamber"
        - "andkovacs"
        - "armeszaros"
        - "gpaless-goto"
        - "psari-goto"
        - "norbert-toth-goto"
    jira:
      members:
        - "dbarsony"
        - "aborsanyihortobagyi"
        - "lcsanky"
        - "zfilyo"
        - "andkovacs"
        - "armeszaros"
        - "gpaless"
        - "psari"
        - "ntoth"
      filters:
        backlog_in_progress: 12345  # REPLACE with actual filter ID
        bugs: 12346
        bugs_created: 12347
        bugs_resolved: 12348
        completed_12weeks: 12349
        flagged_blocked: 12350
        recently_released: 12351
        scope: 12352
        wip: 12353

  - name: "WebTC"
    display_name: "WebTC Team"
    github:
      team_slug: "itsg-rescue-webtc"
      members:
        - "icsiza"
        - "teklavass"
        - "rgolle"
        - "KrisztianSzabados"
        - "bkissbarnabas"
    jira:
      members:
        - "icsiza"
        - "tvass"
        - "rgolle"
        - "kszabados"
        - "bkiss"
      filters:
        backlog_in_progress: 22345  # REPLACE with actual filter ID
        bugs: 22346
        bugs_created: 22347
        bugs_resolved: 22348
        completed_12weeks: 22349
        flagged_blocked: 22350
        recently_released: 22351
        scope: 22352
        wip: 22353

time_periods:
  last_n_days: [7, 14, 30, 60, 90]
  quarters_enabled: true
  custom_range_enabled: true
  max_days_back: 365

activity_thresholds:
  minimum_values:
    prs_per_month: 5
    reviews_per_month: 10
    commits_per_month: 20
  trend_decline_threshold_percent: 20
  below_average_threshold_percent: 70

dashboard:
  port: 5000
  debug: true
  cache_duration_minutes: 60
```

### Step 3: Collect Data

Run the data collection script:

```bash
python collect_data.py
```

This will:
- Collect GitHub metrics for both teams
- Collect Jira metrics via filter IDs
- Calculate team-level aggregations
- Collect person-level metrics for all team members
- Save everything to the cache

**Note:** First run may take 5-15 minutes depending on the amount of data.

### Step 4: Launch Dashboard

Start the Flask dashboard:

```bash
python -m src.dashboard.app
```

Open in your browser: http://localhost:5000

## Dashboard Navigation

### Main Dashboard
- Shows overall GitHub and Jira metrics
- Links to team dashboards

### Team Dashboards
- **URL:** `/team/Native` or `/team/WebTC`
- Shows team-level GitHub metrics (PRs, reviews, commits)
- Shows Jira filter results (throughput, WIP, flagged items, bugs)
- Displays team member activity grid (clickable to person pages)

### Person Dashboards
- **URL:** `/person/<username>`
- Shows individual GitHub activity
- Shows individual Jira issue completion
- Time period filtering (future enhancement)

### Team Comparison
- **URL:** `/comparison`
- Side-by-side comparison of Native vs WebTC
- GitHub metrics comparison
- Jira metrics comparison (if available)

## Troubleshooting

### "Team not found" error
- Check that your config.yaml has the `teams` section
- Verify team names match (case-sensitive)
- Re-run `python collect_data.py` after config changes

### "No metrics found" error
- Run `python collect_data.py` to collect data first
- Check that GitHub token has access to the organization
- Verify team members' usernames are correct

### Jira filter errors
- Verify filter IDs are correct using `python list_jira_filters.py`
- Check that your Jira account has access to the filters
- Ensure filters are marked as "favourite" in Jira

### GitHub API rate limiting
- GitHub has rate limits (5000 requests/hour for authenticated)
- The collector limits PRs to 50 per repo and commits to 100 per repo
- If you hit limits, wait an hour or reduce `days_back` in config

## File Structure

```
team_metrics/
├── config/
│   ├── config.yaml              # Your configuration (gitignored)
│   └── config.example.yaml      # Template with team setup
├── data/
│   └── metrics_cache.pkl        # Cached metrics data
├── src/
│   ├── collectors/
│   │   ├── github_collector.py  # Enhanced with team methods
│   │   └── jira_collector.py    # Enhanced with filter support
│   ├── models/
│   │   └── metrics.py           # Enhanced with team/person calculations
│   ├── dashboard/
│   │   ├── app.py               # Enhanced with new routes
│   │   └── templates/
│   │       ├── team_dashboard.html
│   │       ├── person_dashboard.html
│   │       └── comparison.html
│   ├── utils/
│   │   ├── time_periods.py      # Time period utilities
│   │   ├── activity_thresholds.py
│   │   └── jira_filters.py      # Filter discovery
│   └── config.py                # Enhanced with team properties
├── collect_data.py              # Enhanced for multi-team collection
└── list_jira_filters.py         # NEW: Filter discovery CLI
```

## Key Implementation Details

### Data Collection Flow
1. **Team Collection:** For each team, collect GitHub and Jira metrics
2. **Person Collection:** For each unique member, collect full-year metrics
3. **Aggregation:** Calculate team averages, trends, comparisons
4. **Caching:** Save to pickle file with structure:
   ```python
   {
     'teams': {
       'Native': {...},
       'WebTC': {...}
     },
     'persons': {
       'username': {...}
     },
     'comparison': {...},
     'timestamp': datetime
   }
   ```

### Jira Filter Mapping
Each team has 9 filters:
- `backlog_in_progress`: Items in backlog or in progress
- `bugs`: All bugs
- `bugs_created`: Newly created bugs
- `bugs_resolved`: Resolved bugs
- `completed_12weeks`: Completed in last 12 weeks (for throughput)
- `flagged_blocked`: Flagged/blocked items
- `recently_released`: Recently released items
- `scope`: Team scope
- `wip`: Work in progress items

### Activity Thresholds (Future Enhancement)
The system supports tracking who "needs to be pushed to do more" via:
- Below team average detection
- Declining trend detection
- Custom minimum thresholds

This is implemented in `src/utils/activity_thresholds.py` but not yet integrated into the UI.

## Frontend Architecture

### Template System

The dashboard uses a 3-tier Jinja2 template inheritance system for maintainability and consistency.

**Tier 1: Master Template (`base.html`)**
- Purpose: Provides universal structure for all pages
- Contains: `<head>` with CSS/JS imports, hamburger menu, footer
- Key features:
  - Hamburger menu (checkbox-based, pure CSS, no JavaScript for open/close)
  - Footer with dynamic year (via Flask context processor in app.py)
  - Theme toggle integration
  - Plotly.js CDN import
- Blocks provided: `title`, `extra_css`, `extra_js`, `header`, `content`

**Tier 2: Abstract Templates**

Three specialized templates extend base.html for different page types:

1. `detail_page.html` - For dashboards with headers and navigation
   - Used by: team_dashboard, person_dashboard, comparison, team_members_comparison
   - Provides: Structured header with title, subtitle, nav links
   - Blocks: `page_title`, `header_title`, `header_subtitle`, `additional_nav`, `main_content`

2. `landing_page.html` - For hero-style overview pages
   - Used by: teams_overview
   - Provides: Centered hero section with large title
   - Blocks: `page_title`, `hero_title`, `hero_subtitle`, `hero_meta`, `main_content`

3. `content_page.html` - For static content pages
   - Used by: documentation
   - Provides: Simple header and content area
   - Blocks: `page_title`, `header_title`, `header_subtitle`, `main_content`

**Tier 3: Concrete Templates**
- Extend appropriate abstract template
- Override blocks to provide page-specific content
- No duplication of header/footer/menu code
- Examples: teams_overview.html extends landing_page.html, team_dashboard.html extends detail_page.html

### Navigation System

**Hamburger Menu Implementation:**
- Location: `src/dashboard/static/css/hamburger.css`
- Technique: Checkbox hack (no JavaScript needed for open/close)
- Structure:
  ```html
  <input type="checkbox" id="hamburger-toggle" class="hamburger-checkbox">
  <label for="hamburger-toggle" class="hamburger-icon">...</label>
  <div class="hamburger-overlay"></div>
  <nav class="hamburger-menu">...</nav>
  ```
- Features:
  - Fixed position top-right (z-index: 1001)
  - 50x45px blue button with 3 white bars (made prominent after user feedback)
  - Slides in from right (300px width)
  - Dark overlay backdrop when open
  - Animated menu items (staggered fade-in)
  - Closes on outside click or link selection
  - Responsive: 250px on tablet, 80% width on mobile

**Navigation Items:**
1. 🏠 Home - Returns to teams overview
2. 📚 Documentation - Opens help page
3. 🌓 Theme Toggle - Switch light/dark mode (persists via localStorage)

### Chart Color System

**Semantic Colors (`charts.js`):**
```javascript
const CHART_COLORS = {
    CREATED: '#e74c3c',      // Red - bugs filed, scope added
    RESOLVED: '#2ecc71',     // Green - bugs fixed, scope completed
    NET: '#3498db',          // Blue - net difference (created - resolved)
    TEAM_PRIMARY: '#3498db',
    TEAM_SECONDARY: '#9b59b6',
    PRS: '#3498db',
    REVIEWS: '#9b59b6',
    COMMITS: '#27ae60',
    JIRA_COMPLETED: '#f39c12',
    JIRA_WIP: '#e74c3c',
    PIE_PALETTE: ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22']
};
```

**Color Usage:**
- **Bugs Trend Chart**: Created=Red, Resolved=Green, Net=Blue
- **Scope Trend Chart**: Created=Red, Resolved=Green, Net=Blue
- **Throughput Pie Charts**: Use PIE_PALETTE for issue types
- **Team Comparison Bar Charts**: TEAM_PRIMARY (blue) vs TEAM_SECONDARY (purple)

**Theme-Aware Colors:**
- `getChartColors()` function in `charts.js` provides dynamic colors based on current theme
- Returns: `paper_bgcolor`, `plot_bgcolor`, `font_color`, `grid_color`
- Charts automatically update when theme is toggled

### Footer Implementation

**Context Processor (`app.py`):**
```python
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}
```

- Injects `current_year` variable into all templates
- Footer displays: "© 2026 Team Metrics Dashboard. [Links]"
- Automatically updates each year without code changes

## Next Steps

1. **Run Filter Discovery:** Get your actual filter IDs
2. **Update Config:** Replace placeholder IDs with real ones
3. **Collect Data:** Run `python collect_data.py`
4. **Launch Dashboard:** Run `python -m src.dashboard.app`
5. **Verify:** Check team and person dashboards work correctly

## Support

If you encounter issues:
1. Check the console output from `collect_data.py` for errors
2. Verify GitHub token has organization access
3. Verify Jira API token has filter access
4. Check that all team members exist in both GitHub and Jira
5. Ensure filter IDs are correct

## Future Enhancements

Potential improvements not yet implemented:
- Dynamic time period selection in person dashboards
- Activity threshold indicators ("needs attention" badges)
- Quarterly comparison views
- Export to CSV/Excel
- Historical trend tracking
- Slack/email notifications for blocked items

## Testing Infrastructure

### Test Organization

```
tests/
├── unit/                               # Pure logic tests (95%+ coverage target)
│   ├── test_time_periods.py            # 30+ tests: quarters, periods, date parsing
│   ├── test_activity_thresholds.py     # 15+ tests: averages, trends, flags
│   ├── test_collect_data.py            # 14+ tests: username mapping, config parsing
│   └── test_metrics_calculator.py      # 30+ tests: PR/review/commit metrics
├── collectors/                         # API parsing tests (70%+ coverage target)
│   ├── test_github_collector.py        # 10+ tests: GraphQL response parsing
│   └── test_jira_collector.py          # 12+ tests: status times, throughput, WIP
├── fixtures/
│   └── sample_data.py                  # Mock data generators
├── conftest.py                         # Shared pytest fixtures
└── pytest.ini                          # Pytest configuration
```

### Testing Stack

- **pytest** (7.4+) - Modern Python testing framework
- **pytest-cov** - Coverage reporting (HTML + terminal)
- **pytest-mock** - Mocking utilities
- **freezegun** - Time-based testing (freeze dates for reproducibility)
- **responses** - HTTP request mocking (GitHub/Jira API calls)

### Running Tests

```bash
# Run all tests
pytest                          # Output: 111 passed in ~2.5s

# With coverage
pytest --cov                    # Overall: 83% coverage

# Specific module coverage
pytest --cov=src.utils.time_periods --cov-report=term-missing

# HTML coverage report
pytest --cov --cov-report=html
open htmlcov/index.html

# Run specific test file
pytest tests/unit/test_time_periods.py -v

# Run tests matching pattern
pytest -k "test_quarter" -v

# Fast tests only (exclude @pytest.mark.slow)
pytest -m "not slow"
```

### Test Structure (AAA Pattern)

All tests follow Arrange-Act-Assert pattern:

```python
def test_parse_period_to_dates_90d_format():
    # Arrange
    period = "90d"
    current_date = datetime(2025, 3, 15, tzinfo=timezone.utc)

    # Act
    with freeze_time(current_date):
        start_date, end_date = parse_period_to_dates(period)

    # Assert
    expected_start = datetime(2024, 12, 15, tzinfo=timezone.utc)
    assert start_date == expected_start
    assert end_date == current_date
```

### Shared Fixtures (`conftest.py`)

Available in all tests:

- `sample_pr_dataframe()` - Mock DataFrame with 3 PRs
- `sample_reviews_dataframe()` - Mock review data
- `sample_commits_dataframe()` - Mock commit data
- `empty_dataframes()` - Empty DataFrames for edge case testing
- `sample_team_config()` - Mock team configuration
- `sample_jira_issues()` - Mock Jira issue list
- `sample_github_graphql_response()` - Mock GraphQL API response

### Mock Data Generators (`fixtures/sample_data.py`)

Functions for consistent test data:

- `get_github_graphql_pr_response()` - Full PR response with reviews/commits
- `get_jira_issue_response()` - Issue with changelog and status transitions
- `get_jira_filter_response()` - Filter results with multiple issues

### Coverage Goals

| Module | Target | Actual | Status |
|--------|--------|--------|--------|
| time_periods.py | 95% | 96% | ✅ |
| activity_thresholds.py | 90% | 92% | ✅ |
| metrics.py | 85% | 87% | ✅ |
| github_graphql_collector.py | 70% | 72% | ✅ |
| jira_collector.py | 75% | 78% | ✅ |
| **Overall Project** | **80%** | **83%** | **✅** |

### Adding New Tests

1. **Choose test file** based on module being tested
2. **Use appropriate fixtures** from conftest.py or sample_data.py
3. **Follow AAA pattern** (Arrange, Act, Assert)
4. **Name descriptively**: `test_<function>_<scenario>_<expected_result>`
5. **Parametrize similar tests** to reduce duplication:
   ```python
   @pytest.mark.parametrize("invalid_quarter", [0, 5, -1, 13])
   def test_get_quarter_dates_invalid_quarter_raises_error(invalid_quarter):
       with pytest.raises(ValueError):
           get_quarter_dates(invalid_quarter, 2025)
   ```

### Best Practices

- ✅ Tests run fast (< 100ms each, no I/O)
- ✅ No real API calls (use @responses.activate or mocks)
- ✅ Freeze time for date-dependent tests (freezegun)
- ✅ Test edge cases (empty inputs, None values, zero division)
- ✅ One assertion per test (single responsibility)
- ✅ Clear failure messages
