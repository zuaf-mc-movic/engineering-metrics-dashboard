#!/usr/bin/env python3
"""
Jira Fix Version Verification Script

This script checks your Jira project versions to see:
1. What version names you have
2. Which ones match the expected "Live - D/MMM/YYYY" format
3. Suggests any pattern adjustments needed

Run: python verify_jira_versions.py
"""

import sys
import re
from datetime import datetime, timezone

sys.path.insert(0, '/Users/zmaros/Work/Projects/team_metrics')

from src.config import Config
from src.collectors.jira_collector import JiraCollector


def main():
    print("=" * 70)
    print("Jira Fix Version Verification")
    print("=" * 70)

    # Load config
    try:
        config = Config()
        jira_config = config.jira_config

        if not jira_config or not jira_config.get('server'):
            print(f"\n✗ Jira not configured in config/config.yaml")
            print(f"   Please add jira.server and jira.project_keys to your config")
            return 1

        print(f"\n✓ Config loaded")
        print(f"  Server: {jira_config.get('server')}")
        print(f"  Projects: {', '.join(jira_config.get('project_keys', []))}")
    except Exception as e:
        print(f"\n✗ Error loading config: {e}")
        return 1

    # Create collector
    try:
        collector = JiraCollector(
            server=jira_config['server'],
            username=jira_config.get('username', ''),
            api_token=jira_config.get('api_token', ''),
            project_keys=jira_config.get('project_keys', []),
            days_back=90,
            verify_ssl=False
        )
        print(f"✓ Connected to Jira")
    except Exception as e:
        print(f"\n✗ Error connecting to Jira: {e}")
        return 1

    # Check versions in each project
    total_versions = 0
    matching_versions = 0
    recent_versions = []

    print(f"\n{'='*70}")
    print("Checking Fix Versions in Your Projects")
    print(f"{'='*70}")

    for project_key in jira_config.get('project_keys', []):
        print(f"\n📦 Project: {project_key}")
        print("-" * 70)

        try:
            versions = collector.jira.project_versions(project_key)
            total_versions += len(versions)

            if not versions:
                print("  ⚠️  No versions found in this project")
                continue

            print(f"  Found {len(versions)} version(s)\n")

            # Show recent versions (last 10)
            for version in versions[:10]:
                # Try to parse with our pattern
                parsed = collector._parse_fix_version_name(version.name)

                if parsed:
                    matching_versions += 1
                    env_icon = "🟢" if parsed['environment'] == 'production' else "🔵"
                    recent_versions.append((version.name, parsed))
                    print(f"  {env_icon} {version.name}")
                    print(f"     ✓ Matches pattern")
                    print(f"     Environment: {parsed['environment']}")
                    print(f"     Date: {parsed['published_at'].strftime('%Y-%m-%d')}")
                else:
                    print(f"  ⚠️  {version.name}")
                    print(f"     ✗ Does NOT match expected pattern")

                print()

            if len(versions) > 10:
                print(f"  ... and {len(versions) - 10} more versions")
                print()

        except Exception as e:
            print(f"  ✗ Error: {e}")

    # Summary
    print(f"\n{'='*70}")
    print("Summary")
    print(f"{'='*70}")
    print(f"\nTotal Versions Found: {total_versions}")
    print(f"Matching Pattern: {matching_versions} ({matching_versions/total_versions*100:.1f}%)" if total_versions > 0 else "Matching Pattern: 0")

    if matching_versions > 0:
        print("\n✅ SUCCESS! Your Jira versions match the expected format.")
        print(f"\nWhen you run collect_data.py, it will collect {matching_versions} releases")

        # Show breakdown
        prod_count = sum(1 for _, parsed in recent_versions if parsed['environment'] == 'production')
        staging_count = sum(1 for _, parsed in recent_versions if parsed['environment'] == 'staging')
        print(f"  - Production (Live): {prod_count}")
        print(f"  - Staging (Beta): {staging_count}")
    else:
        print("\n⚠️  WARNING: No versions match the expected pattern.")
        print("\nExpected format examples:")
        print("  ✓ Live - 6/Oct/2025")
        print("  ✓ Beta - 15/Jan/2026")
        print("  ✓ live - 1/Dec/2025  (case insensitive)")
        print("\nYour versions might use a different format.")
        print("We may need to adjust the pattern to match your naming convention.")

    # Pattern explanation
    print(f"\n{'='*70}")
    print("Expected Pattern Details")
    print(f"{'='*70}")
    print("\nThe pattern expects:")
    print("  1. Environment: 'Live' (production) or 'Beta' (staging)")
    print("  2. Separator: ' - ' (space-dash-space)")
    print("  3. Date format: D/MMM/YYYY or DD/MMM/YYYY")
    print("     - Day: 1-31 (single or double digit)")
    print("     - Month: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec")
    print("     - Year: 4 digits")
    print("\nExamples that work:")
    print("  ✓ Live - 6/Oct/2025")
    print("  ✓ Beta - 15/Jan/2026")
    print("  ✓ LIVE - 1/Dec/2025  (case insensitive)")
    print("  ✓ live  -  31/Mar/2025  (extra spaces OK)")
    print("\nExamples that DON'T work:")
    print("  ✗ Live-6/Oct/2025  (missing spaces around dash)")
    print("  ✗ Live - 06/10/2025  (numeric month)")
    print("  ✗ Live - Oct/6/2025  (wrong order)")
    print("  ✗ Prod - 6/Oct/2025  (wrong environment name)")

    print("\n" + "="*70)
    return 0 if matching_versions > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
