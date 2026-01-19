#!/usr/bin/env python3
"""Diagnostic script to analyze lead time mapping from cache"""

import pickle
import re
from datetime import datetime

import pandas as pd


def extract_issue_key(pr):
    """Extract Jira issue key from PR title or branch name"""
    title = pr.get("title", "")
    branch = pr.get("headRefName", "")
    text = f"{title} {branch}"

    match = re.search(r"([A-Z]+-\d+)", text)
    return match.group(1) if match else None


def main():
    # Load cache
    print("Loading cache...")
    with open("data/metrics_cache_90d.pkl", "rb") as f:
        cache = pickle.load(f)

    # Focus on Native Team
    team_name = "Native"

    if team_name not in cache.get("teams", {}):
        print(f"Team '{team_name}' not found in cache")
        return

    team_data = cache["teams"][team_name]

    print(f"\n{'='*80}")
    print(f"ANALYZING: {team_name}")
    print(f"{'='*80}\n")

    # Check issue_to_version_map in team data
    issue_map = team_data.get("issue_to_version_map", {})
    print(f"Issue-to-version map size: {len(issue_map)} entries")
    if issue_map:
        print(f"Sample mappings: {dict(list(issue_map.items())[:10])}\n")
    else:
        print("WARNING: issue_to_version_map is empty!\n")

    # Get PRs
    github_data = team_data.get("github", {})
    raw_data = github_data.get("raw_data", {})
    prs = raw_data.get("prs", [])

    print(f"Total PRs in raw data: {len(prs)}")

    # Convert to DataFrame and filter merged PRs
    prs_df = pd.DataFrame(prs)
    if "merged_at" in prs_df.columns:
        prs_df["merged_at"] = pd.to_datetime(prs_df["merged_at"])
        merged_prs = prs_df[prs_df["merged_at"].notna()]
        print(f"Merged PRs: {len(merged_prs)}\n")
    else:
        print("No merged_at column found\n")
        return

    # Analyze issue key extraction
    print(f"{'='*80}")
    print("PR ANALYSIS")
    print(f"{'='*80}\n")

    prs_with_jira = 0
    prs_mapped_to_version = 0
    prs_no_jira = 0

    sample_prs = []

    for idx, row in merged_prs.head(20).iterrows():
        pr_num = row.get("number")
        title = row.get("title", "")
        branch = row.get("headRefName", "")

        issue_key = extract_issue_key(row)

        if issue_key:
            prs_with_jira += 1
            mapped = issue_key in issue_map
            if mapped:
                prs_mapped_to_version += 1
                version = issue_map[issue_key]
                sample_prs.append(f"PR #{pr_num}: {issue_key} → {version} ✓")
            else:
                sample_prs.append(f"PR #{pr_num}: {issue_key} → NOT IN MAP ✗")
        else:
            prs_no_jira += 1
            sample_prs.append(f"PR #{pr_num}: No Jira key ✗")

    print("Sample of first 20 merged PRs:")
    for line in sample_prs[:10]:
        print(f"  {line}")

    print(f"\n{'='*80}")
    print("SUMMARY (first 20 PRs)")
    print(f"{'='*80}")
    print(f"PRs with Jira key: {prs_with_jira}/20 ({prs_with_jira/20*100:.1f}%)")
    print(f"PRs mapped to version: {prs_mapped_to_version}/20 ({prs_mapped_to_version/20*100:.1f}%)")
    print(f"PRs without Jira key: {prs_no_jira}/20 ({prs_no_jira/20*100:.1f}%)")

    # Check releases
    print(f"\n{'='*80}")
    print("RELEASES")
    print(f"{'='*80}\n")

    jira_data = team_data.get("jira", {})
    releases = jira_data.get("releases", [])

    print(f"Total releases: {len(releases)}")

    releases_with_issues = [r for r in releases if r.get("related_issues")]
    print(f"Releases with related_issues: {len(releases_with_issues)}")

    if releases_with_issues:
        print("\nSample releases with issues:")
        for rel in releases_with_issues[:5]:
            tag = rel.get("tag_name", "?")
            issues = rel.get("related_issues", [])
            print(f"  {tag}: {len(issues)} issues → {issues[:5]}{'...' if len(issues) > 5 else ''}")

    # Check DORA metrics
    print(f"\n{'='*80}")
    print("DORA METRICS")
    print(f"{'='*80}\n")

    dora = team_data.get("dora_metrics", {})
    lead_time = dora.get("lead_time_for_changes", {})

    if lead_time:
        median_days = lead_time.get("median_days")
        sample_size = lead_time.get("sample_size", 0)
        print(f"Lead time median: {median_days} days")
        print(f"Lead time sample size: {sample_size} PRs")
        print(
            f"\nThis means {sample_size}/{len(merged_prs)} PRs ({sample_size/len(merged_prs)*100:.1f}%) were included in lead time calculation"
        )
    else:
        print("No lead time data found")


if __name__ == "__main__":
    main()
