# Phase 2 DORA Metrics - Part 1: GitHub Release Collection

## Status: ✅ COMPLETE

## Implementation Date
January 11, 2026

## Summary
Successfully implemented GitHub release collection using the GraphQL API. Releases are now collected alongside PRs, reviews, and commits during the standard data collection process.

## Changes Made

### 1. GitHub GraphQL Collector (`src/collectors/github_graphql_collector.py`)

**Added Methods:**
- `_collect_releases_graphql(owner, repo_name)` - Collects releases from GitHub GraphQL API
  - Paginates through releases ordered by creation date (descending)
  - Filters by date range (since_date)
  - Skips draft releases
  - Extracts tag name, dates, author, commit info
  - Lines: 264-388

- `_classify_release_environment(tag_name, is_prerelease)` - Classifies releases as production/staging
  - Production: vX.Y.Z semantic version tags without suffixes
  - Staging: Tags with -rc, -beta, -alpha, -dev, -preview, -snapshot suffixes
  - Respects GitHub's prerelease flag
  - Case-insensitive pattern matching
  - Lines: 390-432

**Modified Methods:**
- `collect_all_metrics()` - Added 'releases' key to all_data dictionary (line 175)
- `_collect_repository_metrics()` - Now calls `_collect_releases_graphql()` and includes releases in return (lines 492-500)
- `_filter_by_team_members()` - Includes releases in filtered data (line 259, doesn't filter by person)
- `get_dataframes()` - Returns releases DataFrame (line 771)

**Release Data Structure:**
```python
{
    'repo': 'owner/repo-name',
    'tag_name': 'v1.2.3',
    'release_name': 'Version 1.2.3',
    'published_at': datetime,           # When released publicly
    'created_at': datetime,             # When created
    'environment': 'production',        # or 'staging'
    'author': 'github_username',
    'commit_sha': 'abc123...',
    'committed_date': datetime,
    'is_prerelease': False
}
```

### 2. Data Collection Script (`collect_data.py`)

**Changes:**
- Line 373: Added 'releases' to `all_github_data` dictionary initialization
- Line 427: Extend all_github_data with team releases
- Line 433: Print releases count if any collected
- Line 450: Added 'releases' DataFrame to team_dfs

### 3. Test Suite (`tests/unit/test_release_collection.py`)

**Created comprehensive tests for:**
- Production release classification (v1.2.3, 1.2.3)
- Staging release classification (-rc, -beta, -alpha, -dev, -preview, -snapshot)
- Prerelease flag handling
- Case insensitive pattern matching
- Non-standard tag handling
- Multiple suffix patterns

**Test Results:**
```
14 tests collected
14 passed (100%)
Test duration: 0.78 seconds
```

## Environment Classification Logic

### Production Tags
- Pattern: `^v?\d+\.\d+\.\d+$`
- Examples: `v1.2.3`, `v10.20.30`, `1.2.3`
- Must have no suffix, clean semantic version only

### Staging Tags
- Patterns: `-rc`, `-beta`, `-alpha`, `-dev`, `-test`, `-preview`, `-snapshot`
- Examples: `v1.2.3-rc1`, `v1.2.3-beta.1`, `v1.2.3-alpha`
- Case insensitive matching
- Any GitHub prerelease flag = staging

### Default Behavior
- Non-standard tags default to staging for safety
- Examples: `my-custom-release`, `hotfix-branch` = staging

## GraphQL Query

```graphql
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    releases(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        name
        tagName
        createdAt
        publishedAt
        isPrerelease
        isDraft
        author { login }
        tagCommit {
          oid
          committedDate
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
```

## Collection Behavior

1. **Date Filtering**: Uses `published_at` (or `created_at` as fallback) for date range filtering
2. **Early Termination**: Stops pagination when a full page has no releases in date range
3. **Draft Handling**: Skips draft releases entirely
4. **Error Handling**: Warnings logged for collection errors, continues with other repos
5. **Team-Level Data**: Releases are NOT filtered by individual contributors (team-level metric)

## Integration Points

**Collected Alongside:**
- Pull Requests
- Code Reviews
- Commits

**Available In:**
- `all_github_data['releases']` - Combined list from all teams
- `team_github_data['releases']` - Per-team release list
- `team_dfs['releases']` - DataFrame ready for MetricsCalculator

## Verification Steps

To verify the implementation works:

```bash
# 1. Run tests
source venv/bin/activate
pytest tests/unit/test_release_collection.py -v

# 2. Run data collection (will now include releases)
python collect_data.py

# 3. Check collected releases in cache
python3 << 'EOF'
import pickle
with open('data/metrics_cache_90d.pkl', 'rb') as f:
    cache = pickle.load(f)

# Check team releases
for team_name, team_data in cache['teams'].items():
    releases = team_data.get('github', {}).get('releases', [])
    print(f"{team_name}: {len(releases)} releases")

    # Show production vs staging breakdown
    prod = [r for r in releases if r['environment'] == 'production']
    staging = [r for r in releases if r['environment'] == 'staging']
    print(f"  Production: {len(prod)}, Staging: {len(staging)}")
EOF
```

## Next Steps (Part 2: DORA Metrics Calculation)

With releases now collected, the next step is to implement DORA metrics calculation in `src/models/metrics.py`:

1. **Deployment Frequency** - Count production releases per time period
2. **Lead Time for Changes** - Calculate time from PR merge to next deployment
3. **Change Failure Rate** - Correlate incidents with deployments (requires Jira incident data)
4. **Mean Time to Restore** - Calculate median incident resolution time

See: `/Users/zmaros/.claude/plans/declarative-wiggling-squid.md` for full implementation plan.

## Files Modified

1. `src/collectors/github_graphql_collector.py` (+170 lines)
2. `collect_data.py` (+5 lines)
3. `tests/unit/test_release_collection.py` (+128 lines, new file)
4. `docs/DORA_PHASE2_PART1_COMPLETE.md` (this file, new)

## API Impact

- **No additional rate limit concerns**: Release data is collected from same repositories already being queried
- **Minimal performance impact**: Releases query runs in parallel with PR/commit collection
- **Pagination efficiency**: Early termination prevents unnecessary API calls

## Backwards Compatibility

✅ **Fully backwards compatible**
- Existing code continues to work
- Empty releases list if not used
- No breaking changes to existing metrics
- All existing tests pass
