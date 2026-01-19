# Analysis & Verification Tools

This directory contains scripts for analyzing, verifying, and troubleshooting the Team Metrics system. These are not part of the core application but are useful for maintenance and debugging.

## Tools

### Data Analysis

**`analyze_releases.py`**
- **Purpose**: Analyze release data from cache and compute DORA metrics
- **Usage**:
  ```bash
  python tools/analyze_releases.py                    # Show all releases
  python tools/analyze_releases.py "Native Team" "Live - 21/Oct/2025"  # Specific release
  ```
- **Output**: Release list, issue counts, DORA metrics (deployment frequency, lead time, CFR, MTTR)

**`check_dora_data.py`**
- **Purpose**: Diagnostic tool to inspect DORA metrics data in cache
- **Usage**:
  ```bash
  python tools/check_dora_data.py
  ```
- **Output**: Detailed breakdown of DORA metrics from cached data

**`check_lead_time_mapping.py`**
- **Purpose**: Debug PR to Jira issue to release mapping for lead time calculation
- **Usage**:
  ```bash
  python tools/check_lead_time_mapping.py
  ```
- **Output**: Mapping results showing how PRs connect to releases via Jira issues

### Collection Verification

**`verify_collection.sh`**
- **Purpose**: Quick verification that collection completed successfully
- **Usage**:
  ```bash
  ./tools/verify_collection.sh
  ```
- **Checks**: NoneType errors, releases collected, issue mapping, cache freshness

**`verify_jira_versions.py`**
- **Purpose**: Verify Jira fix version naming patterns are recognized
- **Usage**:
  ```bash
  python tools/verify_jira_versions.py
  ```
- **Output**: Pattern matching results for different version naming conventions

**`verify_scope_filter.py`**
- **Purpose**: Test WebTC Jira scope filter functionality
- **Usage**:
  ```bash
  python tools/verify_scope_filter.py
  ```

### Testing & Performance

**`test_dora_performance.py`**
- **Purpose**: Manual test to verify DORA metrics are included in performance scores
- **Usage**:
  ```bash
  python tools/test_dora_performance.py
  ```
- **Output**: Performance score breakdown showing DORA metric contributions

## When to Use These Tools

- **After collection runs**: Use `verify_collection.sh` to check for issues
- **Investigating DORA metrics**: Use `analyze_releases.py` to see detailed breakdown
- **Troubleshooting Jira**: Use `verify_jira_versions.py` or `verify_scope_filter.py`
- **Performance debugging**: Use `test_dora_performance.py` to validate scoring

## Adding New Tools

When adding new analysis/verification scripts:
1. Place them in this directory
2. Update this README with purpose and usage
3. Follow the naming convention: `verb_noun.py` (e.g., `analyze_releases.py`, `verify_collection.sh`)
4. Include a docstring explaining the tool's purpose
