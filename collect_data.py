#!/usr/bin/env python3
"""Collect metrics data and save to cache file

Supports flexible date ranges: 30d, 90d, 365d, Q1-2025, 2024, or custom ranges.
Use --date-range argument to specify the time window.
"""

import argparse
import os
import pickle
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd

from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.config import Config
from src.models.metrics import MetricsCalculator
from src.utils.date_ranges import DateRangeError, get_cache_filename, parse_date_range
from src.utils.logging import get_logger, setup_logging

# Default time window (used if no --date-range provided)
DEFAULT_RANGE = "90d"


def validate_github_collection(github_data, team_members, collection_status):
    """Validate GitHub data before caching

    Returns:
        (is_valid, warnings, should_cache)
    """
    warnings = []

    # Check for collection errors
    failed_repos = collection_status.get("failed_repos", [])
    if failed_repos:
        warnings.append(f"{len(failed_repos)} repositories failed to collect")

    # Check for members with no data
    members_with_data = set()
    for pr in github_data.get("pull_requests", []):
        members_with_data.add(pr.get("author"))
    for commit in github_data.get("commits", []):
        members_with_data.add(commit.get("author"))

    missing_members = set(team_members) - members_with_data
    if missing_members:
        warnings.append(f"{len(missing_members)} members have no GitHub data: {', '.join(list(missing_members)[:5])}")

    # Check total data volume
    total_prs = len(github_data.get("pull_requests", []))
    total_commits = len(github_data.get("commits", []))

    if total_prs == 0 and total_commits == 0:
        warnings.append("CRITICAL: No GitHub data collected at all!")
        return False, warnings, False

    # Check against previous cache if available (use default cache name)
    default_cache = "data/" + get_cache_filename(DEFAULT_RANGE)
    if os.path.exists(default_cache):
        try:
            with open(default_cache, "rb") as f:
                prev_cache = pickle.load(f)

            prev_prs = sum(
                len(m.get("raw_github_data", {}).get("pull_requests", []))
                for m in prev_cache.get("persons", {}).values()
            )

            if total_prs < prev_prs * 0.5:  # 50% drop
                warnings.append(f"PR count dropped significantly: {prev_prs} → {total_prs}")
        except Exception:
            pass  # Can't load previous cache, skip comparison

    # Decide if we should cache
    should_cache = True
    if failed_repos and len(failed_repos) > len(collection_status.get("successful_repos", [])):
        # More failures than successes
        warnings.append("Too many failures - recommend re-running collection")
        should_cache = False

    return len(warnings) == 0, warnings, should_cache


def load_failed_repos_from_cache(cache_file):
    """Load list of failed repos from previous collection"""
    if not os.path.exists(cache_file):
        return []

    try:
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)

        github_status = cache.get("collection_status", {}).get("github", {})
        failed_repos = github_status.get("failed_repos", [])

        if failed_repos:
            out = get_logger("team_metrics.collection")
            out.section("Previous Collection Had Failures")
            out.info("")
            out.info(f"Found {len(failed_repos)} failed repositories from previous run:", emoji="📝")
            for failed in failed_repos[:10]:  # Show first 10
                out.info(f"- {failed['repo']}: {failed.get('error', 'Unknown error')[:60]}", indent=2)
            if len(failed_repos) > 10:
                out.info(f"... and {len(failed_repos) - 10} more", indent=2)
            out.info("")

        return failed_repos

    except Exception as e:
        out = get_logger("team_metrics.collection")
        out.warning(f"Could not load previous cache: {e}")
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
        if "members" in team and isinstance(team["members"], list):
            for member in team["members"]:
                if isinstance(member, dict):
                    if member.get("github") == github_username:
                        return member.get("jira")

        # Fall back to old format: parallel lists
        github_members = team.get("github", {}).get("members", [])
        jira_members = team.get("jira", {}).get("members", [])

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
        if "members" in team and isinstance(team["members"], list):
            for member in team["members"]:
                if isinstance(member, dict):
                    github = member.get("github")
                    name = member.get("name")
                    if github and name:
                        name_mapping[github] = name
                    elif github:
                        # Fallback: use GitHub username if no name provided
                        name_mapping[github] = github
        # Fall back to old format: github.members
        else:
            github_members = team.get("github", {}).get("members", [])
            for github in github_members:
                name_mapping[github] = github  # Use username as fallback

    return name_mapping


def collect_single_person(
    username: str,
    config: Config,
    teams: List[Dict],
    github_token: str,
    jira_collector: Optional[JiraCollector],
    start_date: datetime,
    end_date: datetime,
    days_back: int,
) -> tuple:
    """Collect metrics for a single person (for parallel execution)

    Args:
        username: GitHub username
        config: Config object
        teams: List of team configurations
        github_token: GitHub API token
        jira_collector: Jira collector instance (or None)
        start_date: Collection start date
        end_date: Collection end date
        days_back: Number of days to collect

    Returns:
        Tuple of (username, metrics_dict, error_message)
        - On success: (username, metrics, None)
        - On failure: (username, None, error_string)
    """
    try:
        # Find team slugs for this user (supports both config formats)
        user_team_slugs = []
        for team in teams:
            is_member = False
            # Check new format: members list with github/jira keys
            if "members" in team and isinstance(team.get("members"), list):
                for member in team["members"]:
                    if isinstance(member, dict) and member.get("github") == username:
                        is_member = True
                        break
            # Check old format: github.members
            elif username in team.get("github", {}).get("members", []):
                is_member = True

            if is_member:
                team_slug = team.get("github", {}).get("team_slug")
                if team_slug:
                    user_team_slugs.append(team_slug)

        github_collector_person = GitHubGraphQLCollector(
            token=github_token,
            organization=config.github_organization,
            teams=user_team_slugs,
            team_members=[username],
            days_back=days_back,
        )

        person_github_data = github_collector_person.collect_person_metrics(
            username=username, start_date=start_date, end_date=end_date
        )

        # Map GitHub username to Jira username
        jira_username = map_github_to_jira_username(username, teams)

        # Collect Jira data (if mapping exists and Jira is configured)
        person_jira_data = []
        jira_collection_failed = False
        jira_status = ""

        if jira_username and jira_collector:
            # Try collecting with progressively simpler queries if timeouts occur
            try:
                # First attempt: Full query with changelog
                person_jira_data = jira_collector.collect_person_issues(
                    jira_username=jira_username, days_back=days_back, expand_changelog=True
                )
                jira_status = f" | Jira: {len(person_jira_data)} issues"
            except Exception as e:
                # Check if it's a timeout error (504 Gateway Timeout or 502 Bad Gateway)
                if "504" in str(e) or "502" in str(e) or "timeout" in str(e).lower():
                    try:
                        # Second attempt: Without changelog expansion (faster)
                        person_jira_data = jira_collector.collect_person_issues(
                            jira_username=jira_username, days_back=days_back, expand_changelog=False
                        )
                        jira_status = f" | Jira: {len(person_jira_data)} issues (no changelog)"
                    except Exception as e2:
                        if "504" in str(e2) or "502" in str(e2) or "timeout" in str(e2).lower():
                            try:
                                # Third attempt: Shorter time window
                                person_jira_data = jira_collector.collect_person_issues(
                                    jira_username=jira_username, days_back=30, expand_changelog=False
                                )
                                jira_status = f" | Jira: {len(person_jira_data)} issues (last 30 days only)"
                            except Exception as e3:
                                jira_status = f" | Jira: failed - {e3}"
                                jira_collection_failed = True
                        else:
                            jira_status = f" | Jira: failed - {e2}"
                            jira_collection_failed = True
                else:
                    jira_status = f" | Jira: failed - {e}"
                    jira_collection_failed = True
        else:
            jira_status = " | Jira: skipped (no mapping)"

        # Calculate person metrics
        person_dfs = {
            "pull_requests": pd.DataFrame(person_github_data["pull_requests"]),
            "reviews": pd.DataFrame(person_github_data["reviews"]),
            "commits": pd.DataFrame(person_github_data["commits"]),
        }

        calculator_person = MetricsCalculator(person_dfs)
        metrics = calculator_person.calculate_person_metrics(
            username=username,
            github_data=person_github_data,
            jira_data=person_jira_data,
            start_date=start_date,
            end_date=end_date,
        )

        # Store raw data for on-demand filtering
        metrics["raw_github_data"] = person_github_data
        metrics["raw_jira_data"] = person_jira_data

        # Mark if Jira collection failed (for dashboard warnings)
        metrics["jira_collection_failed"] = jira_collection_failed

        # Build status string for logging
        status = f"GitHub: {len(person_github_data['pull_requests'])} PRs, {len(person_github_data['commits'])} commits{jira_status}"

        return (username, metrics, None, status, jira_collection_failed)

    except Exception as e:
        return (username, None, str(e), "", False)


def print_progress(current: int, total: int, item_name: str) -> None:
    """Print progress with timestamp

    Args:
        current: Number of completed items
        total: Total number of items
        item_name: Description of current item
    """
    out = get_logger("team_metrics.collection")
    out.progress(current, total, item_name)


def collect_single_team(
    team: Dict,
    config: Config,
    github_token: str,
    jira_config: Dict,
    jira_collector: Optional[JiraCollector],
    start_date: datetime,
    end_date: datetime,
    days_back: int,
) -> tuple:
    """Collect all metrics for a single team (for parallel execution)

    Args:
        team: Team configuration dict
        config: Config object
        github_token: GitHub API token
        jira_config: Jira configuration dict
        jira_collector: Shared Jira collector instance (or None)
        start_date: Collection start date
        end_date: Collection end date
        days_back: Number of days to collect

    Returns:
        Tuple of (team_name, metrics_dict, github_data_dict, error_message)
        - On success: (team_name, metrics, github_data, None)
        - On failure: (team_name, None, None, error_string)
    """
    try:
        team_name = team.get("name")
        team_display = team.get("display_name", team_name)

        # Extract members - support both new unified format and old format
        github_members = []
        jira_members = []

        if "members" in team and isinstance(team.get("members"), list):
            # New format: unified members list
            for member in team["members"]:
                if isinstance(member, dict):
                    if member.get("github"):
                        github_members.append(member["github"])
                    if member.get("jira"):
                        jira_members.append(member["jira"])
        else:
            # Old format: separate arrays
            github_members = team.get("github", {}).get("members", [])
            jira_members = team.get("jira", {}).get("members", [])

        filter_ids = team.get("jira", {}).get("filters", {})

        # Extract team_slug for GitHub team repositories
        team_slug = team.get("github", {}).get("team_slug")
        team_slugs = [team_slug] if team_slug else []

        # Collect GitHub metrics for team using GraphQL API
        parallel_cfg = config.parallel_config
        repo_workers = parallel_cfg.get("repo_workers", 5)

        github_collector = GitHubGraphQLCollector(
            token=github_token,
            organization=config.github_organization,
            teams=team_slugs,
            team_members=github_members,
            days_back=days_back,
            repo_workers=repo_workers,
        )

        team_github_data = github_collector.collect_all_metrics()

        # Collect Jira filter metrics for team
        jira_filter_results = {}
        if jira_collector and filter_ids:
            # Get parallel config
            parallel_cfg = config.parallel_config
            use_parallel = parallel_cfg.get("enabled", True)
            filter_workers = parallel_cfg.get("filter_workers", 4)

            jira_filter_results = jira_collector.collect_team_filters(
                filter_ids, parallel=use_parallel, max_workers=filter_workers
            )

        # Collect incidents for DORA metrics (CFR & MTTR)
        if jira_collector and filter_ids and "incidents" in filter_ids:
            incidents = jira_collector.collect_incidents(
                filter_id=filter_ids.get("incidents"), correlation_window_hours=24
            )
            jira_filter_results["incidents"] = incidents

        # Collect releases from Jira Fix Versions
        jira_releases = []
        if jira_collector:
            team_project_keys = team.get("jira", {}).get("project_keys", jira_collector.project_keys)

            # Create team-specific JiraCollector with team members for filtering
            team_jira_collector = JiraCollector(
                server=jira_config["server"],
                username=jira_config["username"],
                api_token=jira_config["api_token"],
                project_keys=team_project_keys,
                team_members=jira_members,
                days_back=days_back,
                verify_ssl=False,
                timeout=config.dashboard_config.get("jira_timeout_seconds", 120),
            )

            jira_releases = team_jira_collector.collect_releases_from_fix_versions(project_keys=team_project_keys)

        # Build mapping: issue key → fix version name (for lead time calculation)
        # If an issue has multiple Fix Versions, keep the earliest deployment
        issue_to_version_map = {}
        if jira_collector:
            # First, sort releases by published_at date (earliest first)
            sorted_releases = sorted(
                jira_releases, key=lambda r: r.get("published_at", "9999-12-31")  # Put releases without dates last
            )
            for release in sorted_releases:
                for issue_key in release.get("related_issues", []):
                    # Only add if not already mapped (earliest version wins)
                    if issue_key not in issue_to_version_map:
                        issue_to_version_map[issue_key] = release["tag_name"]

        # Convert to DataFrames for calculator
        team_dfs = {
            "pull_requests": pd.DataFrame(team_github_data["pull_requests"]),
            "reviews": pd.DataFrame(team_github_data["reviews"]),
            "commits": pd.DataFrame(team_github_data["commits"]),
            "deployments": pd.DataFrame(team_github_data["deployments"]),
            "releases": pd.DataFrame(jira_releases),
        }

        calculator = MetricsCalculator(team_dfs)
        metrics = calculator.calculate_team_metrics(
            team_name=team_name,
            team_config=team,
            jira_filter_results=jira_filter_results,
            issue_to_version_map=issue_to_version_map,
            dora_config=config.dora_config,
        )

        # Build status string
        status = f"PRs: {len(team_github_data['pull_requests'])}, Reviews: {len(team_github_data['reviews'])}, Releases: {len(jira_releases)}"

        return (team_name, metrics, team_github_data, None, status)

    except Exception as e:
        import traceback

        error_detail = f"{e}\n{traceback.format_exc()}"
        return (team.get("name", "Unknown"), None, None, error_detail, "")


# Parse command-line arguments
parser = argparse.ArgumentParser(
    description="Collect team metrics data from GitHub and Jira",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
  python collect_data.py                    # Use default 90-day window
  python collect_data.py --date-range 30d   # Last 30 days
  python collect_data.py --date-range Q1-2025  # Q1 2025
  python collect_data.py --date-range 2024  # Full year 2024
  python collect_data.py --date-range 2024-01-01:2024-03-31  # Custom range
  python collect_data.py -v                 # Verbose output
  python collect_data.py -q                 # Quiet mode (errors only)
    """,
)
parser.add_argument(
    "--date-range",
    type=str,
    default=DEFAULT_RANGE,
    help=f"Date range to collect (default: {DEFAULT_RANGE}). "
    "Formats: 30d, 90d, Q1-2025, 2024, YYYY-MM-DD:YYYY-MM-DD",
)
parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity: -v (INFO), -vv (DEBUG)")
parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (warnings and errors only)")
parser.add_argument("--log-file", type=str, help="Override log file location")

if __name__ == "__main__":
    args = parser.parse_args()

    # Determine log level from CLI flags
    if args.quiet:
        log_level = "WARNING"
    elif args.verbose >= 2:
        log_level = "DEBUG"
    elif args.verbose == 1:
        log_level = "INFO"
    else:
        log_level = "INFO"

    # Setup logging
    setup_logging(log_level=log_level, log_file=args.log_file, config_file="config/logging.yaml")
    out = get_logger("team_metrics.collection")

    # Parse the date range
    try:
        date_range = parse_date_range(args.date_range)
    except DateRangeError as e:
        out.error(f"Error: {e}")
        out.info("")
        out.info("Valid formats:")
        out.info("  - Days: 30d, 90d, 180d, 365d", indent=2)
        out.info("  - Quarters: Q1-2025, Q2-2024", indent=2)
        out.info("  - Years: 2024, 2025", indent=2)
        out.info("  - Custom: 2024-01-01:2024-12-31", indent=2)
        sys.exit(1)

    # Determine cache filename based on date range
    cache_filename = get_cache_filename(date_range.range_key)
    cache_file = os.path.join("data", cache_filename)

    out.section("Team Metrics Data Collection")

    # Check for resume opportunity
    failed_repos_prev = load_failed_repos_from_cache(cache_file)
    retry_mode = False

    if failed_repos_prev:
        try:
            response = input("Retry failed repositories only? (y/n): ").strip().lower()
            if response == "y":
                retry_mode = True
                out.info("Running in RETRY MODE - collecting previously failed repos", emoji="🔄")
                out.info("Note: This will merge with existing cache data.")
                out.info("")
        except (EOFError, KeyboardInterrupt):
            out.info("Continuing with full collection...")
            retry_mode = False

    # Use parsed date range
    start_date = date_range.start_date
    end_date = date_range.end_date
    days_back = date_range.days

    out.info(f"Date Range: {date_range.description}", emoji="📅")
    out.info(f"   From: {start_date.strftime('%Y-%m-%d')}", indent=2)
    out.info(f"   To:   {end_date.strftime('%Y-%m-%d')}", indent=2)
    out.info(f"   Days: {days_back}", indent=2)
    out.info(f"   Cache: {cache_filename}", indent=2)
    out.info("")

    config = Config()

    # Check if teams are configured
    teams = config.teams

    if not teams:
        out.warning("No teams configured. Using legacy collection mode...")
        out.info("")

        # Legacy collection (original behavior)
        # Note: Legacy GitHubCollector (REST API) is deprecated - this path shouldn't execute
        # Keeping for reference but may be removed in future versions
        out.warning("WARNING: Using deprecated legacy collection path")
        out.info("Please configure teams in config.yaml to use modern GraphQL collector", indent=2)
        out.info("")

        from src.collectors.github_collector import GitHubCollector

        github_collector = GitHubCollector(
            token=config.github_token,
            repositories=config.github_repositories if config.github_repositories else None,
            organization=config.github_organization,
            teams=config.github_teams,
            team_members=config.github_team_members,
            days_back=days_back,
        )

        dataframes = github_collector.get_dataframes()

        out.success("GitHub collection complete!")
        out.info(f"- Pull Requests: {len(dataframes['pull_requests'])}", indent=2)
        out.info(f"- Reviews: {len(dataframes['reviews'])}", indent=2)
        out.info(f"- Commits: {len(dataframes['commits'])}", indent=2)
        out.info("")

        # Collect Jira metrics
        jira_config = config.jira_config
        if jira_config.get("server") and jira_config.get("project_keys"):
            try:
                out.info("Collecting Jira metrics...", emoji="📊")
                jira_collector = JiraCollector(
                    server=jira_config["server"],
                    username=jira_config["username"],
                    api_token=jira_config["api_token"],
                    project_keys=jira_config["project_keys"],
                    team_members=config.jira_team_members,
                    days_back=days_back,
                    verify_ssl=False,
                    timeout=config.dashboard_config.get("jira_timeout_seconds", 120),
                )

                jira_dataframes = jira_collector.get_dataframes()
                dataframes["jira_issues"] = jira_dataframes["issues"]
                dataframes["jira_worklogs"] = jira_dataframes["worklogs"]

                out.success("Jira collection complete!")
                out.info(f"- Issues: {len(jira_dataframes['issues'])}", indent=2)
                out.info("")
            except Exception as e:
                out.warning(f"Jira collection failed: {e}")
                dataframes["jira_issues"] = pd.DataFrame()
                dataframes["jira_worklogs"] = pd.DataFrame()
        else:
            dataframes["jira_issues"] = pd.DataFrame()
            dataframes["jira_worklogs"] = pd.DataFrame()

        # Calculate metrics
        out.info("Calculating metrics...", emoji="🔢")
        calculator = MetricsCalculator(dataframes)
        metrics = calculator.get_all_metrics()

        # Save to cache
        cache_data = {"data": metrics, "timestamp": datetime.now()}

    else:
        # New team-based collection
        out.info(f"Collecting metrics for {len(teams)} team(s)...", emoji="📊")
        out.info("")

        # Initialize collectors
        github_token = config.github_token
        jira_config = config.jira_config

        if not github_token:
            out.error("Error: GitHub token not configured")
            exit(1)

        if not jira_config.get("server"):
            out.warning("Warning: Jira not configured. Jira metrics will be skipped.")
            jira_collector = None
        else:
            try:
                jira_collector = JiraCollector(
                    server=jira_config["server"],
                    username=jira_config["username"],
                    api_token=jira_config["api_token"],
                    project_keys=jira_config.get("project_keys", []),
                    days_back=days_back,
                    verify_ssl=False,
                    timeout=config.dashboard_config.get("jira_timeout_seconds", 120),
                )
                out.success("Connected to Jira")
            except Exception as e:
                out.warning(f"Could not connect to Jira: {e}")
                jira_collector = None

        # Collect data for each team
        team_metrics = {}
        all_github_data = {"pull_requests": [], "reviews": [], "commits": [], "deployments": [], "releases": []}

        # Get parallel collection config
        parallel_cfg = config.parallel_config
        use_parallel_teams = parallel_cfg.get("enabled", True) and len(teams) > 1
        team_workers = min(len(teams), parallel_cfg.get("team_workers", 3))

        if use_parallel_teams:
            out.info(f"Using parallel team collection ({team_workers} workers)", emoji="⚡")
            out.info("")

            # Parallel team collection
            with ThreadPoolExecutor(max_workers=team_workers) as executor:
                # Submit all team collection jobs
                futures = {
                    executor.submit(
                        collect_single_team,
                        team,
                        config,
                        github_token,
                        jira_config,
                        jira_collector,
                        start_date,
                        end_date,
                        days_back,
                    ): team.get("name")
                    for team in teams
                }

                # Collect results as they complete
                completed = 0
                total = len(teams)

                for future in as_completed(futures):
                    team_name = futures[future]
                    completed += 1

                    try:
                        result_team_name, metrics, github_data, error, status = future.result()

                        if error:
                            print_progress(completed, total, f"✗ {team_name} - Error occurred")
                            out.info(f"Error details: {error}", indent=2)
                        else:
                            team_metrics[team_name] = metrics

                            # Add to combined dataset
                            all_github_data["pull_requests"].extend(github_data["pull_requests"])
                            all_github_data["reviews"].extend(github_data["reviews"])
                            all_github_data["commits"].extend(github_data["commits"])
                            all_github_data["deployments"].extend(github_data["deployments"])

                            print_progress(completed, total, f"✓ {team_name} - {status}")

                    except Exception as e:
                        print_progress(completed, total, f"✗ {team_name} - {e}")

        else:
            # Sequential team collection (fallback or single team)
            out.info("Sequential team collection mode")
            out.info("")

            for team in teams:
                team_name = team.get("name")
                team_display = team.get("display_name", team_name)

                out.section(f"Team: {team_display}")

                try:
                    result_team_name, metrics, github_data, error, status = collect_single_team(
                        team, config, github_token, jira_config, jira_collector, start_date, end_date, days_back
                    )

                    if error:
                        out.error(f"Error: {error}")
                    else:
                        team_metrics[team_name] = metrics

                        # Add to combined dataset
                        all_github_data["pull_requests"].extend(github_data["pull_requests"])
                        all_github_data["reviews"].extend(github_data["reviews"])
                        all_github_data["commits"].extend(github_data["commits"])
                        all_github_data["deployments"].extend(github_data["deployments"])

                        out.success(f"{team_display} metrics complete - {status}")

                except Exception as e:
                    out.error(f"{team_display} failed: {e}")

        # Collect person-level metrics (same 90-day window as teams)
        out.info("")
        out.section("Collecting Person-Level Metrics")

        person_metrics = {}
        # Use same date range as team collection (already calculated above)
        # Person metrics are fixed to DAYS_BACK constant (currently 90 days)

        all_members = set()
        for team in teams:
            # Check for new format: members list with github/jira keys
            if "members" in team and isinstance(team.get("members"), list):
                for member in team["members"]:
                    if isinstance(member, dict) and "github" in member:
                        all_members.add(member["github"])
                    elif isinstance(member, str):
                        # Old format where members is a simple list
                        all_members.add(member)
            # Fall back to old format: github.members
            else:
                all_members.update(team.get("github", {}).get("members", []))

        out.info(f"Collecting metrics for {len(all_members)} unique team members...")
        out.info(f"Time period: {date_range.description} ({start_date.date()} to {end_date.date()})")
        out.info("")

        # Get parallel collection config
        parallel_cfg = config.parallel_config
        use_parallel = parallel_cfg.get("enabled", True) and len(all_members) > 1
        person_workers = parallel_cfg.get("person_workers", 8)

        if use_parallel:
            out.info(f"Using parallel collection ({person_workers} workers)", emoji="⚡")
            out.info("")

            # Parallel person collection
            with ThreadPoolExecutor(max_workers=person_workers) as executor:
                # Submit all person collection jobs
                futures = {
                    executor.submit(
                        collect_single_person,
                        username,
                        config,
                        teams,
                        github_token,
                        jira_collector,
                        start_date,
                        end_date,
                        days_back,
                    ): username
                    for username in all_members
                }

                # Collect results as they complete
                completed = 0
                total = len(all_members)

                for future in as_completed(futures):
                    username = futures[future]
                    completed += 1

                    try:
                        result_username, metrics, error, status, jira_failed = future.result()

                        if error:
                            print_progress(completed, total, f"✗ {username} - {error}")
                        else:
                            person_metrics[username] = metrics
                            # Determine status emoji
                            if jira_failed:
                                emoji = "⚠️"
                            else:
                                emoji = "✓"
                            print_progress(completed, total, f"{emoji} {username} - {status}")

                    except Exception as e:
                        print_progress(completed, total, f"✗ {username} - {e}")
        else:
            # Sequential person collection (fallback or single person)
            out.info("Sequential collection mode")
            out.info("")

            for username in all_members:
                try:
                    result_username, metrics, error, status, jira_failed = collect_single_person(
                        username, config, teams, github_token, jira_collector, start_date, end_date, days_back
                    )

                    if error:
                        out.error(f"{username} - {error}")
                    else:
                        person_metrics[username] = metrics
                        if jira_failed:
                            out.warning(f"{username} - {status} (partial - Jira collection failed)")
                        else:
                            out.success(f"{username} - {status}")
                except Exception as e:
                    out.error(f"{username} - {e}")

        # Calculate team comparison
        out.info("")
        out.info("Calculating team comparisons...", emoji="🔢")

        all_dfs = {
            "pull_requests": pd.DataFrame(all_github_data["pull_requests"]),
            "reviews": pd.DataFrame(all_github_data["reviews"]),
            "commits": pd.DataFrame(all_github_data["commits"]),
            "deployments": pd.DataFrame(all_github_data["deployments"]),
        }

        calculator_all = MetricsCalculator(all_dfs)
        team_comparison = calculator_all.calculate_team_comparison(team_metrics)

        # Build display name mapping
        member_names = build_member_name_mapping(teams)

        # Validate GitHub data before caching
        out.info("")
        out.section("Validating GitHub Collection")

        all_members = []
        for team in teams:
            # Extract GitHub members from team config (supports both new and old formats)
            if "members" in team and isinstance(team.get("members"), list):
                # New format: unified members list
                for member in team["members"]:
                    if isinstance(member, dict) and member.get("github"):
                        all_members.append(member["github"])
            else:
                # Old format: separate arrays
                github_members = team.get("github", {}).get("members", [])
                all_members.extend(github_members)

        is_valid, validation_warnings, should_cache = validate_github_collection(
            all_github_data, all_members, {}  # Collection status not available with parallel collection
        )

        if validation_warnings:
            out.info("")
            for warning in validation_warnings:
                if warning.startswith("CRITICAL"):
                    out.error(warning)
                elif "dropped significantly" in warning or "Too many failures" in warning:
                    out.warning(warning)
                else:
                    out.warning(warning)
            out.info("")

        if not should_cache:
            out.error("Data validation failed - NOT caching to prevent data loss!")
            out.info("Previous cache remains intact.", indent=2)
            out.info("")
            out.info("Recommendations:")
            out.info("1. Check GitHub API status: https://www.githubstatus.com/", indent=1)
            out.info("2. Verify your GitHub token has correct permissions", indent=1)
            out.info("3. Re-run collection after issues are resolved", indent=1)
            out.info("")
            exit(1)

        if not is_valid:
            out.warning("Data validation warnings detected. Caching anyway, but review logs.")
            out.info("")

        # Backup current cache before overwriting
        if os.path.exists(cache_file):
            backup_file = f"{cache_file}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copy(cache_file, backup_file)
            out.info(f"Backed up previous cache to: {backup_file}", emoji="📦")

        # Package everything
        cache_data = {
            "teams": team_metrics,
            "persons": person_metrics,
            "comparison": team_comparison,
            "member_names": member_names,  # GitHub username -> display name mapping
            "timestamp": datetime.now(),
            "date_range": {  # NEW: Store date range info
                "range_key": date_range.range_key,
                "description": date_range.description,
                "start_date": start_date,
                "end_date": end_date,
                "days": days_back,
            },
            "collection_status": {
                "github": {},  # Collection status not available with parallel collection
                "validation_warnings": validation_warnings,
            },
        }

    # Save to cache file
    os.makedirs("data", exist_ok=True)

    with open(cache_file, "wb") as f:
        pickle.dump(cache_data, f)

    out.info("")
    out.success(f"Metrics saved to {cache_file}")
    out.info("")
    out.section("Collection Complete!")
    out.info("")
    out.info("Now start the dashboard:")
    out.info("python -m src.dashboard.app", indent=1)
    out.info("")
    out.info("Then open: http://localhost:5001")
    out.info("")
