# DORA Metrics Improvements

## Summary

This document describes the improvements made to the DORA metrics implementation based on the validation report findings.

**Date:** 2026-01-18
**Status:** Implemented and Tested

---

## Changes Implemented

### 1. ✅ Enhanced Zero Incidents Handling

**Problem:** When zero incidents were collected, the system displayed "unknown" status with negative messaging ("Incident data not available"), even though zero incidents is actually excellent.

**Solution:** Distinguish between three states:
- `incidents_df is None` → "Incident data not configured" (unknown, low badge)
- `incidents_df.empty` → "No incidents (Excellent!)" (elite, elite badge)
- `incidents_df with data` → Calculate CFR/MTTR normally

**Files Modified:**
- `src/models/dora_metrics.py:408-432` - CFR handling
- `src/models/dora_metrics.py:519-547` - MTTR handling

**Impact:**
- CFR: 0.0% with elite badge when zero incidents
- MTTR: 0 hours with elite badge when zero incidents
- Both metrics now correctly treat zero incidents as positive indicators

---

### 2. ✅ Lead Time Outlier Filtering

**Problem:** Lead times of 300-500+ days were inflating trend data and distorting metrics, likely due to old PRs cherry-picked to releases months later or incorrect Fix Version mappings.

**Solution:** Add configurable max threshold with automatic filtering:
- Default: 180 days (configurable in `config.yaml`)
- Filters outliers before calculating median/average/P95
- Logs filtering activity: "Filtered X lead time outliers (>180 days) from Y total PRs"
- If all values filtered: Returns "note" explaining threshold

**Files Modified:**
- `config/config.yaml` - Added `dora_metrics` section
- `config/config.example.yaml` - Added `dora_metrics` section with documentation
- `src/config.py:205-227` - New `dora_config` property
- `src/models/dora_metrics.py:29-46` - Updated method signature
- `src/models/dora_metrics.py:180-198` - Updated lead time method signature
- `src/models/dora_metrics.py:281-305` - Outlier filtering logic
- `src/models/metrics.py:264-286` - Accept and default dora_config
- `collect_data.py:471` - Pass dora_config to calculator

**Configuration:**
```yaml
dora_metrics:
  max_lead_time_days: 180  # Filter lead times > 180 days
  cfr_correlation_window_hours: 24  # Hours for incident correlation
```

**Impact:**
- More accurate lead time medians (removes 300-500 day outliers)
- Cleaner trend data
- Configurable per organization's needs

---

### 3. ✅ Configurable CFR Correlation Window

**Problem:** The 24-hour correlation window for matching incidents to deployments was hardcoded, making it inflexible for teams with different incident response patterns.

**Solution:** Make correlation window configurable:
- Default: 24 hours (configurable in `config.yaml`)
- Passed through entire call chain to CFR calculation
- Uses same `dora_metrics` config section as lead time

**Files Modified:**
- `config/config.yaml` - Added `cfr_correlation_window_hours: 24`
- `config/config.example.yaml` - Added with documentation
- `src/config.py:205-227` - Loads from config with default
- `src/models/dora_metrics.py:35-36` - Method parameter
- `src/models/dora_metrics.py:91-93` - Pass to CFR method
- `src/models/dora_metrics.py:411-420` - Updated method signature
- `src/models/dora_metrics.py:475-479` - Removed hardcoded value, use parameter
- `src/models/metrics.py:324-325` - Pass from dora_config
- `collect_data.py:471` - Pass dora_config to calculator

**Impact:**
- Teams can adjust based on their incident response time
- More flexible CFR calculation
- Preserves existing 24-hour default behavior

---

### 4. ✅ Fix Multiple Fix Versions Overwriting

**Problem:** If a Jira issue had multiple Fix Versions (e.g., deployed in v1.0 and v1.1), the `issue_to_version_map` only stored the last version processed, potentially mapping PRs to wrong deployments.

**Solution:** Track the **earliest** deployment for each issue:
- Sort releases by `published_at` date (earliest first)
- Only map issue key if not already mapped
- Earliest deployment wins (most accurate for lead time)

**Files Modified:**
- `collect_data.py:449-461` - Sort releases and use earliest mapping

**Before:**
```python
for release in jira_releases:
    for issue_key in release.get("related_issues", []):
        issue_to_version_map[issue_key] = release["tag_name"]  # Last wins!
```

**After:**
```python
sorted_releases = sorted(
    jira_releases,
    key=lambda r: r.get("published_at", "9999-12-31")
)
for release in sorted_releases:
    for issue_key in release.get("related_issues", []):
        if issue_key not in issue_to_version_map:  # Earliest wins
            issue_to_version_map[issue_key] = release["tag_name"]
```

**Impact:**
- More accurate lead time calculation
- Prevents issues from being mapped to later deployments
- Handles cherry-pick workflows correctly

---

## Configuration Reference

### New DORA Metrics Section

Add to `config/config.yaml`:

```yaml
# DORA Metrics configurations
dora_metrics:
  max_lead_time_days: 180  # Filter out lead times > 180 days (likely data errors)
  cfr_correlation_window_hours: 24  # Hours after deployment to correlate incidents
```

**Defaults if not specified:**
- `max_lead_time_days: 180`
- `cfr_correlation_window_hours: 24`

---

## Testing

All existing tests pass after changes:

```bash
pytest tests/unit/test_dora_metrics.py -v
# ============================== 39 passed in 1.19s ===============================
```

**Coverage:** DORA metrics module maintains 82.75% test coverage

---

## Validation Results

### Before Changes
- **CFR:** "unknown" with "Incident data not available" (negative message)
- **MTTR:** "unknown" with "Incident data not available" (negative message)
- **Lead Time:** Included 300-500 day outliers in trend data
- **Issue Mapping:** Last Fix Version won if multiple versions

### After Changes
- **CFR:** 0.0% with "No incidents (Excellent!)" and elite badge ✅
- **MTTR:** 0 hours with "No incidents to restore (Excellent!)" and elite badge ✅
- **Lead Time:** Filters outliers >180 days, logs filtering activity ✅
- **Issue Mapping:** Earliest Fix Version wins, more accurate lead time ✅

---

## Backward Compatibility

All changes are backward compatible:

1. **Zero incidents handling:** Improves display, no breaking changes
2. **Lead time filtering:** Uses sensible default (180 days), optional config
3. **CFR correlation window:** Uses existing default (24 hours), optional config
4. **Fix Version mapping:** More correct behavior, no API changes

**No migration required** - existing caches and configurations continue to work.

---

## Next Steps (Recommended)

### Priority 1: Verify Jira Incident Filters
- Open filters 84312 (Native) and 84313 (WebTC) in Jira web UI
- Confirm if zero incidents is accurate or a configuration issue
- If filters are too restrictive, adjust JQL criteria

### Priority 2: Tune Configuration
- Monitor filtered outlier counts in logs
- Adjust `max_lead_time_days` if too many/few are filtered
- Consider adjusting `cfr_correlation_window_hours` based on incident response times

### Priority 3: Improve Native Team Issue Mapping
- Native: Only 24% of releases have team-assigned issues (8/33)
- WebTC: 100% of releases have team-assigned issues (4/4)
- Improve Fix Version assignment discipline for Native team
- Consider backfilling missing Fix Version data

---

## Files Changed

### Configuration
- `config/config.yaml` - Added dora_metrics section
- `config/config.example.yaml` - Added dora_metrics section with docs

### Core Logic
- `src/config.py` - New dora_config property
- `src/models/dora_metrics.py` - Zero incidents handling, outlier filtering, configurable CFR
- `src/models/metrics.py` - Pass dora_config through call chain
- `collect_data.py` - Fix version mapping logic, pass dora_config

### Documentation
- `docs/DORA_IMPROVEMENTS.md` - This file (NEW)

---

## Commit Message Suggestion

```
feat: Improve DORA metrics handling and configurability

- Handle zero incidents as positive (elite badge) vs missing data
- Add configurable lead time outlier filtering (default 180 days)
- Make CFR correlation window configurable (default 24 hours)
- Fix multiple Fix Versions overwriting (use earliest deployment)

Closes: DORA Metrics Validation Report recommendations
All tests pass (39 passed)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Related Documentation

- Original validation report in conversation transcript
- `CLAUDE.md` - DORA metrics overview
- `docs/DORA_PHASE2_COMPLETE.md` - DORA implementation details
- `docs/JIRA_FIX_VERSION_TROUBLESHOOTING.md` - Fix Version guidance
