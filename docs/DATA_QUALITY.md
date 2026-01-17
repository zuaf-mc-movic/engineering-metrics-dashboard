# Data Quality Summary

## Executive Summary

The Team Metrics Dashboard collects engineering metrics from two primary sources:
- **GitHub GraphQL API v4**: Pull requests, code reviews, commits, and releases
- **Jira REST API v2**: Issues, fix versions (deployments), incidents, and team filters

Data is collected daily at 10:00 AM via automated scheduling (launchd on macOS), processed into DORA metrics (Deployment Frequency, Lead Time, Change Failure Rate, MTTR), and cached for dashboard visualization.

**Collection Efficiency**: GraphQL batching reduces API calls by 50-70% compared to REST. Parallel collection (3 teams, 5 repos, 8 persons concurrently) provides 5-6x speedup.

**Data Quality Measures**: Three-tier release filtering, anti-noise JQL for Jira, deduplication, date range validation, and post-collection validation checks ensure accurate metrics.

## GitHub Data Collection

**Source**: `src/collectors/github_graphql_collector.py` (1,220 lines)

### What We Collect

#### Pull Requests
**Fields Collected**:
- Metadata: `number`, `title`, `author`, `state`, `merged`
- Timestamps: `created_at`, `merged_at`, `closed_at`
- Metrics: `additions`, `deletions`, `changed_files`, `comments`
- Calculated: `cycle_time_hours`, `time_to_first_review_hours`

**Used For**:
- PR count, merge rate, cycle time metrics
- Lead time for changes (DORA)
- Contributor activity analysis
- Team velocity tracking

#### Code Reviews
**Fields Collected**:
- `pr_number`, `reviewer`, `submitted_at`
- `state` (APPROVED, CHANGES_REQUESTED)
- `pr_author`

**Used For**:
- Review participation metrics
- Collaboration patterns
- Code quality indicators

#### Commits
**Fields Collected**:
- `sha`, `author`, `date`
- `additions`, `deletions`
- `pr_number` (associated PR)

**Used For**:
- Individual contributor metrics
- Commit frequency analysis
- Code churn tracking

#### Releases (Legacy GitHub)
**Fields Collected**:
- `tag_name`, `published_at`, `created_at`
- `environment` (production/staging)
- `commit_sha`, `commit_date`

**Used For**:
- Deployment frequency (fallback if Jira unavailable)
- Release tracking

**Note**: Jira Fix Versions are the primary source for DORA deployment tracking.

### How We Collect

#### API Technology
- **GraphQL API v4**: Primary collection method
- **Endpoint**: `https://api.github.com/graphql`
- **Authentication**: Bearer token
- **Rate Limit**: 5,000 points/hour (separate from REST API's 5,000 requests/hour)
- **Advantage**: 50-70% fewer API calls vs REST

#### Query Batching Strategy
Single query fetches multiple data types simultaneously:
```graphql
query {
  repository(owner: "org", name: "repo") {
    pullRequests(first: 50) { ... }
    releases(first: 20) { ... }
  }
}
```

**Benefits**:
- Combines PRs + Releases into one request
- Each PR includes nested reviews and commits
- Reduces API calls by ~50%
- Lower latency (fewer round trips)

#### Pagination & Early Termination
- **Method**: Cursor-based pagination
- **Ordering**: `CREATED_AT DESC` (newest first)
- **Early Stop**: Pagination stops when data falls outside date range
- **Page Size**: 50 PRs per page, 20 releases per page
- **Safety Limit**: Max 20 pages per repository

#### Date Filtering
- **Since Date**: Calculated from `--date-range` parameter (default: 90 days)
- **End Date**: Current time (or specified end date for historical analysis)
- **Filtering Logic**:
  - Server-side: None (GitHub GraphQL has limited filtering)
  - Client-side: After fetching, filter by `created_at >= since_date`
  - Early termination when `created_at < since_date` for entire page

#### Team Member Filtering
- **Post-Collection**: Data filtered to configured team members
- **GitHub Usernames**: Defined in `config/config.yaml` per team
- **Filter Fields**: `author` (PRs/commits), `reviewer` (reviews)
- **Rationale**: Ensures metrics reflect only team activity

#### Parallelization
Configured in `config/config.yaml`:
```yaml
parallel_collection:
  enabled: true
  repo_workers: 3        # Repositories collected concurrently
  team_workers: 3        # Teams collected concurrently
  person_workers: 8      # Individual persons collected concurrently
```

**Implementation**:
- `ThreadPoolExecutor` for concurrent requests
- 200ms delay between repository submissions (prevents rate limiting)
- Connection pooling (HTTPAdapter with pool_size=10)

#### Rate Limiting & Retry Logic
**Primary Rate Limit (5000 points/hour)**:
- Monitored via response headers
- Not typically hit with current query patterns

**Secondary Rate Limit (403 errors)**:
- **Detection**: "secondary rate limit" in response message
- **Retry Strategy**: 3 attempts with exponential backoff (5s, 10s, 20s)
- **Prevents**: Overwhelming GitHub's abuse detection

**Transient Errors (502, 503, 504, 429)**:
- **Retry Strategy**: 3 attempts with exponential backoff (1s, 2s, 4s)
- **Timeout Handling**: 30s request timeout, retry on timeout

**Code Reference**: `src/collectors/github_graphql_collector.py:80-137`

#### Repository Caching
- **Purpose**: Avoid redundant team repository lookups
- **Duration**: 24 hours
- **Cache File**: `data/.repo_cache.json`
- **Speedup**: Saves 5-15 seconds per collection
- **Clear Command**: `python scripts/clear_repo_cache.py`

### Data Quality Measures

#### Deduplication
- **Commits**: Same SHA appearing in multiple PRs counted once
- **Method**: Track `seen_shas` set during collection

#### Date Range Validation
- **Boundary Checks**: All dates validated against `since_date` and `end_date`
- **Timezone Handling**: All timestamps converted to UTC
- **Consistency**: Same date range applied across all data types

#### Error Tracking
Collected per repository:
- `successful_repos`: Repositories with data
- `failed_repos`: Repositories with errors (connection, timeout, etc.)
- `partial_repos`: Repositories with incomplete data
- `error_details`: Full error messages and stack traces

**Post-Collection Reporting**: Shows success rate and problematic repositories

#### Team Member Verification
- **Username Validation**: Warns if configured usernames have no activity
- **Case Sensitivity**: GitHub usernames are case-sensitive
- **Not Found**: Empty results (not errors) if username doesn't exist

#### Connection Pooling
- **Purpose**: Reuse TCP connections, prevent exhaustion
- **Configuration**: `HTTPAdapter(pool_connections=10, pool_maxsize=10)`
- **Benefit**: 5-10% speedup, improved reliability

## Jira Data Collection

**Source**: `src/collectors/jira_collector.py` (1,028 lines)

### What We Collect

#### Issues (Team & Individual)
**Fields Collected**:
- Identity: `key`, `project`, `type`, `status`, `priority`
- Ownership: `assignee`, `reporter`, `created`, `updated`, `resolved`
- Planning: `story_points`, `fix_versions`, `labels`
- Changelog: Status transition history (for cycle time)

**Used For**:
- Throughput (completed issues per week)
- Work-in-progress (WIP) tracking
- Cycle time calculation
- Sprint metrics
- Bug tracking

#### Fix Versions (PRIMARY for DORA)
**Fields Collected**:
- `name`, `releaseDate`, `released` (boolean status)
- `related_issues` (list of issue keys included in release)

**Formats Supported**:
1. **Date Format**: "Live - 6/Oct/2025", "Beta - 15/Jan/2026"
2. **Underscore Format**: "RA_Web_2025_11_25"

**Used For**:
- **Deployment Frequency** (DORA): Count of production releases per week
- **Lead Time** (DORA): PR merge date → Release date via issue mapping
- Release planning and tracking

**Why Primary**: More reliable than GitHub Releases for actual deployments. GitHub releases may be created but not deployed.

#### Incidents (Production Issues)
**Fields Collected**:
- `key`, `created`, `resolved`, `priority`
- `related_deployment` (tag/version that caused issue)
- `labels` (e.g., "production", "customer-impacting")
- `resolution_time_hours` (calculated: resolved - created)

**Detection Criteria** (any of):
1. Issue type = "Incident"
2. High/Critical priority bugs
3. Labels containing "production"

**Used For**:
- **Change Failure Rate** (DORA): % of deployments causing incidents
- **MTTR** (DORA): Median time to resolve production incidents

#### Jira Filters (Team-Defined Queries)
**Types**:
- `wip`: Work in progress (not Done)
- `bugs`: Active bugs
- `bugs_created`: Bugs created in time period
- `bugs_resolved`: Bugs resolved in time period
- `completed_12weeks`: Throughput metric
- `scope`: Sprint/backlog scope tracking
- `flagged_blocked`: Blocked work items
- `recently_released`: Recent releases
- `incidents`: Production incidents (for DORA)

**Configuration**: Filter IDs defined per team in `config/config.yaml`

**Used For**: Team-specific metrics, custom dashboards

### How We Collect

#### API Technology
- **Jira REST API v2**: Standard Jira Cloud/Server API
- **Endpoint**: `{server}/rest/api/2/` (e.g., `https://jira.company.com/rest/api/2/`)
- **Authentication**: Bearer token (API token, not username/password)
- **SSL**: `verify_ssl=False` for self-signed certificates (configurable)
- **Timeout**: 120 seconds (configurable via `dashboard.jira_timeout_seconds`)

#### Anti-Noise JQL Filtering
**Problem**: Bulk administrative updates (e.g., mass label changes) pull in thousands of old closed tickets, inflating metrics.

**Solution**: Smart JQL constraints
```jql
assignee = "user" AND (
  created >= -90d OR
  resolved >= -90d OR
  (statusCategory != Done AND updated >= -90d)
)
```

**Rationale**:
- Captures new issues (`created >= -90d`)
- Captures resolved issues (`resolved >= -90d`)
- Captures active WIP (`statusCategory != Done AND updated >= -90d`)
- **Excludes**: Closed tickets updated by admin (e.g., label changes)

**Impact**: Prevents 1000s of irrelevant closed tickets from polluting metrics

**Code Reference**: `jira_collector.py:60`, `:195`

#### Three-Tier Release Filtering
Ensures only valid team deployments are counted for DORA metrics.

**Tier 1: Status Check**
- `released = True` (version marked as released in Jira)
- `releaseDate` in the past (not future/planned releases)

**Tier 2: Pattern Matching**
Supports two naming conventions:
```python
# Format 1: "Live - 6/Oct/2025", "Beta - 15/Jan/2026"
pattern = r"^(Live|Beta|Production)\s*-\s*\d{1,2}/[A-Za-z]{3}/\d{4}$"

# Format 2: "RA_Web_2025_11_25", "Mobile_2025_12_01"
pattern = r"^\w+_\d{4}_\d{2}_\d{2}$"
```

**Tier 3: Team Member Filtering**
- Only releases with issues assigned to/reported by team members
- Prevents counting organization-wide releases unrelated to team's work

**Why Three Tiers**: Without filtering, deployment metrics were inflated 2-3x. Typical realistic value: 0.5-2.0 deployments/week per team.

**Code Reference**: `jira_collector.py:649-758`

#### Parallelization
Configured in `config/config.yaml`:
```yaml
parallel_collection:
  filter_workers: 4      # Jira filters collected concurrently
```

**Implementation**: `ThreadPoolExecutor` for concurrent filter queries

**Benefits**: 4x speedup for teams with 10+ filters

#### Fallback Queries
When primary query times out or fails:
1. **Remove Changelog**: Skip status history (faster query)
2. **Shorter Window**: Reduce date range (e.g., 90d → 30d)
3. **Progressive Simplification**: Try simpler queries before giving up

**Code Reference**: `jira_collector.py:253-290`

### Data Quality Measures

#### Anti-Noise JQL
(See "Anti-Noise JQL Filtering" above)

#### Release Pattern Validation
Only accepted formats counted. Prevents:
- Draft versions (e.g., "v1.2.3-SNAPSHOT")
- Planning versions (e.g., "Q1 2025 Planning")
- Non-release fix versions (e.g., "Backlog", "Future")

#### Team Member Validation
Jira usernames configured per team. Only issues with team members as assignee counted in releases.

**Prevents**: Organization-wide releases inflating team's deployment frequency

#### Timezone-Aware Datetimes
All timestamps converted to UTC with timezone info:
```python
datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
```

**Prevents**: Timezone bugs causing incorrect date filtering

#### Library Bug Workaround
**Bug**: Jira Python library v3.x throws `TypeError: NoneType` when using `fields='key'`

**Workaround**: Fetch all fields instead of selective fields
```python
# Bug-prone (selective fields)
issues = jira.search_issues(jql, fields='key')  # Crashes

# Workaround (all fields)
issues = jira.search_issues(jql)  # Works
```

**Trade-off**: Slightly larger API responses (~10-15 fields vs 1)

**Code Reference**: `jira_collector.py:_get_issues_for_version()`, commit 6451da5

### Known Data Quality Issues

#### Issue 1: Jira Noise from Bulk Updates
- **Status**: ✅ Fixed (Anti-noise JQL filtering)
- **Details**: See "Anti-Noise JQL Filtering" section

#### Issue 2: Over-Counting Releases
- **Status**: ✅ Fixed (Three-tier filtering)
- **Details**: See "Three-Tier Release Filtering" section
- **Documentation**: `docs/JIRA_FIX_VERSION_TROUBLESHOOTING.md`

#### Issue 3: Jira Library TypeError
- **Status**: ✅ Workaround in place
- **Details**: See "Library Bug Workaround" section

## Summary of Recent Fixes (Jan 17, 2026)

### GitHub Secondary Rate Limit (403 errors)
**Problem**: Automated collection failing with "secondary rate limit" errors

**Root Cause**: 5 concurrent repository workers + no delays = too many requests/second

**Fix Applied**:
1. Added 403 retry logic with longer backoff (5s, 10s, 20s)
2. Added 200ms delay between repository submissions
3. Reduced `repo_workers` from 5 → 3

**Code Changes**: `src/collectors/github_graphql_collector.py:103-120`, `:301-307`

**Result**: No more 403 errors, collection succeeds

### Date Comparison TypeError
**Problem**: `'<=' not supported between instances of 'str' and 'datetime.datetime'`

**Root Cause**: Person metrics collection filters by `end_date`, but some date fields stored as ISO strings

**Fix Applied**: Safe date comparison helper that handles both datetime objects and ISO strings

**Code Changes**: `src/collectors/github_graphql_collector.py:1196-1209`

**Result**: Person metrics collection succeeds

### Missing cycle_time_hours Field
**Problem**: `KeyError: 'cycle_time_hours'` when calculating team metrics

**Root Cause**: Old `_extract_pr_data()` method (used in sequential collection fallback) doesn't calculate `cycle_time_hours`

**Fix Applied**: Added `cycle_time_hours` and `time_to_first_review_hours` calculation to `_extract_pr_data()`

**Code Changes**: `src/collectors/github_graphql_collector.py:477-518`

**Result**: Metrics calculation succeeds for all PRs

**Note**: This document was created on Jan 17, 2026 after fixing automated collection issues.
