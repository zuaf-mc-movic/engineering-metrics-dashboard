# Team Metrics Dashboard

A Python-based metrics collection and visualization tool for tracking team performance across GitHub and Jira using **GraphQL API** for efficient data collection.

## Features

- **GitHub Metrics Collection (GraphQL API)**:
  - Pull Request metrics (cycle time, review time, merge rate)
  - Code review metrics (engagement, response times, cross-team reviews)
  - Contributor activity tracking (commits, lines changed)
  - PR size distribution and trends

- **Jira Integration (Self-Hosted)**:
  - Team-specific Jira filter metrics
  - Throughput tracking (completed items per week)
  - WIP statistics and age distribution
  - Bug tracking (created vs resolved)
  - Flagged/blocked item monitoring
  - **Incident tracking** for DORA Change Failure Rate and MTTR
  - Interactive Jira charts on team dashboards:
    - **Throughput by Issue Type**: Pie chart showing distribution of completed work by type (Story, Bug, Task, etc.)
    - **WIP Items by Status**: Horizontal bar chart showing work-in-progress distribution across statuses
    - **WIP Age Distribution**: Bar chart showing how long items have been in WIP status
    - **Bugs Created vs Resolved**: Dual-panel chart (90 days) with trend comparison and net difference showing backlog growth
    - **Scope Created vs Resolved**: Dual-panel chart (90 days) with trend comparison and net difference showing backlog health
  - Bearer token authentication support
  - SSL verification bypass for self-signed certificates

- **DORA Metrics** (DevOps Research and Assessment):
  - **Deployment Frequency**: Production deployment rate per week with weekly trend chart
  - **Lead Time for Changes**: Time from commit to production with weekly trend chart (Jira Fix Version mapping)
    - **Cross-team filtering**: Automatically filters releases to only team-relevant deployments for accurate lead time
  - **Change Failure Rate**: Percentage of deployments causing incidents with weekly trend chart (requires incident tracking)
  - **Mean Time to Recovery**: Median time to resolve production incidents with weekly trend chart (requires incident tracking)
  - Performance level classification (Elite, High, Medium, Low) based on DORA benchmarks
  - Automatic correlation between deployments and incidents
  - Weekly trend visualizations for all 4 metrics on team dashboards

- **Team-Based Organization**:
  - Multiple team support with separate configurations
  - Team-level metrics and dashboards
  - Person-level metrics for individual contributors
  - Team comparison views

- **Web Dashboard**: Interactive Flask-based visualization
  - Main overview dashboard with 2-column team layout
    - Organized sections: GitHub metrics, Jira metrics, DORA metrics
    - At-a-glance DORA performance levels with color-coded badges
  - Individual team dashboards with Jira metrics and DORA trend charts
  - Person dashboards with trend visualizations
    - 4 interactive trend charts (PRs, reviews, commits, code changes)
    - Flexible date ranges: 30d, 60d, 90d, 180d, 365d, quarters, years, custom
  - Team comparison dashboard with side-by-side charts, DORA metrics, and performance scores
  - Team member comparison with performance rankings and leaderboard
  - Dark mode support across all views
  - Responsive chart layouts with optimal sizing
  - 🎨 **Semantic Chart Colors**: Consistent color coding (Red=Created, Green=Resolved, Blue=Net) across all charts for intuitive understanding
  - 🍔 **Hamburger Navigation**: Accessible slide-out menu on all pages with theme toggle, home, and documentation links
  - 🌓 **Light/Dark Theme**: Persistent theme selection with modern design and smooth transitions

- **Efficient Data Collection**:
  - GraphQL API for GitHub (50-70% fewer API calls vs REST)
  - Separate rate limits from REST API (5000 points/hour)
  - Offline collection with caching (`collect_data.py`)
  - Dashboard refresh button using GraphQL

## Known Limitations

**Jira API Integration:**
- The Jira Python library has a known bug when fetching specific fields from Fix Versions. We use a workaround (fetching default fields) that slightly increases API response sizes but ensures reliability. This is transparent to users and requires no configuration. See [Troubleshooting Guide](docs/JIRA_FIX_VERSION_TROUBLESHOOTING.md#issue-8-internal-library-error-when-fetching-version-issues) for technical details.

## Project Structure

```
team_metrics/
├── src/
│   ├── collectors/
│   │   ├── github_graphql_collector.py  # Primary GitHub data collector (GraphQL API v4)
│   │   └── jira_collector.py            # Jira REST API collector with Bearer auth
│   ├── models/
│   │   ├── __init__.py                  # Package exports (backward compatibility)
│   │   ├── metrics.py                   # Core MetricsCalculator class (605 lines)
│   │   ├── dora_metrics.py              # DORA metrics calculations (635 lines)
│   │   ├── performance_scoring.py       # Performance scoring utilities (270 lines)
│   │   └── jira_metrics.py              # Jira metrics processing (226 lines)
│   ├── utils/
│   │   └── date_ranges.py               # Date range and period utilities
│   ├── dashboard/
│   │   ├── app.py                       # Flask application and routes
│   │   ├── templates/
│   │   │   ├── base.html                # Master template (hamburger menu, footer)
│   │   │   ├── detail_page.html         # Abstract template for detail views
│   │   │   ├── landing_page.html        # Abstract template for landing pages
│   │   │   ├── content_page.html        # Abstract template for static content
│   │   │   ├── teams_overview.html      # Main dashboard (extends landing_page)
│   │   │   ├── team_dashboard.html      # Team-specific view (extends detail_page)
│   │   │   ├── person_dashboard.html    # Individual view (extends detail_page)
│   │   │   ├── comparison.html          # Cross-team comparison (extends detail_page)
│   │   │   ├── team_members_comparison.html  # Member comparison (extends detail_page)
│   │   │   └── documentation.html       # Help page (extends content_page)
│   │   └── static/
│   │       ├── css/
│   │       │   ├── main.css             # Core styles with theme variables
│   │       │   └── hamburger.css        # Hamburger menu styles
│   │       └── js/
│   │           ├── theme-toggle.js      # Dark/light mode switcher
│   │           └── charts.js            # Shared chart utilities and CHART_COLORS
│   ├── config.py                        # Configuration loader
│   └── __init__.py
├── tests/                               # Test suite (417 tests, 51.25% coverage)
│   ├── unit/
│   │   ├── test_jira_metrics.py         # 26 tests for Jira metrics processing
│   │   ├── test_dora_metrics.py         # 39 tests for DORA metrics & trends
│   │   ├── test_dora_trends.py          # 13 tests for DORA trend calculations
│   │   ├── test_performance_score.py    # 19 tests for performance scoring
│   │   ├── test_config.py               # 27 tests for configuration validation
│   │   └── test_metrics_calculator.py   # 30+ tests for metrics calculations
│   ├── collectors/
│   │   └── test_jira_collector.py       # 27 tests for Jira collector
│   ├── integration/                     # Integration tests (currently disabled)
│   │   ├── test_parallel_collection.py.disabled
│   │   ├── test_dora_lead_time_mapping.py.disabled
│   │   ├── test_error_recovery.py.disabled
│   │   └── test_collection_workflow.py.disabled
│   ├── fixtures/
│   │   └── sample_data.py               # Mock data generators for testing
│   ├── conftest.py                      # Shared pytest fixtures
│   └── pytest.ini                       # Pytest configuration
├── config/
│   ├── config.yaml                      # Main configuration (gitignored)
│   └── config.example.yaml              # Configuration template
├── data/
│   └── metrics_cache.pkl                # Cached metrics data (gitignored)
├── scripts/
│   ├── start_dashboard.sh               # Dashboard wrapper for launchd
│   └── collect_data.sh                  # Collection wrapper for launchd
├── collect_data.py                      # Main data collection script
├── list_jira_filters.py                 # Utility to discover Jira filter IDs
├── requirements.txt                     # Production dependencies
├── requirements-dev.txt                 # Testing dependencies (pytest, coverage, mocking)
├── README.md                            # This file
├── CLAUDE.md                            # AI assistant guidance
├── RELEASE_NOTES.md                     # Release history and changelog
└── docs/                                # Documentation
    ├── QUICK_START.md                   # Quick setup guide
    ├── IMPLEMENTATION_GUIDE.md          # Detailed implementation notes
    ├── LEAD_TIME_FIX_RESULTS.md         # Lead time fix analysis
    └── *.md                             # Other documentation
```

## Setup

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure GitHub and Jira Access

Copy the example configuration:
```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` and add:

**GitHub Configuration:**
```yaml
github:
  token: "your_github_personal_access_token"
  organization: "your-org-name"
  days_back: 90
```

**Jira Configuration** (for self-hosted Jira):
```yaml
jira:
  server: "https://jira.yourcompany.com"
  username: "your_jira_username"  # NOT email - use username
  api_token: "your_bearer_token"  # Bearer token for authentication
  project_keys:
    - "PROJECT1"
    - "PROJECT2"
```

**Team Configuration:**
```yaml
teams:
  - name: "Backend"
    display_name: "Backend Team"
    github:
      team_slug: "backend-team"
      members:
        - "github-user1"
        - "github-user2"
    jira:
      members:
        - "jira-user1"
        - "jira-user2"
      filters:
        backlog_in_progress: 12345
        bugs: 12346
        completed_12weeks: 12347
        incidents: 12348  # For DORA CFR/MTTR
        # ... more filter IDs
```

### 3. Validate Configuration

Before running data collection, validate your configuration:

```bash
python validate_config.py
```

This checks for:
- Valid YAML syntax
- Required fields present (GitHub token, Jira credentials, teams)
- Correct data types and formats
- No duplicate team names
- Performance weights sum to 100%

**Usage:**
```bash
# Validate default config
python validate_config.py

# Validate specific file
python validate_config.py --config path/to/config.yaml
```

### 4. Find Your Jira Filter IDs

Run the utility script to discover your Jira filter IDs:
```bash
python list_jira_filters.py
```

Add the relevant filter IDs to your team configuration.

### 4. Collect Data

Run the data collection script (takes 15-30 minutes):
```bash
source venv/bin/activate
python collect_data.py --date-range 90d  # Default: last 90 days
```

You can collect data for different time ranges:
```bash
python collect_data.py --date-range 30d     # Last 30 days
python collect_data.py --date-range 180d    # Last 6 months
python collect_data.py --date-range Q1-2025 # Q1 2025
python collect_data.py --date-range 2024    # Full year 2024
```

Each collection creates a separate cache file (e.g., `data/metrics_cache_90d.pkl`).

### 5. Start the Dashboard

```bash
python -m src.dashboard.app
```

Access the dashboard at:
- Main: `http://localhost:5001`
- Team view: `http://localhost:5001/team/<team_name>`
- Person view: `http://localhost:5001/person/<username>`
- Comparison: `http://localhost:5001/comparison`

### 6. Exporting Metrics Data

Export metrics data to CSV or JSON format from any dashboard page:

**Available on:**
- Team Dashboard: `/team/<team_name>`
- Person Dashboard: `/person/<username>`
- Team Comparison: `/comparison`
- Team Member Comparison: `/team/<team_name>/compare`

**Formats:**
- **CSV**: Flattened data structure, Excel-compatible, ideal for spreadsheets
- **JSON**: Nested structure with full metadata, ideal for programmatic access

**Usage:**
1. Navigate to any dashboard page
2. Click "📊 Export CSV" or "📋 Export JSON" at the top of the page
3. File downloads automatically with a descriptive name

**Export Filenames:**

All exported files include the current date in the filename:
- `team_native_metrics_2026-01-14.csv`
- `person_jdoe_metrics_2026-01-14.json`

This makes it easy to maintain historical snapshots and organize your exports chronologically.

**Export Data Includes:**
- All metrics visible on the page
- Date range metadata
- Export timestamp
- Team/person identifiers

### 7. Verify Installation (Optional)

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run test suite (417 tests: 397 passed, 20 integration tests currently disabled)
pytest

# Check coverage (51.25% overall, with 94% jira_metrics, 75% dora_metrics)
pytest --cov
```

## Date Range Selection

### In the Dashboard

The dashboard includes a date range selector in the hamburger menu (☰) with preset options:
- Last 30 days
- Last 60 days
- Last 90 days (default)
- Last 180 days
- Last 365 days
- Quarterly views (Q1-2025, Q2-2024, etc.)
- Yearly views (2024, 2025, etc.)

The selected range persists as you navigate between pages via the `?range=` URL parameter.

### During Data Collection

Use the `--date-range` argument to collect data for specific time periods:

```bash
# Last 30 days
python collect_data.py --date-range 30d

# Last 90 days (default)
python collect_data.py --date-range 90d

# Specific quarter
python collect_data.py --date-range Q1-2025

# Specific year
python collect_data.py --date-range 2024

# Custom date range
python collect_data.py --date-range 2024-01-01:2024-12-31
```

Each collection creates a separate cache file (e.g., `metrics_cache_30d.pkl`, `metrics_cache_90d.pkl`) allowing you to switch between date ranges in the dashboard without re-collecting data.

## Configuration

### GitHub Token Permissions

Create a GitHub Personal Access Token with these permissions:
- `repo` - Access to repositories (required for PRs, commits)
- `read:org` - Read organization data (required for team membership)

### Jira Bearer Token

For self-hosted Jira instances:
1. Generate a personal access token in Jira
2. Use **Bearer token authentication** (not username/password)
3. Configure with `username` field (not `email`)
4. SSL verification is automatically disabled for self-signed certificates

Test your Jira token:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" -k https://jira.yourcompany.com/rest/api/2/serverInfo
```

### Team Configuration

Each team requires:
- **name**: Internal team identifier (used in URLs)
- **display_name**: Human-readable team name
- **github.team_slug**: GitHub team slug
- **github.members**: List of GitHub usernames
- **jira.members**: List of Jira usernames (may differ from GitHub)
- **jira.filters**: Dictionary of filter IDs for team-specific metrics

**Filter Types:**
- `backlog_in_progress`: Items in backlog or in progress
- `bugs`: Current bug count
- `bugs_created`: Bugs created in time period
- `bugs_resolved`: Bugs resolved in time period
- `completed_12weeks`: Items completed in last 12 weeks
- `flagged_blocked`: Items with impediments
- `incidents`: Production incidents for DORA CFR/MTTR (required for incident tracking)
- `recently_released`: Recently deployed items
- `scope`: Team backlog size
- `wip`: Work in progress

**Incident Tracking Setup** (for DORA CFR & MTTR):

To enable Change Failure Rate and MTTR metrics, create a Jira filter for production incidents:

```jql
project IN (YOUR_PROJECTS)
AND (
    issuetype = Incident
    OR (priority IN (Blocker, Critical, High) AND labels IN (production, p1, sev1))
)
AND (created >= -90d OR resolved >= -90d)
ORDER BY created DESC
```

Add the filter ID to your team configuration:
```yaml
jira:
  filters:
    incidents: 12354  # Your incident filter ID
```

The system will automatically correlate incidents to deployments for accurate failure tracking.

## Data Refresh

Three ways to refresh metrics:

### 1. Offline Collection (Recommended)
```bash
python collect_data.py
```
- Full team and person-level metrics
- Takes 15-30 minutes
- Uses efficient GraphQL API

### 2. Dashboard Refresh Button
- Click "Refresh Data" in the web UI
- Team-level metrics only
- Takes 5-10 minutes
- Uses GraphQL API

### 3. Auto-Refresh
- Automatic after 60 minutes (configurable)
- Same as Dashboard Refresh Button

## Logging

Collection runs automatically write structured logs to the `logs/` directory for monitoring and debugging:

- **Location**: `logs/` directory
- **Format**: JSON (machine-parseable for analysis)
- **Rotation**: Automatic at 10MB with gzip compression
- **Retention**: 10 backup files (~100MB total disk usage)

### Verbosity Control

```bash
# Normal mode (INFO level)
python collect_data.py --date-range 90d

# Verbose mode (DEBUG level)
python collect_data.py --date-range 90d -v

# Quiet mode (warnings and errors only)
python collect_data.py --date-range 90d -q
```

### Log Analysis Examples

```bash
# View recent errors
tail -f logs/team_metrics_error.log | jq .

# Track collection progress
tail -f logs/team_metrics.log | jq -r 'select(.progress) | "\(.progress.current)/\(.progress.total) - \(.progress.item)"'

# Count error types
jq -r 'select(.level=="ERROR") | .logger' logs/team_metrics.log | sort | uniq -c
```

See [CLAUDE.md - Logging](CLAUDE.md#logging) for complete documentation including:
- Interactive vs background mode output
- Configuration options
- Advanced log analysis commands
- Architecture details

## Performance

**Optimized Data Collection** (5-6x total speedup):

The dashboard implements multiple performance optimizations for efficient data collection:

- **Team Parallelization**: Collects up to 3 teams concurrently
- **Repository Parallelization**: Collects up to 5 repositories per team concurrently
- **Person Parallelization**: Collects up to 8 person metrics concurrently
- **Filter Parallelization**: Collects up to 4 Jira filters per team concurrently
- **Connection Pooling**: Reuses HTTP connections to reduce TCP handshake overhead (automatic, 5-10% speedup)
- **Repository Caching**: Caches team repository lists for 24 hours to eliminate redundant queries (automatic, 5-15s saved)
- **GraphQL Query Batching**: Combines PRs and Releases queries into single requests (automatic, 20-40% speedup, 50% fewer API calls)

**Results**:
- Single collection: ~1.5 minutes (down from ~5 minutes)
- 12-range collection: ~4 hours (down from ~18 hours)
- Overall speedup: 5-6x from combined optimizations

**Configuration**:

Parallel collection is enabled by default. Adjust worker counts in `config/config.yaml`:

```yaml
parallel_collection:
  enabled: true           # Set to false to disable
  person_workers: 8       # Concurrent person collections
  team_workers: 3         # Concurrent team collections
  repo_workers: 5         # Concurrent repo collections per team
  filter_workers: 4       # Concurrent Jira filter collections per team
```

**Note**: GitHub secondary rate limits (403 errors) may occur with aggressive parallelization. The system handles these gracefully with retry logic. Reduce `repo_workers` to 3-4 or `filter_workers` to 2-3 if errors are frequent.

## GraphQL API Benefits

The system uses GitHub's GraphQL API v4 for data collection:

**Advantages:**
- **Separate rate limit**: 5000 points/hour (independent from REST's 5000 requests/hour)
- **Efficient queries**: Fetch PRs, reviews, and commits in single requests
- **Fewer API calls**: 50-70% reduction compared to REST API
- **Better performance**: Faster data collection with pagination built-in

**Implementation:**
- `GitHubGraphQLCollector` in `src/collectors/github_graphql_collector.py`
- Used by both `collect_data.py` and dashboard refresh

## Architecture Highlights

### Multi-Team Support
- Each team has separate GitHub and Jira member lists
- Team-specific Jira filters for custom metrics
- Cross-team comparison capabilities

### Caching Strategy
- Offline collection saves to `data/metrics_cache.pkl`
- Dashboard loads instantly from cache
- Configurable cache duration (default: 60 minutes)
- Refresh on-demand via button or auto-refresh

### Dashboard Views
1. **Main Dashboard** - Overview of all teams with 2-column grid layout
2. **Team Dashboard** - Team-specific metrics with Jira filters and WIP charts
3. **Person Dashboard** - Individual contributor metrics with:
   - Interactive trend charts showing activity over time
   - Flexible date ranges selectable via dashboard menu
   - Weekly aggregated trends for visualization
4. **Team Comparison Dashboard** - Side-by-side team comparison with centered bar charts, DORA metrics with performance level badges, and performance scores
5. **Team Member Comparison** - Within-team rankings with performance scores and leaderboard (🥇🥈🥉)

### Performance Scoring System

The dashboard includes a **composite performance scoring system** used to rank teams and individuals across multiple metrics.

**How It Works:**
- Scores range from **0-100** (higher is better)
- Each metric is normalized using min-max scaling across all teams/members
- Normalized scores are weighted and summed to create the composite score
- Team size normalization ensures fair per-capita comparison

**Default Metric Weights:**
| Metric | Weight | Description |
|--------|--------|-------------|
| PRs Created | 20% | Pull requests authored |
| Reviews Given | 20% | Code reviews provided to others |
| Commits | 15% | Total commits authored |
| Cycle Time | 15% | PR merge time (lower is better, inverted) |
| Jira Completed | 20% | Jira issues resolved |
| Merge Rate | 10% | Percentage of PRs successfully merged |

**Key Features:**
- **Cycle Time Inversion**: Lower cycle times score higher (faster PR merges are better)
- **Team Size Normalization**: Divides volume metrics by team size for fair comparison
- **Consistent Algorithm**: Same scoring logic for both team and person comparisons
- **Visual Rankings**: Teams/members displayed with scores, ranks, and badges (🥇🥈🥉)

**Where You See It:**
- Team Comparison page: Overall Performance card with scores per team
- Team Member Comparison: Top Performers leaderboard with rankings

**Implementation:** See `src/models/performance_scoring.py:PerformanceScorer` for the scoring algorithm. The MetricsCalculator delegates to this static utility class for all performance score calculations.

### UI Features
- **Dark Mode**: Toggle between light and dark themes across all pages
- **Consistent Styling**: CSS variables ensure uniform appearance
- **Optimized Charts**: Plotly charts with theme-aware colors and proper sizing
- **Responsive Layout**: Charts and grids adapt to screen size
- **Direct Links**: Quick access to GitHub PRs, commits, and Jira filters
- ↑ **Back to Top Button** - Floating button for quick navigation on long pages
- 📅 **Data Freshness Indicator** - "Data from X hours ago" badges show cache age
- ⏳ **Loading States** - Visual feedback during data reload operations

## Analysis Tools

Verify and analyze collected metrics:

```bash
# Quick verification (checks for errors, counts releases, verifies issue mapping)
./tools/verify_collection.sh

# Detailed analysis (shows releases, issue counts, DORA metrics)
python tools/analyze_releases.py

# Specific release details
python tools/analyze_releases.py "Team Name" "Release Name"
```

See `ANALYSIS_COMMANDS.md` for complete reference with Python snippets and verification checklist.

## Troubleshooting

### GitHub Rate Limits
If you hit rate limits with GraphQL:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.github.com/rate_limit
```

GraphQL has a separate limit, so this is rare.

### Jira Authentication Issues
- Ensure you're using a **Bearer token** (not password)
- Use `username` field in config (not `email`)
- Test with: `curl -H "Authorization: Bearer YOUR_TOKEN" -k https://jira.yourcompany.com/rest/api/2/serverInfo`

### Jira Query Performance
The system automatically filters out noise from administrative updates:
- Queries use `statusCategory != Done` filter on `updated >= -90d` to ignore closed tickets
- Prevents bulk operations (mass label updates) from polluting metrics with thousands of old tickets
- Maintains 100% accuracy while improving performance
- See Documentation page (📚 in hamburger menu) for details

### No Data Showing
- Check team members are listed correctly in config
- Verify Jira filter IDs are correct (run `list_jira_filters.py`)
- Ensure `days_back` covers active development period

## Automation Setup (macOS)

### Persistent Dashboard Service

The dashboard can run continuously in the background using macOS launchd:

```bash
# Load the dashboard service (auto-starts on boot)
launchctl load ~/Library/LaunchAgents/com.team-metrics.dashboard.plist

# Verify it's running
launchctl list | grep team-metrics
curl http://localhost:5001
```

The service will:
- Start automatically on system boot
- Restart automatically if it crashes
- Run independently of terminal sessions

### Scheduled Data Collection

Daily data collection at 10:00 AM:

```bash
# Load the collection scheduler
launchctl load ~/Library/LaunchAgents/com.team-metrics.collect.plist

# Manually trigger collection (optional)
launchctl start com.team-metrics.collect
```

### Management Commands

**Stop/Start Dashboard**:
```bash
launchctl stop com.team-metrics.dashboard
launchctl start com.team-metrics.dashboard
```

**Reload After Changes**:
```bash
launchctl unload ~/Library/LaunchAgents/com.team-metrics.dashboard.plist
launchctl load ~/Library/LaunchAgents/com.team-metrics.dashboard.plist
```

**View Logs**:
```bash
tail -f logs/dashboard.log
tail -f logs/collect_data.log
```

**Disable Automation**:
```bash
launchctl unload ~/Library/LaunchAgents/com.team-metrics.collect.plist
launchctl unload ~/Library/LaunchAgents/com.team-metrics.dashboard.plist
```

## Quick Start

See [QUICK_START.md](docs/QUICK_START.md) for a detailed quick start guide.

See [IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md) for technical implementation details.

## Code Quality

The project uses modern Python code quality tools:

- **Black** (formatter) - Consistent code style (120 char lines)
- **isort** (import sorter) - Organized imports
- **Pylint** (linter) - Code quality checks (score: 9.28/10)
- **Mypy** (type checker) - Static type checking

### Quick Commands

```bash
make format      # Auto-format code
make lint        # Run linter
make typecheck   # Run type checker
make test        # Run tests
make check       # Run all checks
```

See [docs/CODE_QUALITY.md](docs/CODE_QUALITY.md) for detailed documentation.

## Next Steps

- **Historical tracking**: Store metrics over time for trend analysis
- **More visualizations**: Add trend lines and time series graphs
- **Alerts**: Email notifications for metric thresholds
- **Production deployment**: Use gunicorn/waitress for production Flask server
