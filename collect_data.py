#!/usr/bin/env python3
"""Collect metrics data and save to cache file"""

import argparse
import pickle
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from src.config import Config
from src.collectors.github_collector import GitHubCollector
from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.models.metrics import MetricsCalculator
from src.utils.time_periods import get_last_n_days, get_current_year, parse_period_to_dates, format_period_label
import pandas as pd


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

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Collect team metrics data')
parser.add_argument('--period', default='90d', help='Time period (e.g., 90d, Q1-2025, H1-2026)')
parser.add_argument('--start-date', help='Start date (YYYY-MM-DD) - overrides period')
parser.add_argument('--end-date', help='End date (YYYY-MM-DD) - overrides period')
args = parser.parse_args()

print("=" * 70)
print("Team Metrics Data Collection")
print("=" * 70)
print()

# Determine date range
if args.start_date and args.end_date:
    # Use explicit dates
    start_date = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc)
    end_date = datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc)
    period_label = f"{args.start_date} to {args.end_date}"
    print(f"📅 Using custom date range: {period_label}")
else:
    # Use period
    start_date, end_date = parse_period_to_dates(args.period)
    period_label = format_period_label(args.period)
    print(f"📅 Using period: {period_label}")

print(f"   From: {start_date.strftime('%Y-%m-%d')}")
print(f"   To:   {end_date.strftime('%Y-%m-%d')}")
print()

# Calculate days_back from date range
days_back = (end_date - start_date).days

config = Config()

# Check if teams are configured
teams = config.teams

if not teams:
    print("⚠️  No teams configured. Using legacy collection mode...")
    print()

    # Legacy collection (original behavior)
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
        'deployments': []
    }

    for team in teams:
        team_name = team.get('name')
        team_display = team.get('display_name', team_name)

        print(f"\n{'='*70}")
        print(f"Team: {team_display}")
        print(f"{'='*70}")

        github_members = team.get('github', {}).get('members', [])
        jira_members = team.get('jira', {}).get('members', [])
        filter_ids = team.get('jira', {}).get('filters', {})

        print(f"GitHub members: {len(github_members)}")
        print(f"Jira members: {len(jira_members)}")

        # Collect GitHub metrics for team using GraphQL API
        print(f"\n📊 Collecting GitHub metrics for {team_display} (using GraphQL API)...")

        github_collector = GitHubGraphQLCollector(
            token=github_token,
            organization=config.github_organization,
            teams=[team.get('github', {}).get('team_slug')] if team.get('github', {}).get('team_slug') else [],
            team_members=github_members,
            days_back=days_back
        )

        team_github_data = github_collector.collect_all_metrics()

        # Add to combined dataset
        all_github_data['pull_requests'].extend(team_github_data['pull_requests'])
        all_github_data['reviews'].extend(team_github_data['reviews'])
        all_github_data['commits'].extend(team_github_data['commits'])
        all_github_data['deployments'].extend(team_github_data['deployments'])

        print(f"   - PRs: {len(team_github_data['pull_requests'])}")
        print(f"   - Reviews: {len(team_github_data['reviews'])}")
        print(f"   - Commits: {len(team_github_data['commits'])}")

        # Collect Jira filter metrics for team
        jira_filter_results = {}
        if jira_collector and filter_ids:
            print(f"\n📊 Collecting Jira filter metrics for {team_display}...")
            jira_filter_results = jira_collector.collect_team_filters(filter_ids)

        # Calculate team metrics
        print(f"\n🔢 Calculating team metrics for {team_display}...")

        # Convert to DataFrames for calculator
        team_dfs = {
            'pull_requests': pd.DataFrame(team_github_data['pull_requests']),
            'reviews': pd.DataFrame(team_github_data['reviews']),
            'commits': pd.DataFrame(team_github_data['commits']),
            'deployments': pd.DataFrame(team_github_data['deployments']),
        }

        calculator = MetricsCalculator(team_dfs)
        team_metrics[team_name] = calculator.calculate_team_metrics(
            team_name=team_name,
            team_config=team,
            jira_filter_results=jira_filter_results
        )

        print(f"✅ {team_display} metrics complete")

    # Collect person-level metrics for last 365 days
    print(f"\n{'='*70}")
    print("Collecting Person-Level Metrics")
    print(f"{'='*70}")

    person_metrics = {}
    # Collect last 365 days of data for person metrics (not current year)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=365)

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
    print(f"Time period: Last 365 days ({start_date.date()} to {end_date.date()})")
    print()

    for username in all_members:
        print(f"  {username}...", end=" ")

        try:
            github_collector_person = GitHubGraphQLCollector(
                token=github_token,
                organization=config.github_organization,
                teams=[team.get('github', {}).get('team_slug') for team in teams if username in team.get('github', {}).get('members', [])],
                team_members=[username],
                days_back=365  # Full year
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
            if jira_username and jira_collector:
                try:
                    person_jira_data = jira_collector.collect_person_issues(
                        jira_username=jira_username,
                        days_back=365
                    )
                    print(f"GitHub: {len(person_github_data['pull_requests'])} PRs, {len(person_github_data['commits'])} commits | Jira: {len(person_jira_data)} issues")
                except Exception as e:
                    print(f"⚠️ Could not fetch Jira data for {jira_username}: {e}")
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

    # Package everything
    cache_data = {
        'teams': team_metrics,
        'persons': person_metrics,
        'comparison': team_comparison,
        'timestamp': datetime.now()
    }

# Save to cache file
cache_file = 'data/metrics_cache.pkl'
import os
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
