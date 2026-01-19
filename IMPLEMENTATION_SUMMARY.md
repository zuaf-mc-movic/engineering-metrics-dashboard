# Implementation Summary: Codecov Fix + Jira Filter Validation Plan

**Date**: January 19, 2026
**Status**: Codecov fix completed ✅ | Jira validation requires manual completion ⚠️

---

## Part 1: Codecov Upload Fix - ✅ COMPLETED

### What Was Fixed

Updated `.github/workflows/code-quality.yml` to fix Codecov v5 token requirement.

**Changes Made**:
1. Added `token: ${{ secrets.CODECOV_TOKEN }}` parameter
2. Changed `file:` to `files:` (v5 API requirement)
3. Fixed bug in `list_jira_filters.py` to support both `email` and `username` config keys

### Files Modified

- `.github/workflows/code-quality.yml` (lines 67-74)
- `list_jira_filters.py` (lines 38-47)

### Next Steps for User

1. **Add Codecov Token to GitHub Secrets**:
   ```
   GitHub repo → Settings → Secrets and variables → Actions
   Click "New repository secret"
   Name: CODECOV_TOKEN
   Value: 9a5cd4ab-e5df-4b43-964a-b9f79a66dec4
   ```

2. **Commit and Push Changes**:
   ```bash
   git add .github/workflows/code-quality.yml list_jira_filters.py
   git commit -m "fix: Add Codecov token for v5 upload and fix list_jira_filters.py"
   git push
   ```

3. **Verify Fix**:
   - Watch GitHub Actions workflow run
   - Check for successful upload (no more "Token required" error)
   - Verify coverage appears on codecov.io dashboard

---

## Part 2: Jira Filter Validation - ⚠️ MANUAL COMPLETION REQUIRED

### Issue Encountered

Cannot connect to corporate Jira instance from this environment:
- **Error**: HTTP 401 Unauthorized
- **Reason**: Requires authentication to `https://jira.ops.expertcity.com`
- **Blocker**: Cannot export filter configurations or audit JQL queries remotely

### What Needs to Be Done Manually

#### Step 1: Export Filter Configuration (15 min)

**From a machine with Jira access**, run:

```bash
# Export all filters
python list_jira_filters.py > filter_audit_full.txt

# Export team-specific filters
python list_jira_filters.py "Native" > filter_audit_native.txt
python list_jira_filters.py "WebTC" > filter_audit_webtc.txt
```

#### Step 2: Audit Each Filter Type (1-2 hours)

For each filter in `config/config.yaml`, verify JQL queries match validation criteria below:

**Native Team Filters**:
- `wip: 81010` - WIP Filter
- `bugs: 81015` - Active Bugs Filter
- `bugs_created: 81012` - Bug Creation Rate
- `bugs_resolved: 81013` - Bug Resolution Velocity
- `completed_12weeks: 80911` - Throughput/Completed Work
- `incidents: 84312` - DORA Incident Tracking
- `scope: 80910` - Scope/Planning
- `backlog_in_progress: 81014` - Backlog WIP
- `flagged_blocked: 81011` - Blocked Work
- `recently_released: 82112` - Recent Releases

**WebTC Team Filters**:
- `wip: 81024`
- `bugs: 81018`
- `bugs_created: 81019`
- `bugs_resolved: 81020`
- `completed_12weeks: 81021`
- `incidents: 84313`
- `scope: 81023`
- `backlog_in_progress: 81017`
- `flagged_blocked: 81022`
- `recently_released: 82122`

---

### Validation Criteria by Filter Type

#### A. WIP Filters (IDs: 81010, 81024)

**Expected JQL Pattern**:
```jql
project = "PROJECT_KEY"
AND statusCategory != Done
AND assignee in (team_member_1, team_member_2, ...)
```

**Validation Checklist**:
- ✅ Only includes `statusCategory != Done` (not hardcoded statuses)
- ✅ Includes assignee constraint (team members only)
- ✅ No date filters (WIP should show ALL active work)
- ❌ RED FLAG: If includes `resolved` or `closed` status
- ❌ RED FLAG: If missing assignee constraint (returns org-wide WIP)

**Anti-Noise Protection**:
Currently gets automatic time constraint in code (NOT in `filters_needing_time_constraint` list), so WIP filter uses raw JQL from Jira.

**Action if Invalid**:
- Update JQL in Jira to add/fix assignee constraint
- Consider adding to `filters_needing_time_constraint` if returning historical items

---

#### B. Bug Filters (IDs: 81015/81012/81013, 81018/81019/81020)

**Expected JQL Patterns**:

**bugs (active bugs)**:
```jql
project = "PROJECT_KEY"
AND type = Bug
AND statusCategory != Done
AND assignee in (team_members)
```

**bugs_created (bug creation rate)**:
```jql
project = "PROJECT_KEY"
AND type = Bug
AND created >= -90d
AND assignee in (team_members)
```

**bugs_resolved (bug resolution velocity)**:
```jql
project = "PROJECT_KEY"
AND type = Bug
AND resolved >= -90d
AND assignee in (team_members)
```

**Validation Checklist**:
- ✅ Uses `type = Bug` or `issuetype = Bug`
- ✅ Assignee constraint present
- ✅ Created/resolved use relative dates (`>= -90d` not `>= 2025-01-01`)
- ✅ Active bugs: `statusCategory != Done`
- ❌ RED FLAG: Hardcoded dates (will become stale)
- ❌ RED FLAG: Missing assignee (returns org-wide bugs)

**Anti-Noise Protection**:
`bugs` filter gets automatic time constraint added (line 373 of `jira_collector.py`):
```jql
(original_filter_jql) AND (created >= -90d OR resolved >= -90d)
```

**Action if Invalid**:
- Fix hardcoded dates to relative dates
- Add assignee constraints if missing
- Verify bugs filter gets time constraint in code

---

#### C. Throughput/Completed Filters (IDs: 80911, 81021)

**Expected JQL Pattern**:
```jql
project = "PROJECT_KEY"
AND statusCategory = Done
AND resolved >= -12w
AND assignee in (team_members)
```

**Validation Checklist**:
- ✅ Uses `statusCategory = Done` or `status in (Closed, Resolved, Done)`
- ✅ Uses relative time window (`>= -12w` or `>= -90d`)
- ✅ Assignee constraint present
- ✅ Uses `resolved >= X` (not `updated >= X` which includes admin changes)
- ❌ RED FLAG: Uses `updated >= X` (will include closed items with label changes)
- ❌ RED FLAG: Hardcoded date range
- ❌ RED FLAG: Missing assignee constraint

**Anti-Noise Protection**:
This is critical - must use `resolved >= -90d` NOT `updated >= -90d`.
Code doesn't add time constraint to completed_12weeks (not in list at line 373).

**Action if Invalid**:
- Change `updated` to `resolved` in JQL
- Add assignee constraint if missing
- Verify relative date window (not hardcoded)

---

#### D. Incident Filters (IDs: 84312, 84313)

**Expected JQL Pattern**:
```jql
project = "PROJECT_KEY"
AND (type = Incident OR type = Defect OR labels = "incident")
AND resolved >= -90d
AND assignee in (team_members)
```

**Validation Checklist**:
- ✅ Captures production incidents/defects
- ✅ Uses relative date window
- ✅ Assignee constraint present
- ✅ Includes `resolved >= X` to get resolution time
- ❌ RED FLAG: Too narrow (missing incident types)
- ❌ RED FLAG: Too broad (includes dev/staging issues)
- ❌ RED FLAG: Missing assignee (org-wide incidents)

**Critical for DORA**:
- Used for Change Failure Rate (CFR): `failed_deployments / total_deployments`
- Used for Mean Time to Recover (MTTR): median time from incident creation to resolution

**Action if Invalid**:
- Update JQL to capture all production incident types
- Add environment filter if available (`environment = production`)
- Verify assignee constraint

---

#### E. Scope Filters (IDs: 80910, 81023)

**Expected**: Sprint/backlog planning scope

**Validation Checklist**:
- ✅ Uses relative dates or sprint-based queries
- ✅ Assignee constraint
- ❌ RED FLAG: Returns entire backlog history

**Anti-Noise Protection**:
Gets automatic time constraint (line 373 of `jira_collector.py`).

---

#### F. Other Filters

- **backlog_in_progress**: Native=81014, WebTC=81017
- **flagged_blocked**: Native=81011, WebTC=81022
- **recently_released**: Native=82112, WebTC=82122

**Validation**: Verify JQL matches filter name purpose.

---

### Step 3: Cross-Check Filter IDs (15 min)

**Critical**: Verify `config.yaml` filter IDs actually match intended filters in Jira.

**Method**:
1. For each filter ID in `config.yaml`
2. Look up in Jira (via `list_jira_filters.py` output or Jira UI)
3. Verify filter name matches expected purpose

**Example**:
```yaml
# config.yaml
bugs: 81015  # Should be "Rescue Native - Bugs" in Jira
```

**Action if Mismatch**:
- Update `config.yaml` with correct filter ID
- Document in validation report

---

### Step 4: Test Filter Results (30 min)

**Run Existing Validation Tools**:

```bash
# Test scope filter returns data
python tools/verify_scope_filter.py

# Verify Jira version pattern matching
python tools/verify_jira_versions.py

# Test actual collection (dry run with small window)
python collect_data.py --date-range 7d
```

**Verify**:
- Filters return expected issue counts
- No errors in logs
- Issue counts make sense (not 0, not 10,000)

---

### Step 5: Document Findings (30 min)

**Create Validation Report**: `docs/JIRA_FILTER_VALIDATION_REPORT.md`

**Template**:
```markdown
# Jira Filter Validation Report
Date: 2026-01-19

## Summary
- Total filters audited: 20 (10 per team × 2 teams)
- Issues found: X
- Issues fixed: Y
- Remaining concerns: Z

## Filter-by-Filter Results

### Native Team

#### WIP Filter (ID: 81010)
- ✅ Status: Valid
- JQL: `project=RSC AND statusCategory!=Done AND assignee in (...)`
- Concerns: None

#### Bugs Filter (ID: 81015)
- ❌ Status: Invalid - Missing assignee constraint
- JQL: `project=RSC AND type=Bug AND statusCategory!=Done`
- Action Taken: Updated JQL in Jira to add assignee constraint
- New JQL: `project=RSC AND type=Bug AND statusCategory!=Done AND assignee in (...)`

[... continue for all 20 filters ...]

## Issues Fixed

1. **Native bugs filter (81015)**: Added assignee constraint
2. **WebTC completed_12weeks (81021)**: Changed `updated>=` to `resolved>=`
[...]

## Recommendations

1. Add automated filter validation to CI
2. Create filter update checklist for team changes
3. Document filter maintenance procedures
```

---

### Step 6: Code Updates (if needed - 30 min)

**Potential Code Changes**:

**A. Expand Time Constraint List** (if needed)

File: `src/collectors/jira_collector.py` line 373

**Current**:
```python
filters_needing_time_constraint = ["scope", "bugs"]
```

**If WIP/completed_12weeks need time constraints**:
```python
filters_needing_time_constraint = ["scope", "bugs", "wip", "completed_12weeks"]
```

**B. Add Filter Validation to Config Validation**

File: `validate_config.py`

Add checks:
- Verify filter IDs are integers
- Warn if filter IDs look suspicious (e.g., 0, negative)
- Optional: Test connection to each filter ID

**C. Add Filter JQL Inspection Tool** (optional)

New file: `tools/inspect_filter_jql.py`

```python
#!/usr/bin/env python3
"""
Inspect JQL queries for configured filters

Usage: python tools/inspect_filter_jql.py
"""
# Connect to Jira
# For each team's filters:
#   - Fetch filter by ID
#   - Display name + JQL
#   - Run validation checks
#   - Report issues
```

---

## Critical Files Reference

### Modified:
1. `.github/workflows/code-quality.yml` - Codecov token added ✅
2. `list_jira_filters.py` - Fixed email/username compatibility ✅

### To Review:
1. `config/config.yaml` - Current filter configuration
2. Jira filters (via Jira UI) - Update JQL queries for invalid filters
3. `src/collectors/jira_collector.py` - Time constraint logic (line 373)

### To Create:
1. `docs/JIRA_FILTER_VALIDATION_REPORT.md` - Document all findings
2. `tools/inspect_filter_jql.py` - (Optional) Automated filter inspection tool

---

## Validation Checklist

Use this checklist when manually validating filters:

```
Native Team (10 filters):
[ ] 81010 - wip: Valid JQL, assignee constraint, no date filters
[ ] 81015 - bugs: Valid JQL, assignee constraint, statusCategory!=Done
[ ] 81012 - bugs_created: Relative dates (>= -90d), assignee constraint
[ ] 81013 - bugs_resolved: Uses resolved>= (not updated>=), assignee constraint
[ ] 80911 - completed_12weeks: Uses resolved>= (not updated>=), relative dates
[ ] 84312 - incidents: Captures production incidents, assignee constraint
[ ] 80910 - scope: Relative dates or sprint-based
[ ] 81014 - backlog_in_progress: Valid JQL matches purpose
[ ] 81011 - flagged_blocked: Valid JQL matches purpose
[ ] 82112 - recently_released: Valid JQL matches purpose

WebTC Team (10 filters):
[ ] 81024 - wip: Valid JQL, assignee constraint, no date filters
[ ] 81018 - bugs: Valid JQL, assignee constraint, statusCategory!=Done
[ ] 81019 - bugs_created: Relative dates (>= -90d), assignee constraint
[ ] 81020 - bugs_resolved: Uses resolved>= (not updated>=), assignee constraint
[ ] 81021 - completed_12weeks: Uses resolved>= (not updated>=), relative dates
[ ] 84313 - incidents: Captures production incidents, assignee constraint
[ ] 81023 - scope: Relative dates or sprint-based
[ ] 81017 - backlog_in_progress: Valid JQL matches purpose
[ ] 81022 - flagged_blocked: Valid JQL matches purpose
[ ] 82122 - recently_released: Valid JQL matches purpose
```

---

## Timeline Estimate

| Task | Time | Status |
|------|------|--------|
| Part 1: Codecov Fix | 30 min | ✅ COMPLETE |
| Jira Export | 15 min | ⚠️ MANUAL |
| Jira Audit | 1-2 hours | ⚠️ MANUAL |
| Jira Fixes | 1 hour | ⚠️ MANUAL |
| Documentation | 30 min | ⚠️ MANUAL |
| Code Updates (optional) | 30 min | ⚠️ MANUAL |
| Verification | 30 min | ⚠️ MANUAL |
| **Total** | **3.5-4.5 hours** | **30 min done, 3-4h remaining** |

---

## Success Criteria

### Part 1: Codecov - ✅ CAN VERIFY
- ✅ GitHub Actions workflow uploads coverage without errors
- ✅ Coverage report visible on codecov.io dashboard
- ✅ No more "Token required" errors in logs

### Part 2: Jira Filters - ⚠️ REQUIRES MANUAL VALIDATION
- ⚠️ All 20 filter IDs verified to match correct filters
- ⚠️ All filter JQL queries audited for accuracy
- ⚠️ Issues fixed for: WIP, bugs, throughput, incidents
- ⚠️ Validation report created documenting findings
- ⚠️ Test collection runs without errors
- ⚠️ Metrics look reasonable (spot-check)

---

## Next Actions for User

1. **Immediately**:
   - Add `CODECOV_TOKEN` to GitHub Secrets
   - Commit and push changes
   - Verify Codecov upload works

2. **From machine with Jira access**:
   - Run `list_jira_filters.py` to export filter data
   - Audit filter JQL queries against validation criteria
   - Update invalid filters in Jira UI
   - Update `config.yaml` if filter IDs are mismatched
   - Document findings in `docs/JIRA_FILTER_VALIDATION_REPORT.md`
   - Test collection with `python collect_data.py --date-range 7d`

3. **Optional improvements**:
   - Add filter validation checks to `validate_config.py`
   - Create `tools/inspect_filter_jql.py` for automated inspection
   - Add automated filter validation to CI pipeline

---

## Risk Assessment

**Part 1 (Codecov)**: ✅ Low Risk - COMPLETE
- Non-breaking change (adding token)
- Only affects coverage reporting, not tests
- Can revert easily if issues

**Part 2 (Jira Filters)**: ⚠️ Medium Risk - REQUIRES MANUAL COMPLETION
- Changing filter JQL affects metrics accuracy
- Bad JQL could break collection or return wrong data
- Mitigation: Test with 7-day window first, compare before/after
- Recommendation: Fix filters one at a time, testing after each change

---

## Questions?

- Codecov token issues? Check GitHub Secrets configuration
- Jira connection issues? Verify credentials and VPN access
- Filter validation questions? Refer to validation criteria sections above
- Need help with JQL? See Jira documentation or existing filter examples
