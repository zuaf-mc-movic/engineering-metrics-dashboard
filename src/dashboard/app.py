import csv
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from flask import Flask, Response, jsonify, make_response, redirect, render_template, request

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd

from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.config import Config
from src.models.metrics import MetricsCalculator
from src.utils.date_ranges import get_cache_filename, get_preset_ranges
from src.utils.logging import get_logger

# Initialize logger
dashboard_logger = get_logger("team_metrics.dashboard")

app = Flask(__name__)


# Context processor to inject current year and date range info into all templates
@app.context_processor
def inject_template_globals() -> Dict[str, Any]:
    """Inject global template variables"""
    range_key = request.args.get("range", "90d")
    date_range_info: Dict[str, Any] = metrics_cache.get("date_range", {})

    # Get team list from cache or config
    teams = []
    cache_data = metrics_cache.get("data")
    if cache_data and "teams" in cache_data:
        teams = sorted(cache_data["teams"].keys())
    else:
        # Fallback to config
        config = get_config()
        teams = [team["name"] for team in config.teams]

    return {
        "current_year": datetime.now().year,
        "current_range": range_key,
        "available_ranges": get_available_ranges(),
        "date_range_info": date_range_info,
        "team_list": teams,
    }


def format_time_ago(timestamp: Optional[datetime]) -> str:
    """Convert timestamp to 'X hours ago' format

    Args:
        timestamp: datetime object

    Returns:
        str: Human-readable time ago string
    """
    if not timestamp:
        return "Unknown"

    now = datetime.now()
    delta = now - timestamp

    if delta.total_seconds() < 60:
        return "Just now"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(delta.total_seconds() / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"


# Register as Jinja filter
app.jinja_env.filters["time_ago"] = format_time_ago

# Global cache
metrics_cache: Dict[str, Any] = {"data": None, "timestamp": None}


def load_cache_from_file(range_key: str = "90d") -> bool:
    """Load cached metrics from file for a specific date range

    Args:
        range_key: Date range key (e.g., '90d', 'Q1-2025')

    Returns:
        bool: True if cache loaded successfully
    """
    import pickle
    from pathlib import Path

    cache_filename = get_cache_filename(range_key)
    cache_file = Path(__file__).parent.parent.parent / "data" / cache_filename

    if cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cache_data = pickle.load(f)
                # Handle both old format (cache_data['data']) and new format (direct structure)
                if "data" in cache_data:
                    metrics_cache["data"] = cache_data["data"]
                else:
                    # New format: teams, persons, comparison at top level
                    metrics_cache["data"] = cache_data
                metrics_cache["timestamp"] = cache_data.get("timestamp")
                metrics_cache["range_key"] = range_key
                metrics_cache["date_range"] = cache_data.get("date_range", {})
                dashboard_logger.info(f"Loaded cached metrics from {cache_file}")
                dashboard_logger.info(f"Cache timestamp: {metrics_cache['timestamp']}")
                if metrics_cache["date_range"]:
                    dashboard_logger.info(f"Date range: {metrics_cache['date_range'].get('description')}")
                return True
        except Exception as e:
            dashboard_logger.error(f"Failed to load cache: {e}")
            return False
    return False


def get_available_ranges() -> List[Tuple[str, str, bool]]:
    """Get list of available cached date ranges

    Returns:
        list: List of (range_key, description, file_exists) tuples
    """
    import pickle
    from pathlib import Path

    data_dir = Path(__file__).parent.parent.parent / "data"
    available = []

    # Check preset ranges
    for range_spec, description in get_preset_ranges():
        cache_file = data_dir / get_cache_filename(range_spec)
        if cache_file.exists():
            # Try to load date range info from cache
            try:
                with open(cache_file, "rb") as f:
                    cache_data = pickle.load(f)
                    if "date_range" in cache_data:
                        description = cache_data["date_range"].get("description", description)
            except:
                pass
            available.append((range_spec, description, True))

    # Check for other cached files (quarters, years, custom)
    if data_dir.exists():
        for cache_file in data_dir.glob("metrics_cache_*.pkl"):
            range_key = cache_file.stem.replace("metrics_cache_", "")
            if range_key not in [r[0] for r in available]:
                # Try to get description from cache
                try:
                    with open(cache_file, "rb") as f:
                        cache_data = pickle.load(f)
                        if "date_range" in cache_data:
                            description = cache_data["date_range"].get("description", range_key)
                        else:
                            description = range_key
                        available.append((range_key, description, True))
                except:
                    available.append((range_key, range_key, True))

    return available


# Try to load default cache on startup (90d)
load_cache_from_file("90d")


def get_config() -> Config:
    """Load configuration"""
    return Config()


def get_display_name(username: str, member_names: Optional[Dict[str, str]] = None) -> str:
    """Get display name for a GitHub username, fallback to username."""
    if member_names and username in member_names:
        return member_names[username]
    return username


def filter_github_data_by_date(raw_data: Dict, start_date: datetime, end_date: datetime) -> Dict:
    """Filter GitHub raw data by date range"""
    filtered = {}

    # Filter PRs
    if "pull_requests" in raw_data and raw_data["pull_requests"]:
        prs_df = pd.DataFrame(raw_data["pull_requests"])
        if "created_at" in prs_df.columns:
            prs_df["created_at"] = pd.to_datetime(prs_df["created_at"])
            mask = (prs_df["created_at"] >= start_date) & (prs_df["created_at"] <= end_date)
            filtered["pull_requests"] = prs_df[mask].to_dict("records")
        else:
            filtered["pull_requests"] = raw_data["pull_requests"]
    else:
        filtered["pull_requests"] = []

    # Filter reviews
    if "reviews" in raw_data and raw_data["reviews"]:
        reviews_df = pd.DataFrame(raw_data["reviews"])
        if "submitted_at" in reviews_df.columns:
            reviews_df["submitted_at"] = pd.to_datetime(reviews_df["submitted_at"])
            mask = (reviews_df["submitted_at"] >= start_date) & (reviews_df["submitted_at"] <= end_date)
            filtered["reviews"] = reviews_df[mask].to_dict("records")
        else:
            filtered["reviews"] = raw_data["reviews"]
    else:
        filtered["reviews"] = []

    # Filter commits
    if "commits" in raw_data and raw_data["commits"]:
        commits_df = pd.DataFrame(raw_data["commits"])
        # Check for both 'date' and 'committed_date' field names
        date_field = "date" if "date" in commits_df.columns else "committed_date"
        if date_field in commits_df.columns:
            commits_df["commit_date"] = pd.to_datetime(commits_df[date_field], utc=True)
            mask = (commits_df["commit_date"] >= start_date) & (commits_df["commit_date"] <= end_date)
            filtered["commits"] = commits_df[mask].to_dict("records")
        else:
            filtered["commits"] = raw_data["commits"]
    else:
        filtered["commits"] = []

    return filtered


def filter_jira_data_by_date(issues: List, start_date: datetime, end_date: datetime) -> List:
    """Filter Jira issues by date range

    Args:
        issues: List of Jira issue dictionaries
        start_date: Start date for filtering
        end_date: End date for filtering

    Returns:
        List of filtered issue dictionaries
    """
    if not issues:
        return []

    issues_df = pd.DataFrame(issues)

    # Convert date fields to datetime
    if "created" in issues_df.columns:
        issues_df["created"] = pd.to_datetime(issues_df["created"], utc=True)
    if "resolved" in issues_df.columns:
        issues_df["resolved"] = pd.to_datetime(issues_df["resolved"], utc=True)
    if "updated" in issues_df.columns:
        issues_df["updated"] = pd.to_datetime(issues_df["updated"], utc=True)

    # Include issue if ANY of these conditions are true:
    # - Created in period
    # - Resolved in period
    # - Updated in period (for WIP items)
    mask = pd.Series([False] * len(issues_df))

    if "created" in issues_df.columns:
        created_mask = (issues_df["created"] >= start_date) & (issues_df["created"] <= end_date)
        mask |= created_mask

    if "resolved" in issues_df.columns:
        resolved_mask = (
            issues_df["resolved"].notna() & (issues_df["resolved"] >= start_date) & (issues_df["resolved"] <= end_date)
        )
        mask |= resolved_mask

    if "updated" in issues_df.columns:
        updated_mask = (issues_df["updated"] >= start_date) & (issues_df["updated"] <= end_date)
        mask |= updated_mask

    return cast(List[Any], issues_df[mask].to_dict("records"))


def should_refresh_cache(cache_duration_minutes: int = 60) -> bool:
    """Check if cache should be refreshed"""
    if metrics_cache["timestamp"] is None:
        return True

    elapsed = (datetime.now() - metrics_cache["timestamp"]).total_seconds() / 60
    return bool(elapsed > cache_duration_minutes)


def refresh_metrics() -> Optional[Dict]:
    """Collect and calculate metrics using GraphQL API"""
    config = get_config()
    teams = config.teams

    if not teams:
        dashboard_logger.warning("No teams configured. Please configure teams in config.yaml")
        return None

    dashboard_logger.info(f"Refreshing metrics for {len(teams)} team(s) using GraphQL API...", emoji="🔄")

    # Connect to Jira
    jira_config = config.jira_config
    jira_collector = None

    if jira_config.get("server"):
        try:
            jira_collector = JiraCollector(
                server=jira_config["server"],
                username=jira_config["username"],
                api_token=jira_config["api_token"],
                project_keys=jira_config.get("project_keys", []),
                days_back=config.days_back,
                verify_ssl=False,
                timeout=config.dashboard_config.get("jira_timeout_seconds", 120),
            )
            dashboard_logger.success("Connected to Jira")
        except Exception as e:
            dashboard_logger.warning(f"Could not connect to Jira: {e}")

    # Collect data for each team
    team_metrics = {}
    all_github_data: Dict[str, List] = {"pull_requests": [], "reviews": [], "commits": [], "deployments": []}

    for team in teams:
        team_name = team.get("name")
        dashboard_logger.info("")
        dashboard_logger.info(f"Collecting {team_name} Team...", emoji="📊")

        github_members = team.get("github", {}).get("members", [])
        filter_ids = team.get("jira", {}).get("filters", {})

        # Collect GitHub metrics using GraphQL
        github_collector = GitHubGraphQLCollector(
            token=config.github_token,
            organization=config.github_organization,
            teams=[team.get("github", {}).get("team_slug")] if team.get("github", {}).get("team_slug") else [],
            team_members=github_members,
            days_back=config.days_back,
        )

        team_github_data = github_collector.collect_all_metrics()

        all_github_data["pull_requests"].extend(team_github_data["pull_requests"])
        all_github_data["reviews"].extend(team_github_data["reviews"])
        all_github_data["commits"].extend(team_github_data["commits"])

        dashboard_logger.info(f"- PRs: {len(team_github_data['pull_requests'])}", indent=1)
        dashboard_logger.info(f"- Reviews: {len(team_github_data['reviews'])}", indent=1)
        dashboard_logger.info(f"- Commits: {len(team_github_data['commits'])}", indent=1)

        # Collect Jira filter metrics
        jira_filter_results = {}
        if jira_collector and filter_ids:
            dashboard_logger.info(f"Collecting Jira filters for {team_name}...", emoji="📊")
            jira_filter_results = jira_collector.collect_team_filters(filter_ids)

        # Calculate team metrics
        team_dfs = {
            "pull_requests": pd.DataFrame(team_github_data["pull_requests"]),
            "reviews": pd.DataFrame(team_github_data["reviews"]),
            "commits": pd.DataFrame(team_github_data["commits"]),
            "deployments": pd.DataFrame(team_github_data["deployments"]),
        }

        calculator = MetricsCalculator(team_dfs)
        team_metrics[team_name] = calculator.calculate_team_metrics(
            team_name=team_name, team_config=team, jira_filter_results=jira_filter_results
        )

    # Calculate team comparison
    all_dfs = {
        "pull_requests": pd.DataFrame(all_github_data["pull_requests"]),
        "reviews": pd.DataFrame(all_github_data["reviews"]),
        "commits": pd.DataFrame(all_github_data["commits"]),
        "deployments": pd.DataFrame(all_github_data["deployments"]),
    }

    calculator_all = MetricsCalculator(all_dfs)
    team_comparison = calculator_all.calculate_team_comparison(team_metrics)

    # Package data
    cache_data = {"teams": team_metrics, "comparison": team_comparison, "timestamp": datetime.now()}

    metrics_cache["data"] = cache_data
    metrics_cache["timestamp"] = datetime.now()

    dashboard_logger.info("")
    dashboard_logger.success(f"Metrics refreshed at {metrics_cache['timestamp']}")

    return cache_data


@app.route("/")
def index() -> str:
    """Main dashboard page - shows team overview"""
    config = get_config()

    # Get requested date range from query parameter (default: 90d)
    range_key = request.args.get("range", "90d")

    # Load cache for requested range (if not already loaded)
    if metrics_cache.get("range_key") != range_key:
        load_cache_from_file(range_key)

    # If no cache exists, show loading page
    if metrics_cache["data"] is None:
        available_ranges = get_available_ranges()
        return render_template("loading.html", available_ranges=available_ranges, selected_range=range_key)

    cache = metrics_cache["data"]

    # Get available ranges for selector
    available_ranges = get_available_ranges()
    date_range_info = metrics_cache.get("date_range", {})

    # Check if we have the new team-based structure
    if "teams" in cache:
        # New structure - show team overview
        teams = config.teams
        team_list = []

        for team in teams:
            team_name = team.get("name")
            team_data = cache["teams"].get(team_name, {})
            github_metrics = team_data.get("github", {})
            jira_metrics = team_data.get("jira", {})

            dora_metrics = team_data.get("dora", {})

            team_list.append(
                {
                    "name": team_name,
                    "display_name": team.get("display_name", team_name),
                    "pr_count": github_metrics.get("pr_count", 0),
                    "review_count": github_metrics.get("review_count", 0),
                    "commit_count": github_metrics.get("commit_count", 0),
                    "avg_cycle_time": github_metrics.get("avg_cycle_time", 0),
                    "throughput": (
                        jira_metrics.get("throughput", {}).get("weekly_avg", 0) if jira_metrics.get("throughput") else 0
                    ),
                    "wip_count": jira_metrics.get("wip", {}).get("count", 0) if jira_metrics.get("wip") else 0,
                    "dora": dora_metrics,
                }
            )

        return render_template(
            "teams_overview.html",
            teams=team_list,
            cache=cache,
            config=config,
            updated_at=metrics_cache["timestamp"],
            available_ranges=available_ranges,
            selected_range=range_key,
            date_range_info=date_range_info,
        )
    else:
        # Legacy structure - use old dashboard
        return render_template(
            "dashboard.html",
            metrics=cache,
            updated_at=metrics_cache["timestamp"],
            available_ranges=available_ranges,
            selected_range=range_key,
            date_range_info=date_range_info,
        )


@app.route("/api/metrics")
def api_metrics() -> Union[Response, Tuple[Response, int]]:
    """API endpoint for metrics data"""
    config = get_config()

    if should_refresh_cache(config.dashboard_config.get("cache_duration_minutes", 60)):
        try:
            refresh_metrics()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify(metrics_cache["data"])


@app.route("/api/refresh")
def api_refresh() -> Union[Response, Tuple[Response, int]]:
    """Force refresh metrics"""
    try:
        metrics = refresh_metrics()
        return jsonify({"status": "success", "metrics": metrics})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/reload-cache", methods=["POST"])
def api_reload_cache() -> Union[Response, Tuple[Response, int]]:
    """Reload metrics cache from disk without restarting server"""
    try:
        success = load_cache_from_file()
        if success:
            return jsonify(
                {
                    "status": "success",
                    "message": "Cache reloaded successfully",
                    "timestamp": str(metrics_cache["timestamp"]),
                }
            )
        else:
            return (
                jsonify({"status": "error", "message": "Failed to reload cache - file may not exist or be corrupted"}),
                500,
            )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/collect")
def collect() -> Any:
    """Trigger collection and redirect to dashboard"""
    try:
        refresh_metrics()
        return redirect("/")
    except Exception as e:
        return render_template("error.html", error=str(e))


@app.route("/team/<team_name>")
def team_dashboard(team_name: str) -> str:
    """Team-specific dashboard"""
    config = get_config()

    # Get requested date range from query parameter (default: 90d)
    range_key = request.args.get("range", "90d")

    # Load cache for requested range (if not already loaded)
    if metrics_cache.get("range_key") != range_key:
        load_cache_from_file(range_key)

    if metrics_cache["data"] is None:
        return render_template("loading.html")

    # Check if this is new team-based cache structure
    cache = metrics_cache["data"]

    if "teams" in cache:
        # New structure
        team_data = cache["teams"].get(team_name)

        if not team_data:
            return render_template("error.html", error=f"Team '{team_name}' not found")

        team_config = config.get_team_by_name(team_name)

        # Calculate date range for GitHub search links
        start_date = (datetime.now() - timedelta(days=config.days_back)).strftime("%Y-%m-%d")

        # Get member names mapping
        member_names = cache.get("member_names", {})

        # Add Jira data and update GitHub metrics from persons cache
        # (person data is more accurate as it includes cross-team contributions)
        if "persons" in cache and "github" in team_data and "member_trends" in team_data["github"]:
            member_trends = team_data["github"]["member_trends"]
            for member in member_trends:
                if member in cache["persons"]:
                    person_data = cache["persons"][member]

                    # Update GitHub metrics with person-level data (more comprehensive)
                    if "github" in person_data:
                        github_data = person_data["github"]
                        member_trends[member]["prs"] = github_data.get("prs_created", member_trends[member]["prs"])
                        member_trends[member]["reviews"] = github_data.get(
                            "reviews_given", member_trends[member]["reviews"]
                        )
                        member_trends[member]["commits"] = github_data.get("commits", member_trends[member]["commits"])
                        member_trends[member]["lines_added"] = github_data.get(
                            "lines_added", member_trends[member]["lines_added"]
                        )
                        member_trends[member]["lines_deleted"] = github_data.get(
                            "lines_deleted", member_trends[member]["lines_deleted"]
                        )

                    # Add Jira metrics
                    if "jira" in person_data:
                        member_trends[member]["jira"] = {
                            "completed": person_data["jira"].get("completed", 0),
                            "in_progress": person_data["jira"].get("in_progress", 0),
                            "avg_cycle_time": person_data["jira"].get("avg_cycle_time", 0),
                        }

        return render_template(
            "team_dashboard.html",
            team_name=team_name,
            team_display_name=team_config.get("display_name", team_name) if team_config else team_name,
            team_data=team_data,
            team_config=team_config,
            member_names=member_names,
            config=config,
            days_back=config.days_back,
            start_date=start_date,
            jira_server=config.jira_config.get("server", "https://jira.ops.expertcity.com"),
            github_org=config.github_organization,
            github_base_url=config.github_base_url,
            updated_at=metrics_cache["timestamp"],
        )
    else:
        # Legacy structure - show error
        return render_template(
            "error.html",
            error="Team dashboards require team configuration. Please update config.yaml and re-run data collection.",
        )


@app.route("/person/<username>")
def person_dashboard(username: str) -> str:
    """Person-specific dashboard"""
    config = get_config()

    # Get requested date range from query parameter (default: 90d)
    range_key = request.args.get("range", "90d")

    # Load cache for requested range (if not already loaded)
    if metrics_cache.get("range_key") != range_key:
        load_cache_from_file(range_key)

    if metrics_cache["data"] is None:
        return render_template("loading.html")

    cache = metrics_cache["data"]

    if "persons" not in cache:
        return render_template(
            "error.html",
            error="Person dashboards require team configuration. Please update config.yaml and re-run data collection.",
        )

    # Get cached person data (already contains 90-day metrics)
    person_data = cache["persons"].get(username)
    if not person_data:
        return render_template("error.html", error=f"No metrics found for user '{username}'")

    # Calculate trends from raw data if available
    if "raw_github_data" in person_data and person_data.get("raw_github_data"):
        person_dfs = {
            "pull_requests": pd.DataFrame(person_data["raw_github_data"].get("pull_requests", [])),
            "reviews": pd.DataFrame(person_data["raw_github_data"].get("reviews", [])),
            "commits": pd.DataFrame(person_data["raw_github_data"].get("commits", [])),
        }

        calculator = MetricsCalculator(person_dfs)
        person_data["trends"] = calculator.calculate_person_trends(person_data["raw_github_data"], period="weekly")
    else:
        # No raw data available, set empty trends
        person_data["trends"] = {"pr_trend": [], "review_trend": [], "commit_trend": [], "lines_changed_trend": []}

    # Get display name from cache
    member_names = cache.get("member_names", {})
    display_name = get_display_name(username, member_names)

    # Find which team this person belongs to
    team_name = None
    for team in config.teams:
        # Check new format: members list with github/jira keys
        if "members" in team:
            for member in team.get("members", []):
                if isinstance(member, dict) and member.get("github") == username:
                    team_name = team.get("name")
                    break
        # Check old format: github.members
        elif username in team.get("github", {}).get("members", []):
            team_name = team.get("name")
            break
        if team_name:
            break

    return render_template(
        "person_dashboard.html",
        username=username,
        display_name=display_name,
        person_data=person_data,
        team_name=team_name,
        github_org=config.github_organization,
        github_base_url=config.github_base_url,
        updated_at=metrics_cache["timestamp"],
    )


@app.route("/team/<team_name>/compare")
def team_members_comparison(team_name: str) -> str:
    """Compare all team members side-by-side"""
    config = get_config()

    # Get requested date range from query parameter (default: 90d)
    range_key = request.args.get("range", "90d")

    # Load cache for requested range (if not already loaded)
    if metrics_cache.get("range_key") != range_key:
        load_cache_from_file(range_key)

    if metrics_cache["data"] is None:
        return render_template("loading.html")

    cache = metrics_cache["data"]
    team_data = cache.get("teams", {}).get(team_name)
    team_config = config.get_team_by_name(team_name)

    if not team_data:
        return render_template("error.html", error=f"Team '{team_name}' not found")

    if not team_config:
        return render_template("error.html", error=f"Team configuration for '{team_name}' not found")

    # Get all members from team config - support both formats
    members = []
    if "members" in team_config and isinstance(team_config.get("members"), list):
        # New format: unified members list
        members = [m.get("github") for m in team_config["members"] if isinstance(m, dict) and m.get("github")]
    else:
        # Old format: github.members
        members = team_config.get("github", {}).get("members", [])

    # Get member names mapping
    member_names = cache.get("member_names", {})

    # Build comparison data
    comparison_data = []
    for username in members:
        person_data = cache.get("persons", {}).get(username, {})
        github_data = person_data.get("github", {})
        jira_data = person_data.get("jira", {})

        comparison_data.append(
            {
                "username": username,
                "display_name": get_display_name(str(username), member_names),
                "prs": github_data.get("prs_created", 0),
                "prs_merged": github_data.get("prs_merged", 0),
                "merge_rate": github_data.get("merge_rate", 0) * 100,
                "reviews": github_data.get("reviews_given", 0),
                "commits": github_data.get("commits", 0),
                "lines_added": github_data.get("lines_added", 0),
                "lines_deleted": github_data.get("lines_deleted", 0),
                "cycle_time": github_data.get("avg_pr_cycle_time", 0),
                # Jira metrics
                "jira_completed": jira_data.get("completed", 0),
                "jira_wip": jira_data.get("in_progress", 0),
                "jira_cycle_time": jira_data.get("avg_cycle_time", 0),
            }
        )

    # Calculate performance scores for each member
    for member in comparison_data:
        member["score"] = MetricsCalculator.calculate_performance_score(member, comparison_data)

    # Sort by score descending
    comparison_data.sort(key=lambda x: x["score"], reverse=True)

    # Add rank and badges
    for i, member in enumerate(comparison_data, 1):
        member["rank"] = i
        if i == 1:
            member["badge"] = "🥇"
        elif i == 2:
            member["badge"] = "🥈"
        elif i == 3:
            member["badge"] = "🥉"
        else:
            member["badge"] = ""

    return render_template(
        "team_members_comparison.html",
        team_name=team_name,
        team_display_name=team_config.get("display_name", team_name),
        comparison_data=comparison_data,
        config=config,
        github_org=config.github_organization,
        updated_at=metrics_cache["timestamp"],
    )


@app.route("/documentation")
def documentation() -> str:
    """Documentation and FAQ page"""
    return render_template("documentation.html")


@app.route("/comparison")
def team_comparison() -> str:
    """Side-by-side team comparison"""
    config = get_config()

    # Get requested date range from query parameter (default: 90d)
    range_key = request.args.get("range", "90d")

    # Load cache for requested range (if not already loaded)
    if metrics_cache.get("range_key") != range_key:
        load_cache_from_file(range_key)

    if metrics_cache["data"] is None:
        return render_template("loading.html")

    cache = metrics_cache["data"]

    if "comparison" not in cache:
        return render_template("error.html", error="Team comparison requires team configuration.")

    # Build team_configs dict for easy lookup in template
    team_configs = {team["name"]: team for team in config.teams}

    # Calculate date range for GitHub search links
    start_date = (datetime.now() - timedelta(days=config.days_back)).strftime("%Y-%m-%d")

    # Calculate performance scores for teams
    comparison_data = cache["comparison"]
    team_metrics_list = list(comparison_data.values())

    # Add team sizes and calculate scores with normalization
    for team_name, metrics in comparison_data.items():
        team_config = team_configs[team_name]
        # Get team size - support both formats
        if "members" in team_config and isinstance(team_config.get("members"), list):
            # New format: count members with github field
            team_size = len([m for m in team_config["members"] if isinstance(m, dict) and m.get("github")])
        else:
            # Old format: github.members
            team_size = len(team_config.get("github", {}).get("members", []))
        metrics["team_size"] = team_size

        # Prepare metrics for performance score - map DORA keys
        score_metrics = {
            "prs": metrics.get("prs", 0),
            "reviews": metrics.get("reviews", 0),
            "commits": metrics.get("commits", 0),
            "cycle_time": metrics.get("avg_cycle_time", 0),
            "jira_completed": metrics.get("jira_throughput", 0),
            "merge_rate": metrics.get("merge_rate", 0),
            "team_size": team_size,
            # Map DORA metrics from cache keys to performance score keys
            "deployment_frequency": metrics.get("dora_deployment_freq"),
            "lead_time": metrics.get("dora_lead_time"),
            "change_failure_rate": metrics.get("dora_cfr"),
            "mttr": metrics.get("dora_mttr"),
        }

        # Prepare all metrics list with same mapping
        all_metrics_mapped = []
        for tm in team_metrics_list:
            all_metrics_mapped.append(
                {
                    "prs": tm.get("prs", 0),
                    "reviews": tm.get("reviews", 0),
                    "commits": tm.get("commits", 0),
                    "cycle_time": tm.get("avg_cycle_time", 0),
                    "jira_completed": tm.get("jira_throughput", 0),
                    "merge_rate": tm.get("merge_rate", 0),
                    "team_size": tm.get("team_size", 1),
                    "deployment_frequency": tm.get("dora_deployment_freq"),
                    "lead_time": tm.get("dora_lead_time"),
                    "change_failure_rate": tm.get("dora_cfr"),
                    "mttr": tm.get("dora_mttr"),
                }
            )

        metrics["score"] = MetricsCalculator.calculate_performance_score(
            score_metrics, all_metrics_mapped, team_size=team_size  # Normalize by team size
        )

    # Count wins for each team (who has the highest value in each metric)
    team_wins: Dict[str, int] = {}
    # Higher is better metrics
    metrics_to_compare = ["prs", "reviews", "commits", "jira_throughput", "dora_deployment_freq"]

    for metric in metrics_to_compare:
        max_value = max([m.get(metric, 0) for m in comparison_data.values() if m.get(metric) is not None])
        if max_value > 0:
            for team_name, metrics in comparison_data.items():
                if metrics.get(metric, 0) == max_value:
                    team_wins[team_name] = team_wins.get(team_name, 0) + 1

    # Lower is better metrics: cycle time, lead time, CFR, MTTR
    lower_is_better = {
        "avg_cycle_time": "avg_cycle_time",
        "dora_lead_time": "dora_lead_time",
        "dora_cfr": "dora_cfr",
        "dora_mttr": "dora_mttr",
    }

    for metric_key in lower_is_better.keys():
        metric_values = {
            team: m.get(metric_key, 0)
            for team, m in comparison_data.items()
            if m.get(metric_key) is not None and m.get(metric_key) > 0
        }
        if metric_values:
            min_value = min(metric_values.values())
            for team_name, value in metric_values.items():
                if value == min_value:
                    team_wins[team_name] = team_wins.get(team_name, 0) + 1

    return render_template(
        "comparison.html",
        comparison=comparison_data,
        teams=cache.get("teams", {}),
        team_configs=team_configs,
        team_wins=team_wins,
        config=config,
        github_org=config.github_organization,
        jira_server=config.jira_config.get("server"),
        start_date=start_date,
        days_back=config.days_back,
        updated_at=metrics_cache["timestamp"],
    )


@app.route("/settings")
def settings() -> str:
    """Render performance score settings page"""
    config = get_config()
    current_weights = config.performance_weights

    # Convert to percentages for display
    weights_pct = {k: v * 100 for k, v in current_weights.items()}

    metric_descriptions = {
        "prs": "Pull requests created",
        "reviews": "Code reviews given",
        "commits": "Commits made",
        "cycle_time": "PR cycle time (lower is better)",
        "jira_completed": "Jira issues completed",
        "merge_rate": "PR merge rate",
    }

    metric_labels = {
        "prs": "Pull Requests",
        "reviews": "Code Reviews",
        "commits": "Commits",
        "cycle_time": "Cycle Time",
        "jira_completed": "Jira Completed",
        "merge_rate": "Merge Rate",
    }

    return render_template(
        "settings.html",
        weights=weights_pct,
        metric_descriptions=metric_descriptions,
        metric_labels=metric_labels,
        config=config,
    )


@app.route("/settings/save", methods=["POST"])
def save_settings() -> Union[Response, Tuple[Response, int]]:
    """Save updated performance weights"""
    try:
        # Parse JSON data
        data = request.get_json()

        # Extract weights (in percentages)
        weights_pct = {
            "prs": float(data.get("prs", 20)),
            "reviews": float(data.get("reviews", 20)),
            "commits": float(data.get("commits", 15)),
            "cycle_time": float(data.get("cycle_time", 15)),
            "jira_completed": float(data.get("jira_completed", 20)),
            "merge_rate": float(data.get("merge_rate", 10)),
        }

        # Validate sum
        total = sum(weights_pct.values())
        if not (99.9 <= total <= 100.1):
            return jsonify({"success": False, "error": f"Weights must sum to 100%, got {total:.1f}%"}), 400

        # Convert to decimals
        weights = {k: v / 100 for k, v in weights_pct.items()}

        # Save to config
        config = get_config()
        config.update_performance_weights(weights)

        return jsonify({"success": True, "message": "Settings saved successfully"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/settings/reset", methods=["POST"])
def reset_settings() -> Union[Response, Tuple[Response, int]]:
    """Reset weights to defaults"""
    try:
        default_weights = {
            "prs": 0.20,
            "reviews": 0.20,
            "commits": 0.15,
            "cycle_time": 0.15,
            "jira_completed": 0.20,
            "merge_rate": 0.10,
        }

        config = get_config()
        config.update_performance_weights(default_weights)

        return jsonify({"success": True, "message": "Settings reset to defaults"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# Export Helper Functions
# ============================================================================


def flatten_dict(d: Dict, parent_key: str = "", sep: str = ".") -> Dict:
    """Flatten nested dictionary with dot notation

    Args:
        d: Dictionary to flatten
        parent_key: Parent key for recursion
        sep: Separator for nested keys

    Returns:
        Flattened dictionary
    """
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Convert lists to comma-separated strings
            items.append((new_key, ", ".join(str(x) for x in v)))
        else:
            items.append((new_key, v))
    return dict(items)


def format_value_for_csv(value: Any) -> Union[str, int, float]:
    """Format value for CSV export"""
    if isinstance(value, (int, float)):
        return round(value, 2) if isinstance(value, float) else value
    elif isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    elif value is None:
        return ""
    else:
        return str(value)


def create_csv_response(data: List[Dict], filename: str) -> Response:
    """Create CSV response from data

    Args:
        data: List of dictionaries or single dictionary
        filename: Filename for download

    Returns:
        Flask response with CSV file
    """
    # Ensure data is a list
    if isinstance(data, dict):
        data = [data]

    if not data:
        return make_response("No data to export", 404)

    # Flatten all dictionaries
    flattened_data = [flatten_dict(item) for item in data]

    # Get all unique keys
    all_keys: set[str] = set()
    for item in flattened_data:
        all_keys.update(item.keys())

    # Sort keys for consistent output
    fieldnames = sorted(all_keys)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for item in flattened_data:
        # Format values
        formatted_item = {k: format_value_for_csv(v) for k, v in item.items()}
        writer.writerow(formatted_item)

    # Create response
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


def create_json_response(data: Any, filename: str) -> Response:
    """Create JSON response from data

    Args:
        data: Dictionary or list to export
        filename: Filename for download

    Returns:
        Flask response with JSON file
    """

    # Convert datetime objects to ISO format strings
    def datetime_handler(obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # Pretty-print JSON
    json_str = json.dumps(data, indent=2, default=datetime_handler)

    # Create response
    response = make_response(json_str)
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


# ============================================================================
# Export Routes
# ============================================================================


@app.route("/api/export/team/<team_name>/csv")
def export_team_csv(team_name: str) -> Response:
    """Export team metrics as CSV"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        teams = data.get("teams", {})
        if team_name not in teams:
            return make_response(f"Team '{team_name}' not found", 404)

        team_data = teams[team_name].copy()

        # Add metadata
        date_range_info = metrics_cache.get("date_range", {})
        team_data["export_timestamp"] = datetime.now()
        team_data["date_range_start"] = date_range_info.get("start_date", "")
        team_data["date_range_end"] = date_range_info.get("end_date", "")
        team_data["date_range_label"] = date_range_info.get("label", "")

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"team_{team_name.replace(' ', '_').lower()}_metrics_{date_suffix}.csv"
        return create_csv_response(team_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/team/<team_name>/json")
def export_team_json(team_name: str) -> Response:
    """Export team metrics as JSON"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        teams = data.get("teams", {})
        if team_name not in teams:
            return make_response(f"Team '{team_name}' not found", 404)

        team_data = teams[team_name].copy()

        # Add metadata
        date_range_info = metrics_cache.get("date_range", {})
        export_data = {
            "team": team_data,
            "metadata": {"export_timestamp": datetime.now(), "date_range": date_range_info},
        }

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"team_{team_name.replace(' ', '_').lower()}_metrics_{date_suffix}.json"
        return create_json_response(export_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/person/<username>/csv")
def export_person_csv(username: str) -> Response:
    """Export person metrics as CSV"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        persons = data.get("persons", {})
        if username not in persons:
            return make_response(f"Person '{username}' not found", 404)

        person_data = persons[username].copy()

        # Add metadata
        date_range_info = metrics_cache.get("date_range", {})
        person_data["export_timestamp"] = datetime.now()
        person_data["date_range_start"] = date_range_info.get("start_date", "")
        person_data["date_range_end"] = date_range_info.get("end_date", "")
        person_data["date_range_label"] = date_range_info.get("label", "")

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"person_{username.replace(' ', '_').lower()}_metrics_{date_suffix}.csv"
        return create_csv_response(person_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/person/<username>/json")
def export_person_json(username: str) -> Response:
    """Export person metrics as JSON"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        persons = data.get("persons", {})
        if username not in persons:
            return make_response(f"Person '{username}' not found", 404)

        person_data = persons[username].copy()

        # Add metadata
        date_range_info = metrics_cache.get("date_range", {})
        export_data = {
            "person": person_data,
            "metadata": {"export_timestamp": datetime.now(), "date_range": date_range_info},
        }

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"person_{username.replace(' ', '_').lower()}_metrics_{date_suffix}.json"
        return create_json_response(export_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/comparison/csv")
def export_comparison_csv() -> Response:
    """Export team comparison as CSV"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        comparison = data.get("comparison", {})
        if not comparison:
            return make_response("No comparison data available", 404)

        # Get performance scores and prepare data
        teams_data = []
        for team_name, team_metrics in comparison.items():
            team_row = {"team_name": team_name}
            team_row.update(team_metrics)
            teams_data.append(team_row)

        # Add metadata to first row
        date_range_info = metrics_cache.get("date_range", {})
        if teams_data:
            teams_data[0]["export_timestamp"] = datetime.now()
            teams_data[0]["date_range_start"] = date_range_info.get("start_date", "")
            teams_data[0]["date_range_end"] = date_range_info.get("end_date", "")
            teams_data[0]["date_range_label"] = date_range_info.get("label", "")

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"team_comparison_metrics_{date_suffix}.csv"
        return create_csv_response(teams_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/comparison/json")
def export_comparison_json() -> Response:
    """Export team comparison as JSON"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        comparison = data.get("comparison", {})
        if not comparison:
            return make_response("No comparison data available", 404)

        # Add metadata
        date_range_info = metrics_cache.get("date_range", {})
        export_data = {
            "comparison": comparison,
            "metadata": {"export_timestamp": datetime.now(), "date_range": date_range_info},
        }

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"team_comparison_metrics_{date_suffix}.json"
        return create_json_response(export_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/team-members/<team_name>/csv")
def export_team_members_csv(team_name: str) -> Response:
    """Export team member comparison as CSV"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        teams = data.get("teams", {})
        if team_name not in teams:
            return make_response(f"Team '{team_name}' not found", 404)

        team_data = teams[team_name]
        members_breakdown = team_data.get("members_breakdown", {})

        if not members_breakdown:
            return make_response("No member data available for this team", 404)

        # Prepare member rows
        members_data = []
        for member_name, member_metrics in members_breakdown.items():
            member_row = {"member_name": member_name}
            member_row.update(member_metrics)
            members_data.append(member_row)

        # Add metadata to first row
        date_range_info = metrics_cache.get("date_range", {})
        if members_data:
            members_data[0]["team_name"] = team_name
            members_data[0]["export_timestamp"] = datetime.now()
            members_data[0]["date_range_start"] = date_range_info.get("start_date", "")
            members_data[0]["date_range_end"] = date_range_info.get("end_date", "")
            members_data[0]["date_range_label"] = date_range_info.get("label", "")

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"team_{team_name.replace(' ', '_').lower()}_members_comparison_{date_suffix}.csv"
        return create_csv_response(members_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


@app.route("/api/export/team-members/<team_name>/json")
def export_team_members_json(team_name: str) -> Response:
    """Export team member comparison as JSON"""
    try:
        data = metrics_cache.get("data")
        if not data:
            return make_response("No metrics data available. Please collect data first.", 404)

        teams = data.get("teams", {})
        if team_name not in teams:
            return make_response(f"Team '{team_name}' not found", 404)

        team_data = teams[team_name]
        members_breakdown = team_data.get("members_breakdown", {})

        if not members_breakdown:
            return make_response("No member data available for this team", 404)

        # Add metadata
        date_range_info = metrics_cache.get("date_range", {})
        export_data = {
            "team_name": team_name,
            "members": members_breakdown,
            "metadata": {"export_timestamp": datetime.now(), "date_range": date_range_info},
        }

        date_suffix = datetime.now().strftime("%Y-%m-%d")
        filename = f"team_{team_name.replace(' ', '_').lower()}_members_comparison_{date_suffix}.json"
        return create_json_response(export_data, filename)

    except Exception as e:
        return make_response(f"Error exporting data: {str(e)}", 500)


def main() -> None:
    config = get_config()
    dashboard_config = config.dashboard_config

    app.run(debug=dashboard_config.get("debug", True), port=dashboard_config.get("port", 5001), host="0.0.0.0")


if __name__ == "__main__":
    main()
