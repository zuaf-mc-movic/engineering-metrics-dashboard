#!/usr/bin/env python3
"""Quick diagnostic script to check DORA CFR and MTTR data in cache."""

import pickle
from pathlib import Path

cache_file = Path("data/metrics_cache_90d.pkl")

if not cache_file.exists():
    print(f"❌ Cache file not found: {cache_file}")
    exit(1)

with open(cache_file, "rb") as f:
    cache = pickle.load(f)

print("=" * 80)
print("DORA CFR & MTTR Diagnostic Report")
print("=" * 80)

teams = cache.get("teams", {})
for team_name, team_data in teams.items():
    print(f"\n📊 Team: {team_name}")
    print("-" * 80)

    dora = team_data.get("dora", {})

    # Check CFR
    cfr = dora.get("change_failure_rate", {})
    print(f"\n🔴 Change Failure Rate:")
    print(f"   Rate: {cfr.get('rate_percent')}")
    print(f"   Failed Deployments: {cfr.get('failed_deployments')}")
    print(f"   Total Deployments: {cfr.get('total_deployments')}")
    print(f"   Level: {cfr.get('level')}")
    print(f"   Note: {cfr.get('note')}")

    # Check MTTR
    mttr = dora.get("mttr", {})
    print(f"\n⏱️  Mean Time to Restore:")
    print(f"   Median Hours: {mttr.get('median_hours')}")
    print(f"   Median Days: {mttr.get('median_days')}")
    print(f"   Sample Size: {mttr.get('sample_size')}")
    print(f"   Level: {mttr.get('level')}")
    print(f"   Note: {mttr.get('note')}")

    # Check if incidents data exists
    jira_data = team_data.get("jira", {})
    incidents = jira_data.get("incidents", {})
    print(f"\n🚨 Incidents Data:")
    print(f"   Total Count: {incidents.get('total', 0)}")
    print(f"   Production: {incidents.get('production', 0)}")
    print(f"   Resolved: {incidents.get('resolved', 0)}")

    # Check deployments
    deployment_freq = dora.get("deployment_frequency", {})
    print(f"\n🚀 Deployments (for context):")
    print(f"   Total: {deployment_freq.get('total_deployments')}")
    print(f"   Per Week: {deployment_freq.get('per_week')}")

print("\n" + "=" * 80)
print("Analysis Complete")
print("=" * 80)
