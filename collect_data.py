#!/usr/bin/env python3
"""Collect metrics data and save to cache file

Supports flexible date ranges: 30d, 90d, 365d, Q1-2025, 2024, or custom ranges.
Use --date-range argument to specify the time window.
"""

import pickle
import os
import sys
import shutil
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from src.config import Config
from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.models.metrics import MetricsCalculator
from src.utils.date_ranges import parse_date_range, get_cache_filename, DateRangeError
import pandas as pd

# Default time window (used if no --date-range provided)
DEFAULT_RANGE = "90d"


def validate_github_collection(github_data, team_members, collection_status):
    """Validate GitHub data before caching

    Returns:
        (is_valid, warnings, should_cache)
    """
    warnings = []

    # Check for collection errors
    failed_repos = collection_status.get('failed_repos', [])
    if failed_repos:
        warnings.append(f"❌ {len(failed_repos)} repositories failed to collect")

    # Check for members with no data
    members_with_data = set()
    for pr in github_data.get('pull_requests', []):
        members_with_data.add(pr.get('author'))
    for commit in github_data.get('commits', []):
        members_with_data.add(commit.get('author'))

    missing_members = set(team_members) - members_with_data
    if missing_members:
        warnings.append(f"⚠️  {len(missing_members)} members have no GitHub data: {', '.join(list(missing_members)[:5])}")

    # Check total data volume
    total_prs = len(github_data.get('pull_requests', []))
    total_commits = len(github_data.get('commits', []))

    if total_prs == 0 and total_commits == 0:
        warnings.append(f"❌ CRITICAL: No GitHub data collected at all!")
        return False, warnings, False

    # Check against previous cache if available (use default cache name)
    default_cache = 'data/' + get_cache_filename(DEFAULT_RANGE)
    if os.path.exists(default_cache):
        try:
            with open(default_cache, 'rb') as f:
                prev_cache = pickle.load(f)

            prev_prs = sum(len(m.get('raw_github_data', {}).get('pull_requests', []))
                          for m in prev_cache.get('persons', {}).values())

            if total_prs < prev_prs * 0.5:  # 50% drop
                warnings.append(f"⚠️  PR count dropped significantly: {prev_prs} → {total_prs}")
        except Exception:
            pass  # Can't load previous cache, skip comparison

    # Decide if we should cache
    should_cache = True
    if failed_repos and len(failed_repos) > len(collection_status.get('successful_repos', [])):
        # More failures than successes
        warnings.append("❌ Too many failures - recommend re-running collection")
        should_cache = False

    return len(warnings) == 0, warnings, should_cache


def load_failed_repos_from_cache(cache_file):
    """Load list of failed repos from previous collection"""
    if not os.path.exists(cache_file):
        return []

    try:
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)

        github_status = cache.get('collection_status', {}).get('github', {})
        failed_repos = github_status.get('failed_repos', [])

        if failed_repos:
            print("\n" + "=" * 70)
            print("Previous Collection Had Failures")
            print("=" * 70)
            print(f"\n📝 Found {len(failed_repos)} failed repositories from previous run:")
            for failed in failed_repos[:10]:  # Show first 10
                print(f"   - {failed['repo']}: {failed.get('error', 'Unknown error')[:60]}")
            if len(failed_repos) > 10:
                print(f"   ... and {len(failed_repos) - 10} more")
            print()

        return failed_repos

    except Exception as e:
        print(f"⚠️  Could not load previous cache: {e}")
        return []


def map_github_to_jira_username(github_username: str, teams: List[Dict]) -> Optional[str]:
    """
    Map a GitHub username to corresponding Jira username.

    Supports both config formats:
    - New format: members list with github/jira mapping
    - Old format: separate github.members and jira.members lists (matched by index)

    Args:
        github_username: GitHub username to look up
        teams: List of team configurations

    Returns:
        Jira username or None if not found
    """
    for team in teams:
        # Check for new format: members list with github/jira keys
        if 'members' in team and isinstance(team['members'], list):
            for member in team['members']:
                if isinstance(member, dict):
                    if member.get('github') == github_username:
                        return member.get('jira')

        # Fall back to old format: parallel lists
        github_members = team.get('github', {}).get('members', [])
        jira_members = team.get('jira', {}).get('members', [])

        if github_username in github_members:
            # Find index in GitHub members
            idx = github_members.index(github_username)
            # Return corresponding Jira member if it exists
            if idx < len(jira_members):
                return jira_members[idx]

    return None


def build_member_name_mapping(teams: List[Dict]) -> Dict[str, str]:
    """
    Build mapping from GitHub username to display name.

    Supports both config formats:
    - New format: members list with name/github/jira mapping
    - Old format: separate github.members and jira.members lists (uses username as name)

    Args:
        teams: List of team configurations

    Returns:
        Dict mapping github_username -> display_name
    """
    name_mapping = {}

    for team in teams:
        # Check for new format: members list with github/jira keys
        if 'members' in team and isinstance(team['members'], list):
            for member in team['members']:
                if isinstance(member, dict):
                    github = member.get('github')
                    name = member.get('name')
                    if github and name:
                        name_mapping[github] = name
                    elif github:
                        # Fallback: use GitHub username if no name provided
                        name_mapping[github] = github
        # Fall back to old format: github.members
        else:
            github_members = team.get('github', {}).get('members', [])
            for github in github_members:
                name_mapping[github] = github  # Use username as fallback

    return name_mapping


# Parse command-line arguments
parser = argparse.ArgumentParser(
    description='Collect team metrics data from GitHub and Jira',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog='''
Examples:
  python collect_data.py                    # Use default 90-day window
  python collect_data.py --date-range 30d   # Last 30 days
  python collect_data.py --date-range Q1-2025  # Q1 2025
  python collect_data.py --date-range 2024  # Full year 2024
  python collect_data.py --date-range 2024-01-01:2024-03-31  # Custom range
    '''
)
parser.add_argument(
    '--date-range',
    type=str,
    default=DEFAULT_RANGE,
    help=f'Date range to collect (default: {DEFAULT_RANGE}). '
         'Formats: 30d, 90d, Q1-2025, 2024, YYYY-MM-DD:YYYY-MM-DD'
)

args = parser.parse_args()

# Parse the date range
try:
    date_range = parse_date_range(args.date_range)
except DateRangeError as e:
    print(f"❌ Error: {e}")
    print()
    print("Valid formats:")
    print("  - Days: 30d, 90d, 180d, 365d")
    print("  - Quarters: Q1-2025, Q2-2024")
    print("  - Years: 2024, 2025")
    print("  - Custom: 2024-01-01:2024-12-31")
    sys.exit(1)

# Determine cache filename based on date range
cache_filename = get_cache_filename(date_range.range_key)
cache_file = os.path.join('data', cache_filename)

print("=" * 70)
print("Team Metrics Data Collection")
print("=" * 70)
print()

# Check for resume opportunity
failed_repos_prev = load_failed_repos_from_cache(cache_file)
retry_mode = False

if failed_repos_prev:
    try:
        response = input("Retry failed repositories only? (y/n): ").strip().lower()
        if response == 'y':
            retry_mode = True
            print("\n🔄 Running in RETRY MODE - collecting previously failed repos\n")
            print("Note: This will merge with existing cache data.")
            print()
    except (EOFError, KeyboardInterrupt):
        print("\nContinuing with full collection...")
        retry_mode = False

# Use parsed date range
start_date = date_range.start_date
end_date = date_range.end_date
days_back = date_range.days

print(f"📅 Date Range: {date_range.description}")
print(f"   From: {start_date.strftime('%Y-%m-%d')}")
print(f"   To:   {end_date.strftime('%Y-%m-%d')}")
print(f"   Days: {days_back}")
print(f"   Cache: {cache_filename}")
print()

config = Config()

# Check if teams are configured
teams = config.teams

if not teams:
    print("⚠️  No teams configured. Using legacy collection mode...")
    print()

    # Legacy collection (original behavior)
    # Note: Legacy GitHubCollector (REST API) is deprecated - this path shouldn't execute
    # Keeping for reference but may be removed in future versions
    print("⚠️  WARNING: Using deprecated legacy collection path")
    print("   Please configure teams in config.yaml to use modern GraphQL collector")
    print()

    from src.collectors.github_collector import GitHubCollector
    github_collector = GitHubCollector(
        token=config.github_token,
        repositories=config.github_repositories if config.github_repositories else None,
        organization=config.github_organization,
        teams=config.github_teams,
        team_members=config.github_team_members,
        days_back=days_back
    )

    dataframes = github_collector.get_dataframes()

    print(f"✅ GitHub collection complete!")
    print(f"   - Pull Requests: {len(dataframes['pull_requests'])}")
    print(f"   - Reviews: {len(dataframes['reviews'])}")
    print(f"   - Commits: {len(dataframes['commits'])}")
    print()

    # Collect Jira metrics
    jira_config = config.jira_config
    if jira_config.get('server') and jira_config.get('project_keys'):
        try:
            print("📊 Collecting Jira metrics...")
            jira_collector = JiraCollector(
                server=jira_config['server'],
                username=jira_config['username'],
                api_token=jira_config['api_token'],
                project_keys=jira_config['project_keys'],
                team_members=config.jira_team_members,
                days_back=days_back,
                verify_ssl=False
            )

            jira_dataframes = jira_collector.get_dataframes()
            dataframes['jira_issues'] = jira_dataframes['issues']
            dataframes['jira_worklogs'] = jira_dataframes['worklogs']

            print(f"✅ Jira collection complete!")
            print(f"   - Issues: {len(jira_dataframes['issues'])}")
            print()
        except Exception as e:
            print(f"⚠️  Jira collection failed: {e}")
            dataframes['jira_issues'] = pd.DataFrame()
            dataframes['jira_worklogs'] = pd.DataFrame()
    else:
        dataframes['jira_issues'] = pd.DataFrame()
        dataframes['jira_worklogs'] = pd.DataFrame()

    # Calculate metrics
    print("🔢 Calculating metrics...")
    calculator = MetricsCalculator(dataframes)
    metrics = calculator.get_all_metrics()

    # Save to cache
    cache_data = {
        'data': metrics,
        'timestamp': datetime.now()
    }

else:
    # New team-based collection
    print(f"📊 Collecting metrics for {len(teams)} team(s)...")
    print()

    # Initialize collectors
    github_token = config.github_token
    jira_config = config.jira_config

    if not github_token:
        print("❌ Error: GitHub token not configured")
        exit(1)

    if not jira_config.get('server'):
        print("⚠️  Warning: Jira not configured. Jira metrics will be skipped.")
        jira_collector = None
    else:
        try:
            jira_collector = JiraCollector(
                server=jira_config['server'],
                username=jira_config['username'],
                api_token=jira_config['api_token'],
                project_keys=jira_config.get('project_keys', []),
                days_back=days_back,
                verify_ssl=False
            )
            print("✅ Connected to Jira")
        except Exception as e:
            print(f"⚠️  Could not connect to Jira: {e}")
            jira_collector = None

    # Collect data for each team
    team_metrics = {}
    all_github_data = {
        'pull_requests': [],
        'reviews': [],
        'commits': [],
        'deployments': [],
        'releases': []
    }

    for team in teams:
        team_name = team.get('name')
        team_display = team.get('display_name', team_name)

        print(f"\n{'='*70}")
        print(f"Team: {team_display}")
        print(f"{'='*70}")

        # Extract members - support both new unified format and old format
        github_members = []
        jira_members = []

        if 'members' in team and isinstance(team.get('members'), list):
            # New format: unified members list
            for member in team['members']:
                if isinstance(member, dict):
                    if member.get('github'):
                        github_members.append(member['github'])
                    if member.get('jira'):
                        jira_members.append(member['jira'])
        else:
            # Old format: separate arrays
            github_members = team.get('github', {}).get('members', [])
            jira_members = team.get('jira', {}).get('members', [])

        filter_ids = team.get('jira', {}).get('filters', {})

        # Extract team_slug for GitHub team repositories
        team_slug = team.get('github', {}).get('team_slug')
        team_slugs = [team_slug] if team_slug else []

        print(f"GitHub members: {len(github_members)}")
        print(f"Jira members: {len(jira_members)}")

        # Collect GitHub metrics for team using GraphQL API
        print(f"\n📊 Collecting GitHub metrics for {team_display} (using GraphQL API)...")

        github_collector = GitHubGraphQLCollector(
            token=github_token,
            organization=config.github_organization,
            teams=team_slugs,
            team_members=github_members,
            days_back=days_back
        )

        team_github_data = github_collector.collect_all_metrics()

        # Add to combined dataset
        all_github_data['pull_requests'].extend(team_github_data['pull_requests'])
        all_github_data['reviews'].extend(team_github_data['reviews'])
        all_github_data['commits'].extend(team_github_data['commits'])
        all_github_data['deployments'].extend(team_github_data['deployments'])
        # Note: Releases now collected from Jira Fix Versions (below)

        print(f"   - PRs: {len(team_github_data['pull_requests'])}")
        print(f"   - Reviews: {len(team_github_data['reviews'])}")
        print(f"   - Commits: {len(team_github_data['commits'])}")

        # Collect Jira filter metrics for team
        jira_filter_results = {}
        if jira_collector and filter_ids:
            print(f"\n📊 Collecting Jira filter metrics for {team_display}...")
            jira_filter_results = jira_collector.collect_team_filters(filter_ids)

        # Collect releases from Jira Fix Versions instead of GitHub
        if jira_collector:
            print(f"\n🚀 Collecting releases from Jira Fix Versions for {team_display}...")
            # Use team-specific project keys if available, otherwise use global keys
            team_project_keys = team.get('jira', {}).get('project_keys', jira_collector.project_keys)
            jira_releases = jira_collector.collect_releases_from_fix_versions(
                project_keys=team_project_keys
            )
            all_github_data['releases'].extend(jira_releases)  # Still use 'releases' key for DORA metrics
            print(f"   - Releases (from Jira): {len(jira_releases)}")

        # Calculate team metrics
        print(f"\n🔢 Calculating team metrics for {team_display}...")

        # Build mapping: issue key → fix version name (for lead time calculation)
        issue_to_version_map = {}
        if jira_collector:
            for release in jira_releases:
                for issue_key in release.get('related_issues', []):
                    issue_to_version_map[issue_key] = release['tag_name']
            print(f"   - Mapped {len(issue_to_version_map)} issues to fix versions")

        # Convert to DataFrames for calculator
        team_dfs = {
            'pull_requests': pd.DataFrame(team_github_data['pull_requests']),
            'reviews': pd.DataFrame(team_github_data['reviews']),
            'commits': pd.DataFrame(team_github_data['commits']),
            'deployments': pd.DataFrame(team_github_data['deployments']),
            'releases': pd.DataFrame(all_github_data['releases'])  # Use all collected releases (from Jira)
        }

        calculator = MetricsCalculator(team_dfs)
        team_metrics[team_name] = calculator.calculate_team_metrics(
            team_name=team_name,
            team_config=team,
            jira_filter_results=jira_filter_results,
            issue_to_version_map=issue_to_version_map  # NEW parameter for DORA lead time
        )

        print(f"✅ {team_display} metrics complete")

    # Collect person-level metrics (same 90-day window as teams)
    print(f"\n{'='*70}")
    print("Collecting Person-Level Metrics")
    print(f"{'='*70}")

    person_metrics = {}
    # Use same date range as team collection (already calculated above)
    # Person metrics are fixed to DAYS_BACK constant (currently 90 days)

    all_members = set()
    for team in teams:
        # Check for new format: members list with github/jira keys
        if 'members' in team and isinstance(team.get('members'), list):
            for member in team['members']:
                if isinstance(member, dict) and 'github' in member:
                    all_members.add(member['github'])
                elif isinstance(member, str):
                    # Old format where members is a simple list
                    all_members.add(member)
        # Fall back to old format: github.members
        else:
            all_members.update(team.get('github', {}).get('members', []))

    print(f"Collecting metrics for {len(all_members)} unique team members...")
    print(f"Time period: {date_range.description} ({start_date.date()} to {end_date.date()})")
    print()

    for username in all_members:
        print(f"  {username}...", end=" ")

        try:
            # Find team slugs for this user (supports both config formats)
            user_team_slugs = []
            for team in teams:
                is_member = False
                # Check new format: members list with github/jira keys
                if 'members' in team and isinstance(team.get('members'), list):
                    for member in team['members']:
                        if isinstance(member, dict) and member.get('github') == username:
                            is_member = True
                            break
                # Check old format: github.members
                elif username in team.get('github', {}).get('members', []):
                    is_member = True

                if is_member:
                    team_slug = team.get('github', {}).get('team_slug')
                    if team_slug:
                        user_team_slugs.append(team_slug)

            github_collector_person = GitHubGraphQLCollector(
                token=github_token,
                organization=config.github_organization,
                teams=user_team_slugs,
                team_members=[username],
                days_back=days_back
            )

            person_github_data = github_collector_person.collect_person_metrics(
                username=username,
                start_date=start_date,
                end_date=end_date
            )

            # Map GitHub username to Jira username
            jira_username = map_github_to_jira_username(username, teams)

            # Collect Jira data (if mapping exists and Jira is configured)
            person_jira_data = []
            jira_collection_failed = False
            if jira_username and jira_collector:
                # Try collecting with progressively simpler queries if timeouts occur
                try:
                    # First attempt: Full query with changelog
                    person_jira_data = jira_collector.collect_person_issues(
                        jira_username=jira_username,
                        days_back=days_back,
                        expand_changelog=True
                    )
                    print(f"GitHub: {len(person_github_data['pull_requests'])} PRs, {len(person_github_data['commits'])} commits | Jira: {len(person_jira_data)} issues")
                except Exception as e:
                    # Check if it's a timeout error (504 Gateway Timeout or 502 Bad Gateway)
                    if '504' in str(e) or '502' in str(e) or 'timeout' in str(e).lower():
                        print(f"  ⚠️ Jira query timeout, retrying without changelog expansion...")
                        try:
                            # Second attempt: Without changelog expansion (faster)
                            person_jira_data = jira_collector.collect_person_issues(
                                jira_username=jira_username,
                                days_back=days_back,
                                expand_changelog=False
                            )
                            print(f"GitHub: {len(person_github_data['pull_requests'])} PRs, {len(person_github_data['commits'])} commits | Jira: {len(person_jira_data)} issues (no changelog)")
                        except Exception as e2:
                            if '504' in str(e2) or '502' in str(e2) or 'timeout' in str(e2).lower():
                                print(f"  ⚠️ Still timing out, trying shorter time window (30 days)...")
                                try:
                                    # Third attempt: Shorter time window
                                    person_jira_data = jira_collector.collect_person_issues(
                                        jira_username=jira_username,
                                        days_back=30,
                                        expand_changelog=False
                                    )
                                    print(f"GitHub: {len(person_github_data['pull_requests'])} PRs, {len(person_github_data['commits'])} commits | Jira: {len(person_jira_data)} issues (last 30 days only)")
                                except Exception as e3:
                                    print(f"  ❌ All Jira retry attempts failed for {jira_username}: {e3}")
                                    jira_collection_failed = True
                            else:
                                print(f"  ❌ Could not fetch Jira data for {jira_username}: {e2}")
                                jira_collection_failed = True
                    else:
                        print(f"  ❌ Could not fetch Jira data for {jira_username}: {e}")
                        jira_collection_failed = True
            else:
                print(f"GitHub: {len(person_github_data['pull_requests'])} PRs, {len(person_github_data['commits'])} commits | Jira: skipped (no mapping)")

            # Calculate person metrics
            person_dfs = {
                'pull_requests': pd.DataFrame(person_github_data['pull_requests']),
                'reviews': pd.DataFrame(person_github_data['reviews']),
                'commits': pd.DataFrame(person_github_data['commits']),
            }

            calculator_person = MetricsCalculator(person_dfs)
            person_metrics[username] = calculator_person.calculate_person_metrics(
                username=username,
                github_data=person_github_data,
                jira_data=person_jira_data,  # ← Now passing Jira data!
                start_date=start_date,
                end_date=end_date
            )

            # Store raw data for on-demand filtering
            person_metrics[username]['raw_github_data'] = person_github_data
            person_metrics[username]['raw_jira_data'] = person_jira_data  # ← Store for later filtering

            # Mark if Jira collection failed (for dashboard warnings)
            person_metrics[username]['jira_collection_failed'] = jira_collection_failed

            # Show appropriate status indicator
            if jira_collection_failed:
                print(f"⚠️ (partial - Jira collection failed)")
            else:
                print(f"✅")
        except Exception as e:
            print(f"❌ ({e})")

    # Calculate team comparison
    print(f"\n🔢 Calculating team comparisons...")

    all_dfs = {
        'pull_requests': pd.DataFrame(all_github_data['pull_requests']),
        'reviews': pd.DataFrame(all_github_data['reviews']),
        'commits': pd.DataFrame(all_github_data['commits']),
        'deployments': pd.DataFrame(all_github_data['deployments']),
    }

    calculator_all = MetricsCalculator(all_dfs)
    team_comparison = calculator_all.calculate_team_comparison(team_metrics)

    # Build display name mapping
    member_names = build_member_name_mapping(teams)

    # Validate GitHub data before caching
    print("\n" + "=" * 70)
    print("Validating GitHub Collection")
    print("=" * 70)

    all_members = []
    for team in teams:
        # Extract GitHub members from team config (supports both new and old formats)
        if 'members' in team and isinstance(team.get('members'), list):
            # New format: unified members list
            for member in team['members']:
                if isinstance(member, dict) and member.get('github'):
                    all_members.append(member['github'])
        else:
            # Old format: separate arrays
            github_members = team.get('github', {}).get('members', [])
            all_members.extend(github_members)

    is_valid, validation_warnings, should_cache = validate_github_collection(
        all_github_data,
        all_members,
        github_collector.collection_status if hasattr(github_collector, 'collection_status') else {}
    )

    if validation_warnings:
        print()
        for warning in validation_warnings:
            print(warning)
        print()

    if not should_cache:
        print("❌ Data validation failed - NOT caching to prevent data loss!")
        print("   Previous cache remains intact.")
        print()
        print("Recommendations:")
        print("  1. Check GitHub API status: https://www.githubstatus.com/")
        print("  2. Verify your GitHub token has correct permissions")
        print("  3. Re-run collection after issues are resolved")
        print()
        exit(1)

    if not is_valid:
        print("⚠️  Data validation warnings detected. Caching anyway, but review logs.")
        print()

    # Backup current cache before overwriting
    if os.path.exists(cache_file):
        backup_file = f"{cache_file}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy(cache_file, backup_file)
        print(f"📦 Backed up previous cache to: {backup_file}")

    # Package everything
    cache_data = {
        'teams': team_metrics,
        'persons': person_metrics,
        'comparison': team_comparison,
        'member_names': member_names,  # GitHub username -> display name mapping
        'timestamp': datetime.now(),
        'date_range': {  # NEW: Store date range info
            'range_key': date_range.range_key,
            'description': date_range.description,
            'start_date': start_date,
            'end_date': end_date,
            'days': days_back
        },
        'collection_status': {
            'github': github_collector.collection_status if hasattr(github_collector, 'collection_status') else {},
            'validation_warnings': validation_warnings
        }
    }

# Save to cache file
os.makedirs('data', exist_ok=True)

with open(cache_file, 'wb') as f:
    pickle.dump(cache_data, f)

print()
print(f"✅ Metrics saved to {cache_file}")
print()
print("=" * 70)
print("Collection Complete!")
print("=" * 70)
print()
print("Now start the dashboard:")
print("  python -m src.dashboard.app")
print()
print("Then open: http://localhost:5000")
print()
