# Jira Fix Version DORA Metrics - Troubleshooting Guide

## Quick Diagnosis

Run this first to see what's happening:
```bash
python verify_jira_versions.py
```

---

## Common Issues & Solutions

### Issue 1: "No releases collected from Jira"

**Symptoms:**
```
🚀 Collecting releases from Jira Fix Versions...
  Found 0 versions in project MYPROJ
  Total releases collected: 0
    Production: 0
    Staging: 0
```

**Possible Causes & Solutions:**

#### Cause A: No Fix Versions in Your Projects
**Check:**
```bash
python verify_jira_versions.py
```

**Solution:** Your Jira projects need Fix Versions. Create them in Jira:
1. Go to Project Settings → Versions
2. Create versions with format: `Live - 6/Oct/2025` or `Beta - 15/Jan/2026`

#### Cause B: Version Names Don't Match Pattern
**Check:** Run verification script to see actual version names

**Your versions might look like:**
- `v1.2.3` → GitHub-style (won't match)
- `Release 2025-10-06` → Different format (won't match)
- `Live-6/Oct/2025` → Missing spaces (won't match)

**Solution:** Either:
1. **Rename versions in Jira** to match pattern: `Live - 6/Oct/2025`
2. **Adjust the pattern** in code (see Pattern Customization below)

#### Cause C: Versions Outside 90-Day Window
**Check:** Are your versions older than 90 days?

**Solution:**
- Create newer versions in Jira, OR
- Increase `days_back` in `collect_data.py`:
```python
DAYS_BACK = 180  # Change from 90 to 180
```

---

### Issue 2: "Deployment Frequency shows 0"

**Symptoms:**
- Dashboard shows "0 deployments per week"
- DORA level is "Low"

**Cause:** No production releases found

**Check:**
```bash
python verify_jira_versions.py
```
Look for versions marked with 🟢 (production)

**Solutions:**
1. Ensure versions use "Live" (not "Prod", "Production", or other names)
2. Check versions are within 90-day window
3. Verify versions are being parsed correctly

---

### Issue 3: "Lead Time shows N/A" or "0 PRs"

**Symptoms:**
```
Lead Time for Changes
  Median: —
  No Data
  No PRs mapped to deployments
```

**Possible Causes:**

#### Cause A: No Merged PRs in Period
**Solution:** Wait for PRs to be merged, or extend time window

#### Cause B: PRs Merged Before Deployments
**How it works:** Lead time measures PR merge → next deployment

**Solution:** Ensure you have deployments AFTER PR merges

#### Cause C: PRs Don't Have Jira Issue Keys
**Check:** Look at your PR titles. Do they have issue keys like "PROJ-123"?

**Examples that work:**
- `[PROJ-123] Add new feature`
- `PROJ-456: Fix bug`
- `Feature/PROJ-789-description`

**Solution:**
- The system falls back to time-based matching automatically
- To improve accuracy: Include Jira issue keys in PR titles

---

### Issue 4: "High Lead Time (unexpectedly)"

**Symptoms:** Lead time shows 30+ days when you deploy weekly

**Possible Causes:**

#### Cause A: Time-Based Fallback
When PRs don't have issue keys, lead time = merge → next deployment
- If deployment is weekly, lead time could be 7 days per PR

**Solution:** Include Jira issue keys in PR titles for direct mapping

#### Cause B: Old PRs Still Open
**Check:** Are there very old PRs that finally merged?

**Solution:** This is accurate! Old PRs do have long lead times.

---

### Issue 5: "Change Failure Rate / MTTR shows 'No Data'"

**Symptoms:**
```
Change Failure Rate: —
Incident data not available
```

**Cause:** No incidents collected

**Check:** Do you have a Jira filter for incidents configured?

**Solution:**
1. Check `config/config.yaml` for incidents filter:
```yaml
jira:
  filters:
    incidents: 12345  # Optional
```

2. If no filter: Incidents auto-detected by:
   - Issue type = "Incident"
   - Bugs with priority Blocker/Critical
   - Labels: production, p1, sev1, incident, outage

3. Create incidents in Jira or configure filter

---

### Issue 6: "Connection timeout to Jira"

**Symptoms:**
```
Error: HTTPSConnectionPool(host='jira.yourcompany.com'): Read timed out
```

**Cause:** Large project with many versions/issues

**Solution:** Increase timeout in `src/collectors/jira_collector.py`:
```python
# Line ~30
collector = JiraCollector(
    ...
    timeout=300  # Increase from 120 to 300 seconds
)
```

---

### Issue 7: "Deployment Frequency Dropped After Update"

**Symptoms:**
```
Before: Deployment Frequency: 2.8/week
After:  Deployment Frequency: 1.2/week
```

**This is EXPECTED and CORRECT** ✅

**Why:** The system now accurately counts only:
1. **Actually released versions** (not planned/unreleased ones)
2. **Team-specific releases** (only issues worked on by your team members)

**What Was Fixed:**

#### Fix 1: Version Release Status
Previously counted ALL versions matching the name pattern, including:
- ❌ Unreleased versions (`released=False`)
- ❌ Future releases (scheduled but not deployed yet)

Now checks:
```python
# Only count if version is released AND in the past
if not version.released:
    continue  # Skip unreleased versions
if version.releaseDate > today:
    continue  # Skip future releases
```

**Impact Example:**
- RSC project: Skipped 538 unreleased versions (22% of 2414 total)
- Native Team: 31 → 24 deployments (23% reduction)

#### Fix 2: Team Member Filtering
Previously counted ALL issues in a version, even if other teams did the work.

Now filters by team membership:
```python
# Only count issues assigned to or reported by team members
jql = f'fixVersion = "{version}" AND '
jql += f'(assignee in ({team}) OR reporter in ({team}))'
```

**Impact Example:**
- WebTC Team: 7 → 4 deployments (43% reduction)
- Cross-team releases now counted separately per team

#### Fix 3: Team-Specific Collectors
Each team now gets its own `JiraCollector` instance with team context.

**Result:** Fair apples-to-apples team comparisons (no cross-team contamination).

**What To Expect:**

| Metric | Before Fixes | After Fixes | Change |
|--------|-------------|-------------|--------|
| Deployment Frequency | 2-3/week (inflated) | 0.5-2.0/week (realistic) | 50-70% reduction |
| Lead Time | May be skewed | More accurate | Team-specific |
| DORA Level | Artificially HIGH | Accurate baseline | May drop initially |

**This is GOOD NEWS** - your metrics are now trustworthy! 📊✅

**Common Questions:**

Q: "Why did my metrics drop so much?"
A: Previous metrics were inflated by counting unreleased versions and other teams' work.

Q: "Should I be concerned about lower numbers?"
A: No! These are accurate baselines. Track trends over time to improve.

Q: "Can I see what was filtered out?"
A: Yes! Look for these log messages during collection:
```
✓ Matched 24 released versions
  (Skipped 538 unreleased versions)
  (Skipped 1229 non-matching versions)
```

---

## Pattern Customization

If your version format doesn't match, you can adjust the pattern.

### Your Format: "Production - 2025-10-06"

**Update `src/collectors/jira_collector.py` line 720:**
```python
# Old pattern
pattern = r'^(Live|Beta)\s+-\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})$'

# New pattern for your format
pattern = r'^(Production|Staging)\s+-\s+(\d{4})-(\d{2})-(\d{2})$'
```

**Update parsing logic (line 724-733):**
```python
env_type = match.group(1).lower()  # "production" or "staging"
year = int(match.group(2))         # 2025
month = int(match.group(3))        # 10
day = int(match.group(4))          # 6

# Parse date
date_str = f"{year}-{month:02d}-{day:02d}"
published_at = datetime.strptime(date_str, '%Y-%m-%d')
```

### Your Format: "v1.2.3" (Semantic Versioning)

**This requires different approach** - mapping semantic versions to dates.

Option 1: Add release dates to Jira versions
Option 2: Use GitHub Releases (revert migration)
Option 3: Custom mapping table

Contact for help with this case!

---

## Diagnostic Commands

### See Raw Jira Versions
```python
python3 << 'EOF'
import sys
sys.path.insert(0, '/Users/zmaros/Work/Projects/team_metrics')
from src.config import Config
from src.collectors.jira_collector import JiraCollector

config = Config()
collector = JiraCollector(
    server=config.jira_server,
    username=config.jira_username,
    api_token=config.jira_api_token,
    project_keys=config.jira_project_keys,
    days_back=90
)

for project in config.jira_project_keys:
    versions = collector.jira.project_versions(project)
    print(f"\n{project}:")
    for v in versions:
        print(f"  - {v.name}")
EOF
```

### Check Collected Releases
```python
python3 << 'EOF'
import pickle
with open('data/metrics_cache_90d.pkl', 'rb') as f:
    cache = pickle.load(f)

for team_name, team_data in cache['teams'].items():
    dora = team_data.get('dora', {})
    deploy = dora.get('deployment_frequency', {})

    print(f"\n{team_name}:")
    print(f"  Total Deployments: {deploy.get('total_deployments', 0)}")
    print(f"  Per Week: {deploy.get('per_week', 0)}")
    print(f"  Level: {deploy.get('level', 'unknown')}")
EOF
```

### Test Pattern Matching
```python
python3 << 'EOF'
import sys
sys.path.insert(0, '/Users/zmaros/Work/Projects/team_metrics')
from src.collectors.jira_collector import JiraCollector

collector = JiraCollector(
    server="https://fake.com",
    username="test",
    api_token="test",
    project_keys=["TEST"],
    verify_ssl=False
)

# Test your version names
test_names = [
    "Live - 6/Oct/2025",
    "Your-Version-Name-Here",
    "Another-Version"
]

for name in test_names:
    result = collector._parse_fix_version_name(name)
    print(f"{name}: {'✓ MATCHES' if result else '✗ NO MATCH'}")
    if result:
        print(f"  Environment: {result['environment']}")
        print(f"  Date: {result['published_at']}")
EOF
```

---

## Still Having Issues?

1. **Check the logs** during `collect_data.py`:
   - Look for "Collecting releases from Jira Fix Versions" messages
   - Note any errors or warnings

2. **Run verification script** with verbose output

3. **Check configuration:**
   ```bash
   python3 << 'EOF'
   from src.config import Config
   config = Config()
   print(f"Server: {config.jira_server}")
   print(f"Projects: {config.jira_project_keys}")
   EOF
   ```

4. **Verify Jira connection:**
   - Can you access your Jira in a browser?
   - Are credentials correct in `config/config.yaml`?
   - Is VPN required?

---

## Success Checklist

✅ `verify_jira_versions.py` shows matching versions
✅ `collect_data.py` shows "Total releases collected: X"
✅ Dashboard shows deployment frequency > 0
✅ Lead time shows data (even if using fallback)
✅ DORA level badge appears

If all checks pass → **You're good to go!** 🎉
