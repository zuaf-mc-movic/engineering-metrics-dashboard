# Team Metrics Dashboard - Quick Start

## How to Use

### 1. Collect Data (Run this first, takes 15-30 minutes)
```bash
source venv/bin/activate
python collect_data.py
```

This collects GitHub and Jira data using **GraphQL API** and saves it to `data/metrics_cache.pkl`.

**What it collects:**
- Team-level metrics (GitHub PRs, reviews, commits + Jira filter data)
- Person-level metrics (individual contributor data for the current year)
- Team comparison data

### 2. Start Dashboard
```bash
source venv/bin/activate
python -m src.dashboard.app
```

Then open: **http://localhost:5000**

The dashboard loads instantly from the cached data!

---

## Configuration Files

### Main Config: `config/config.yaml`

**Current Setup - Team-Based Collection:**

The system uses a **team-based configuration** structure. Each team has:
- GitHub team slug and members
- Jira members and filter IDs
- Separate metrics collection per team

**Example Configuration:**
```yaml
github:
  token: "your_github_token"
  organization: "goto-itsg"
  days_back: 90

jira:
  server: "https://jira.ops.expertcity.com"
  username: "zmaros"              # NOT email - use username
  api_token: "your_bearer_token"  # Bearer token for authentication
  project_keys:
    - "RSC"
    - "RW"

teams:
  - name: "Native"
    display_name: "Native Team"
    github:
      team_slug: "itsg-rescue-native"
      members:
        - "daniella-b"
        - "bigfoot-goto"
        - "lcsanky"
        # ... more members
    jira:
      members:
        - "dbarsony"
        - "aborsanyihortobagyi"
        # ... more members
      filters:
        backlog_in_progress: 81014
        bugs: 81015
        bugs_created: 81012
        bugs_resolved: 81013
        completed_12weeks: 80911
        flagged_blocked: 81011
        recently_released: 82112
        scope: 80910
        wip: 81010
```

**Key Points:**
- **GraphQL API** - Uses efficient GraphQL API for GitHub (not REST)
- **Bearer Token** - Jira uses Bearer token authentication (not basic auth)
- **Team Structure** - Separate member lists for GitHub and Jira per team
- **Jira Filters** - Team-specific filter IDs for custom Jira metrics

**To find your Jira filter IDs:**
```bash
python list_jira_filters.py
```

---

## What You'll See

### Dashboard Views

#### 1. **Main Dashboard** (http://localhost:5000)
- Overview of all teams
- Quick comparison metrics

#### 2. **Team Dashboard** (http://localhost:5000/team/<team_name>)
- Team-specific GitHub metrics (PRs, reviews, commits)
- Jira filter results (throughput, WIP, flagged items, bugs)
- Per-member activity breakdown
- Team cycle times and merge rates

#### 3. **Person Dashboard** (http://localhost:5000/person/<username>)
- Individual contributor metrics for the current year
- PRs created, merged, merge rate
- Reviews given, PRs reviewed
- Commits and lines changed
- Jira issues completed

#### 4. **Comparison Dashboard** (http://localhost:5000/comparison)
- Side-by-side team metrics
- Team performance comparison
- Throughput and WIP comparison

### GitHub Metrics (via GraphQL API)
- Pull Requests (total, merged, cycle time, merge rate)
- Code Reviews (total reviews, top reviewers, cross-team reviews)
- Contributors (commits, lines changed, top contributors)
- PR size distribution

### Jira Metrics (via Filters)
- **Throughput** - Items completed per week from `completed_12weeks` filter
- **WIP Statistics** - Age distribution of work in progress
- **Flagged/Blocked** - Issues with impediments
- **Bug Tracking** - Created vs resolved bugs
- **Scope** - Team backlog size
- **Recently Released** - Deployed work

---

## Troubleshooting

### "No data showing"
- Check team configuration in `config/config.yaml`
- Ensure team members are listed correctly in both `github.members` and `jira.members`
- Verify Jira filter IDs are correct (run `list_jira_filters.py`)
- Check that `days_back` covers active development period

### "GitHub API rate limit exceeded"
The system uses **GraphQL API** which has a separate rate limit (5000 points/hour) from REST API (5000 requests/hour).

Check your rate limit:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.github.com/rate_limit
```

**Note:** Both `collect_data.py` and the dashboard refresh button now use GraphQL, so rate limits are much less likely.

### "Jira authentication failed (HTTP 401)"
- Ensure you're using a **Bearer token** (not username/password)
- Config should use `username` field (not `email`)
- For self-hosted Jira, SSL verification is disabled (`verify_ssl=False`)
- Test your token:
  ```bash
  curl -H "Authorization: Bearer YOUR_TOKEN" -k https://jira.ops.expertcity.com/rest/api/2/serverInfo
  ```

### "Collection taking too long"
- Reduce `days_back` from 90 to 30 or 7
- Limit number of repositories by adjusting team slugs
- Person-level collection can take ~1 minute per team member

### "Person dashboard shows no data"
- Person-level metrics collect data for the **current year** only
- Check that the user has activity in the current year
- Verify username exists in team `github.members` list

---

## Daily Workflow

1. **Morning:** Run `collect_data.py` (takes 15-30 min, run in background)
   ```bash
   source venv/bin/activate
   python collect_data.py &
   ```

2. **Start dashboard:**
   ```bash
   python -m src.dashboard.app
   ```

3. **View metrics all day:** Dashboard loads instantly from cache

4. **Refresh data:**
   - **Option A:** Re-run `collect_data.py` (full refresh)
   - **Option B:** Click "Refresh Data" button in dashboard (quick refresh using GraphQL)

5. **Cache Duration:** Data is considered fresh for 60 minutes (configurable in `config.yaml`)

---

## Data Refresh

The system supports **three ways** to refresh data:

### 1. Offline Collection (Recommended)
```bash
python collect_data.py
```
- Full team and person-level metrics
- Uses GraphQL API (efficient)
- Saves to `data/metrics_cache.pkl`
- Takes 15-30 minutes

### 2. Dashboard Refresh Button
- Click "Refresh Data" in the web UI
- Uses GraphQL API (efficient)
- Team-level metrics only (no person-level)
- Takes 5-10 minutes
- Runs in the web request (blocking)

### 3. Auto-Refresh (Cache Expiration)
- Automatic after `cache_duration_minutes` expires (default: 60)
- Triggered when accessing `/api/metrics` endpoint
- Uses GraphQL API
- Same as Dashboard Refresh Button

---

## Files You Can Edit

### Configuration
- `config/config.yaml` - Main configuration (teams, tokens, filter IDs)
- `config/config.example.yaml` - Template for reference

### Core Scripts
- `collect_data.py` - Data collection script (offline, full collection)
- `list_jira_filters.py` - Utility to discover Jira filter IDs

### Dashboard
- `src/dashboard/app.py` - Dashboard logic and routes
- `src/dashboard/templates/*.html` - Dashboard UI templates
  - `dashboard.html` - Main overview
  - `team_dashboard.html` - Team view
  - `person_dashboard.html` - Person view
  - `comparison.html` - Team comparison

### Collectors
- `src/collectors/github_graphql_collector.py` - GitHub GraphQL API collector
- `src/collectors/jira_collector.py` - Jira REST API collector
- `src/models/metrics.py` - Metrics calculation logic

---

## Architecture Highlights

### GraphQL API (Efficient)
- **Collector:** `GitHubGraphQLCollector` in `src/collectors/github_graphql_collector.py`
- **Advantages:**
  - 50-70% fewer API calls than REST
  - Separate rate limit (5000 points/hour)
  - Fetch PRs, reviews, and commits in single queries
  - Pagination built-in

### Jira Bearer Token Auth
- **Authentication:** Bearer token in Authorization header
- **Endpoint:** Self-hosted Jira at `https://jira.ops.expertcity.com`
- **SSL:** Verification disabled for self-signed certificates
- **Config:** Uses `username` field (not `email`)

### Team-Based Collection
- Each team has separate GitHub and Jira member lists
- Jira filters provide custom team metrics
- Team-level and person-level metrics
- Cross-team comparison support

---

## Development

### Install Development Dependencies (Optional, for Testing)

```bash
pip install -r requirements-dev.txt
```

## Verification (Optional)

Run the test suite to verify everything is working:

```bash
# Run all tests
pytest

# Expected output:
# ============================= test session starts ==============================
# collected 111 items
#
# tests/unit/test_time_periods.py ................              [ 14%]
# tests/unit/test_activity_thresholds.py ...........            [ 24%]
# tests/unit/test_collect_data.py ..............                [ 36%]
# tests/unit/test_metrics_calculator.py ........................ [ 58%]
# tests/collectors/test_github_collector.py ..........          [ 67%]
# tests/collectors/test_jira_collector.py ............          [ 78%]
#
# ============================== 111 passed in 2.35s ==============================

# Check test coverage
pytest --cov

# Expected coverage: 83%+ overall
```

**All tests passing indicates:**
- Date utilities working correctly
- Metrics calculations accurate
- API response parsing functional
- Configuration mapping working

---

## Next Steps / Improvements

1. **Scheduled collection** - Set up cron job to run `collect_data.py` daily at 6am
   ```bash
   0 6 * * * cd /path/to/team_metrics && source venv/bin/activate && python collect_data.py
   ```

2. **Background refresh** - Make dashboard refresh non-blocking (use Celery or threading)

3. **More visualizations** - Add trend lines, time series graphs, burn-down charts

4. **Export data** - Add CSV/JSON export functionality for reports

5. **Alerts** - Email notifications when cycle times exceed thresholds

6. **Historical tracking** - Store metrics over time for trend analysis

7. **Person dashboard navigation** - Add links between person and team dashboards
