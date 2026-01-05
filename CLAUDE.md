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
# Collect metrics (takes 15-30 minutes, caches to data/metrics_cache.pkl)
python collect_data.py

# Collect for specific time period
python collect_data.py --period Q1-2025
python collect_data.py --period 90d
python collect_data.py --start-date 2025-01-01 --end-date 2025-03-31

# List available Jira filters (utility to find filter IDs)
python list_jira_filters.py
```

### Running the Dashboard
```bash
# Start Flask web server
python -m src.dashboard.app

# Access at http://localhost:5000
# Available routes:
#   /                                 - Main overview
#   /team/<team_name>                 - Team-specific dashboard
#   /team/<team_name>/compare         - Team member comparison
#   /person/<username>                - Individual contributor dashboard
#   /comparison                       - Cross-team comparison
```

## Architecture

### Data Flow

1. **Collection Phase** (`collect_data.py`):
   - `GitHubGraphQLCollector` → Fetches PRs, reviews, commits from GitHub GraphQL API
   - `JiraCollector` → Fetches team filter results from Jira REST API
   - `MetricsCalculator` → Processes raw data into metrics
   - Cache saved to `data/metrics_cache.pkl` (pickle format)

2. **Dashboard Phase** (`src/dashboard/app.py`):
   - Flask app loads cached metrics on startup
   - Renders templates with pre-calculated metrics
   - Optional: Refresh button re-runs collection using GraphQL API

### Key Components

**Collectors** (`src/collectors/`):
- `github_graphql_collector.py` - **Primary collector**, uses GraphQL API v4 for efficiency
- `github_collector.py` - Legacy REST API collector (kept for reference)
- `jira_collector.py` - Jira REST API with Bearer token authentication

**Models** (`src/models/`):
- `metrics.py` - `MetricsCalculator` class processes raw data into metrics
  - `calculate_team_metrics()` - Team-level aggregations with Jira filters
  - `calculate_person_metrics()` - Individual contributor metrics (365-day rolling window)
  - `calculate_team_comparison()` - Cross-team comparison data

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
  - `comparison.html` - Side-by-side team comparison
- `static/css/main.css` - Theme CSS with dark mode variables
- `static/js/theme-toggle.js` - Dark/light mode toggle

### Configuration Structure

`config/config.yaml` has this structure:
```yaml
github:
  token: "ghp_..."
  organization: "your-org"
  days_back: 90

jira:
  server: "https://jira.yourcompany.com"
  username: "username"  # NOT email
  api_token: "bearer_token"

teams:
  - name: "Backend"
    display_name: "Backend Team"
    github:
      team_slug: "backend-team"
      members: ["user1", "user2"]
    jira:
      members: ["jira.user1", "jira.user2"]
      filters:
        wip: 12345
        completed_12weeks: 12346
        bugs: 12347
        # ... more filter IDs
```

### GitHub GraphQL vs REST

**Why GraphQL is used**:
- Separate rate limit (5000 points/hour vs REST's 5000 requests/hour)
- Single query fetches PRs + reviews + commits (vs 3+ REST calls)
- Pagination built-in, no need for multiple page requests
- 50-70% fewer API calls = faster collection

**GraphQL Query Structure** (see `github_graphql_collector.py`):
- `_fetch_prs_for_user()` - PRs with nested review data
- `_fetch_commits_for_user()` - Commit history with stats
- Pagination handled automatically with cursors

### Metrics Time Windows

- **Team metrics**: Configurable via `days_back` (default: 90 days) or period flags
- **Person metrics**: Fixed 365-day rolling window for consistent comparison
- **Jira metrics**: Team-specific filters define time ranges

## UI Architecture

**Theme System**:
- CSS variables in `main.css` for light/dark modes
- `data-theme` attribute on `<html>` element controls theme
- `theme-toggle.js` handles switching and localStorage persistence

**Chart Rendering**:
- Plotly.js for interactive charts
- Theme-aware colors injected at render time
- Charts use fixed dimensions for consistency (e.g., 450px width in comparison view)

**Key UI Patterns**:
- Cards use `var(--bg-secondary)` for theme-aware backgrounds
- Charts detect theme: `document.documentElement.getAttribute('data-theme')`
- Jira filter links constructed from team config + server URL

## Important Implementation Details

### Jira Integration
- Uses **Bearer token** authentication (not username/password)
- SSL verification disabled (`verify_ssl=False`) for self-signed certificates
- Filter IDs are specific to each Jira instance - use `list_jira_filters.py` to discover
- Filters define team metrics (WIP, bugs, throughput, etc.)

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

**Changing time periods**:
- Team metrics: Modify `config.yaml` `days_back` or use `--period` flag
- Person metrics: Hardcoded to 365 days in `collect_data.py` line 246
- To change person window: Edit `days_back=365` in the person collection loop
