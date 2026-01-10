from flask import Flask, render_template, jsonify, redirect, request
import sys
from pathlib import Path
import json
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import Config
from src.collectors.github_collector import GitHubCollector
from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.models.metrics import MetricsCalculator
import pandas as pd

app = Flask(__name__)

# Context processor to inject current year into all templates
@app.context_processor
def inject_current_year():
    """Inject current year for footer copyright"""
    return {'current_year': datetime.now().year}

# Global cache
metrics_cache = {
    'data': None,
    'timestamp': None
}

def load_cache_from_file():
    """Load cached metrics from file if available"""
    import pickle
    from pathlib import Path

    cache_file = Path(__file__).parent.parent.parent / 'data' / 'metrics_cache.pkl'
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                # Handle both old format (cache_data['data']) and new format (direct structure)
                if 'data' in cache_data:
                    metrics_cache['data'] = cache_data['data']
                else:
                    # New format: teams, persons, comparison at top level
                    metrics_cache['data'] = cache_data
                metrics_cache['timestamp'] = cache_data.get('timestamp')
                print(f"Loaded cached metrics from {cache_file}")
                print(f"Cache timestamp: {metrics_cache['timestamp']}")
                return True
        except Exception as e:
            print(f"Failed to load cache: {e}")
            return False
    return False

# Try to load cache on startup
load_cache_from_file()

def get_config():
    """Load configuration"""
    return Config()

def get_display_name(username, member_names=None):
    """Get display name for a GitHub username, fallback to username."""
    if member_names and username in member_names:
        return member_names[username]
    return username

def filter_github_data_by_date(raw_data, start_date, end_date):
    """Filter GitHub raw data by date range"""
    filtered = {}

    # Filter PRs
    if 'pull_requests' in raw_data and raw_data['pull_requests']:
        prs_df = pd.DataFrame(raw_data['pull_requests'])
        if 'created_at' in prs_df.columns:
            prs_df['created_at'] = pd.to_datetime(prs_df['created_at'])
            mask = (prs_df['created_at'] >= start_date) & (prs_df['created_at'] <= end_date)
            filtered['pull_requests'] = prs_df[mask].to_dict('records')
        else:
            filtered['pull_requests'] = raw_data['pull_requests']
    else:
        filtered['pull_requests'] = []

    # Filter reviews
    if 'reviews' in raw_data and raw_data['reviews']:
        reviews_df = pd.DataFrame(raw_data['reviews'])
        if 'submitted_at' in reviews_df.columns:
            reviews_df['submitted_at'] = pd.to_datetime(reviews_df['submitted_at'])
            mask = (reviews_df['submitted_at'] >= start_date) & (reviews_df['submitted_at'] <= end_date)
            filtered['reviews'] = reviews_df[mask].to_dict('records')
        else:
            filtered['reviews'] = raw_data['reviews']
    else:
        filtered['reviews'] = []

    # Filter commits
    if 'commits' in raw_data and raw_data['commits']:
        commits_df = pd.DataFrame(raw_data['commits'])
        # Check for both 'date' and 'committed_date' field names
        date_field = 'date' if 'date' in commits_df.columns else 'committed_date'
        if date_field in commits_df.columns:
            commits_df['commit_date'] = pd.to_datetime(commits_df[date_field], utc=True)
            mask = (commits_df['commit_date'] >= start_date) & (commits_df['commit_date'] <= end_date)
            filtered['commits'] = commits_df[mask].to_dict('records')
        else:
            filtered['commits'] = raw_data['commits']
    else:
        filtered['commits'] = []

    return filtered

def filter_jira_data_by_date(issues, start_date, end_date):
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
    if 'created' in issues_df.columns:
        issues_df['created'] = pd.to_datetime(issues_df['created'], utc=True)
    if 'resolved' in issues_df.columns:
        issues_df['resolved'] = pd.to_datetime(issues_df['resolved'], utc=True)
    if 'updated' in issues_df.columns:
        issues_df['updated'] = pd.to_datetime(issues_df['updated'], utc=True)

    # Include issue if ANY of these conditions are true:
    # - Created in period
    # - Resolved in period
    # - Updated in period (for WIP items)
    mask = pd.Series([False] * len(issues_df))

    if 'created' in issues_df.columns:
        created_mask = (issues_df['created'] >= start_date) & (issues_df['created'] <= end_date)
        mask |= created_mask

    if 'resolved' in issues_df.columns:
        resolved_mask = issues_df['resolved'].notna() & (issues_df['resolved'] >= start_date) & (issues_df['resolved'] <= end_date)
        mask |= resolved_mask

    if 'updated' in issues_df.columns:
        updated_mask = (issues_df['updated'] >= start_date) & (issues_df['updated'] <= end_date)
        mask |= updated_mask

    return issues_df[mask].to_dict('records')

def should_refresh_cache(cache_duration_minutes=60):
    """Check if cache should be refreshed"""
    if metrics_cache['timestamp'] is None:
        return True

    elapsed = (datetime.now() - metrics_cache['timestamp']).total_seconds() / 60
    return elapsed > cache_duration_minutes

def refresh_metrics():
    """Collect and calculate metrics using GraphQL API"""
    config = get_config()
    teams = config.teams

    if not teams:
        print("⚠️ No teams configured. Please configure teams in config.yaml")
        return None

    print(f"🔄 Refreshing metrics for {len(teams)} team(s) using GraphQL API...")

    # Connect to Jira
    jira_config = config.jira_config
    jira_collector = None

    if jira_config.get('server'):
        try:
            jira_collector = JiraCollector(
                server=jira_config['server'],
                username=jira_config['username'],
                api_token=jira_config['api_token'],
                project_keys=jira_config.get('project_keys', []),
                days_back=config.days_back,
                verify_ssl=False
            )
            print("✅ Connected to Jira")
        except Exception as e:
            print(f"⚠️ Could not connect to Jira: {e}")

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
        print(f"\n📊 Collecting {team_name} Team...")

        github_members = team.get('github', {}).get('members', [])
        filter_ids = team.get('jira', {}).get('filters', {})

        # Collect GitHub metrics using GraphQL
        github_collector = GitHubGraphQLCollector(
            token=config.github_token,
            organization=config.github_organization,
            teams=[team.get('github', {}).get('team_slug')] if team.get('github', {}).get('team_slug') else [],
            team_members=github_members,
            days_back=config.days_back
        )

        team_github_data = github_collector.collect_all_metrics()

        all_github_data['pull_requests'].extend(team_github_data['pull_requests'])
        all_github_data['reviews'].extend(team_github_data['reviews'])
        all_github_data['commits'].extend(team_github_data['commits'])

        print(f"   - PRs: {len(team_github_data['pull_requests'])}")
        print(f"   - Reviews: {len(team_github_data['reviews'])}")
        print(f"   - Commits: {len(team_github_data['commits'])}")

        # Collect Jira filter metrics
        jira_filter_results = {}
        if jira_collector and filter_ids:
            print(f"📊 Collecting Jira filters for {team_name}...")
            jira_filter_results = jira_collector.collect_team_filters(filter_ids)

        # Calculate team metrics
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

    # Calculate team comparison
    all_dfs = {
        'pull_requests': pd.DataFrame(all_github_data['pull_requests']),
        'reviews': pd.DataFrame(all_github_data['reviews']),
        'commits': pd.DataFrame(all_github_data['commits']),
        'deployments': pd.DataFrame(all_github_data['deployments']),
    }

    calculator_all = MetricsCalculator(all_dfs)
    team_comparison = calculator_all.calculate_team_comparison(team_metrics)

    # Package data
    cache_data = {
        'teams': team_metrics,
        'comparison': team_comparison,
        'timestamp': datetime.now()
    }

    metrics_cache['data'] = cache_data
    metrics_cache['timestamp'] = datetime.now()

    print(f"\n✅ Metrics refreshed at {metrics_cache['timestamp']}")

    return cache_data

@app.route('/')
def index():
    """Main dashboard page - shows team overview"""
    config = get_config()

    # If no cache exists, show loading page
    if metrics_cache['data'] is None:
        return render_template('loading.html')

    cache = metrics_cache['data']

    # Check if we have the new team-based structure
    if 'teams' in cache:
        # New structure - show team overview
        teams = config.teams
        team_list = []

        for team in teams:
            team_name = team.get('name')
            team_data = cache['teams'].get(team_name, {})
            github_metrics = team_data.get('github', {})
            jira_metrics = team_data.get('jira', {})

            team_list.append({
                'name': team_name,
                'display_name': team.get('display_name', team_name),
                'pr_count': github_metrics.get('pr_count', 0),
                'review_count': github_metrics.get('review_count', 0),
                'commit_count': github_metrics.get('commit_count', 0),
                'avg_cycle_time': github_metrics.get('avg_cycle_time', 0),
                'throughput': jira_metrics.get('throughput', {}).get('weekly_avg', 0) if jira_metrics.get('throughput') else 0,
                'wip_count': jira_metrics.get('wip', {}).get('count', 0) if jira_metrics.get('wip') else 0,
            })

        return render_template('teams_overview.html',
                             teams=team_list,
                             cache=cache,
                             config=config,
                             updated_at=metrics_cache['timestamp'])
    else:
        # Legacy structure - use old dashboard
        return render_template('dashboard.html',
                             metrics=cache,
                             updated_at=metrics_cache['timestamp'])

@app.route('/api/metrics')
def api_metrics():
    """API endpoint for metrics data"""
    config = get_config()

    if should_refresh_cache(config.dashboard_config.get('cache_duration_minutes', 60)):
        try:
            refresh_metrics()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify(metrics_cache['data'])

@app.route('/api/refresh')
def api_refresh():
    """Force refresh metrics"""
    try:
        metrics = refresh_metrics()
        return jsonify({'status': 'success', 'metrics': metrics})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/collect/<period>')
def api_collect_period(period):
    """
    Trigger metrics collection for a specific time period.

    This is a simplified implementation that returns a message about running
    the collection script manually with the specified period.

    For full implementation, run: python collect_data.py --period <period>
    """
    from src.utils.time_periods import parse_period_to_dates, format_period_label

    try:
        # Validate the period format
        start_date, end_date = parse_period_to_dates(period)
        label = format_period_label(period)

        # Return instructions for manual collection
        return jsonify({
            'status': 'info',
            'message': 'Period-based collection requires running the collection script',
            'period': period,
            'label': label,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'command': f'python collect_data.py --period {period}',
            'note': 'This will take 15-30 minutes to complete. Run the command in your terminal.'
        })

    except ValueError as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/reload-cache', methods=['POST'])
def api_reload_cache():
    """Reload metrics cache from disk without restarting server"""
    try:
        success = load_cache_from_file()
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Cache reloaded successfully',
                'timestamp': str(metrics_cache['timestamp'])
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to reload cache - file may not exist or be corrupted'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/collect')
def collect():
    """Trigger collection and redirect to dashboard"""
    try:
        refresh_metrics()
        return redirect('/')
    except Exception as e:
        return render_template('error.html', error=str(e))

@app.route('/team/<team_name>')
def team_dashboard(team_name):
    """Team-specific dashboard"""
    config = get_config()

    if metrics_cache['data'] is None:
        return render_template('loading.html')

    # Check if this is new team-based cache structure
    cache = metrics_cache['data']

    if 'teams' in cache:
        # New structure
        team_data = cache['teams'].get(team_name)

        if not team_data:
            return render_template('error.html', error=f"Team '{team_name}' not found")

        team_config = config.get_team_by_name(team_name)

        # Calculate date range for GitHub search links
        start_date = (datetime.now() - timedelta(days=config.days_back)).strftime('%Y-%m-%d')

        # Get member names mapping
        member_names = cache.get('member_names', {})

        # Add Jira data to member_trends from persons cache
        if 'persons' in cache and 'github' in team_data and 'member_trends' in team_data['github']:
            member_trends = team_data['github']['member_trends']
            for member in member_trends:
                if member in cache['persons']:
                    person_data = cache['persons'][member]
                    if 'jira' in person_data:
                        member_trends[member]['jira'] = {
                            'completed': person_data['jira'].get('completed', 0),
                            'in_progress': person_data['jira'].get('in_progress', 0),
                            'avg_cycle_time': person_data['jira'].get('avg_cycle_time', 0)
                        }

        return render_template('team_dashboard.html',
                             team_name=team_name,
                             team_display_name=team_config.get('display_name', team_name) if team_config else team_name,
                             team_data=team_data,
                             team_config=team_config,
                             member_names=member_names,
                             config=config,
                             days_back=config.days_back,
                             start_date=start_date,
                             jira_server=config.jira_config.get('server', 'https://jira.ops.expertcity.com'),
                             github_org=config.github_organization,
                             github_base_url=config.github_base_url,
                             updated_at=metrics_cache['timestamp'])
    else:
        # Legacy structure - show error
        return render_template('error.html',
                             error="Team dashboards require team configuration. Please update config.yaml and re-run data collection.")

@app.route('/person/<username>')
def person_dashboard(username):
    """Person-specific dashboard showing last 90 days of metrics"""
    config = get_config()

    if metrics_cache['data'] is None:
        return render_template('loading.html')

    cache = metrics_cache['data']

    if 'persons' not in cache:
        return render_template('error.html',
                             error="Person dashboards require team configuration. Please update config.yaml and re-run data collection.")

    # Get cached person data (already contains 90-day metrics)
    person_data = cache['persons'].get(username)
    if not person_data:
        return render_template('error.html', error=f"No metrics found for user '{username}'")

    # Calculate trends from raw data if available
    if 'raw_github_data' in person_data and person_data.get('raw_github_data'):
        person_dfs = {
            'pull_requests': pd.DataFrame(person_data['raw_github_data'].get('pull_requests', [])),
            'reviews': pd.DataFrame(person_data['raw_github_data'].get('reviews', [])),
            'commits': pd.DataFrame(person_data['raw_github_data'].get('commits', []))
        }

        calculator = MetricsCalculator(person_dfs)
        person_data['trends'] = calculator.calculate_person_trends(
            person_data['raw_github_data'],
            period='weekly'
        )
    else:
        # No raw data available, set empty trends
        person_data['trends'] = {
            'pr_trend': [],
            'review_trend': [],
            'commit_trend': [],
            'lines_changed_trend': []
        }

    # Get display name from cache
    member_names = cache.get('member_names', {})
    display_name = get_display_name(username, member_names)

    # Find which team this person belongs to
    team_name = None
    for team in config.teams:
        # Check new format: members list with github/jira keys
        if 'members' in team:
            for member in team.get('members', []):
                if isinstance(member, dict) and member.get('github') == username:
                    team_name = team.get('name')
                    break
        # Check old format: github.members
        elif username in team.get('github', {}).get('members', []):
            team_name = team.get('name')
            break
        if team_name:
            break

    return render_template('person_dashboard.html',
                         username=username,
                         display_name=display_name,
                         person_data=person_data,
                         team_name=team_name,
                         github_org=config.github_organization,
                         github_base_url=config.github_base_url,
                         updated_at=metrics_cache['timestamp'])

@app.route('/team/<team_name>/compare')
def team_members_comparison(team_name):
    """Compare all team members side-by-side"""
    config = get_config()

    if metrics_cache['data'] is None:
        return render_template('loading.html')

    cache = metrics_cache['data']
    team_data = cache.get('teams', {}).get(team_name)
    team_config = config.get_team_by_name(team_name)

    if not team_data:
        return render_template('error.html', error=f"Team '{team_name}' not found")

    if not team_config:
        return render_template('error.html', error=f"Team configuration for '{team_name}' not found")

    # Get all members from team config - support both formats
    members = []
    if 'members' in team_config and isinstance(team_config.get('members'), list):
        # New format: unified members list
        members = [
            m.get('github') for m in team_config['members']
            if isinstance(m, dict) and m.get('github')
        ]
    else:
        # Old format: github.members
        members = team_config.get('github', {}).get('members', [])

    # Get member names mapping
    member_names = cache.get('member_names', {})

    # Build comparison data
    comparison_data = []
    for username in members:
        person_data = cache.get('persons', {}).get(username, {})
        github_data = person_data.get('github', {})
        jira_data = person_data.get('jira', {})

        comparison_data.append({
            'username': username,
            'display_name': get_display_name(username, member_names),
            'prs': github_data.get('prs_created', 0),
            'prs_merged': github_data.get('prs_merged', 0),
            'merge_rate': github_data.get('merge_rate', 0) * 100,
            'reviews': github_data.get('reviews_given', 0),
            'commits': github_data.get('commits', 0),
            'lines_added': github_data.get('lines_added', 0),
            'lines_deleted': github_data.get('lines_deleted', 0),
            'cycle_time': github_data.get('avg_pr_cycle_time', 0),
            # Jira metrics
            'jira_completed': jira_data.get('completed', 0),
            'jira_wip': jira_data.get('in_progress', 0),
            'jira_cycle_time': jira_data.get('avg_cycle_time', 0)
        })

    # Calculate performance scores for each member
    for member in comparison_data:
        member['score'] = MetricsCalculator.calculate_performance_score(member, comparison_data)

    # Sort by score descending
    comparison_data.sort(key=lambda x: x['score'], reverse=True)

    # Add rank and badges
    for i, member in enumerate(comparison_data, 1):
        member['rank'] = i
        if i == 1:
            member['badge'] = '🥇'
        elif i == 2:
            member['badge'] = '🥈'
        elif i == 3:
            member['badge'] = '🥉'
        else:
            member['badge'] = ''

    return render_template('team_members_comparison.html',
                         team_name=team_name,
                         team_display_name=team_config.get('display_name', team_name),
                         comparison_data=comparison_data,
                         config=config,
                         github_org=config.github_organization,
                         updated_at=metrics_cache['timestamp'])

@app.route('/documentation')
def documentation():
    """Documentation and FAQ page"""
    return render_template('documentation.html')

@app.route('/comparison')
def team_comparison():
    """Side-by-side team comparison"""
    if metrics_cache['data'] is None:
        return render_template('loading.html')

    cache = metrics_cache['data']

    if 'comparison' not in cache:
        return render_template('error.html',
                             error="Team comparison requires team configuration.")

    config = get_config()

    # Build team_configs dict for easy lookup in template
    team_configs = {team['name']: team for team in config.teams}

    # Calculate date range for GitHub search links
    start_date = (datetime.now() - timedelta(days=config.days_back)).strftime('%Y-%m-%d')

    # Calculate performance scores for teams
    comparison_data = cache['comparison']
    team_metrics_list = list(comparison_data.values())

    # Add team sizes and calculate scores with normalization
    for team_name, metrics in comparison_data.items():
        team_config = team_configs[team_name]
        # Get team size - support both formats
        if 'members' in team_config and isinstance(team_config.get('members'), list):
            # New format: count members with github field
            team_size = len([
                m for m in team_config['members']
                if isinstance(m, dict) and m.get('github')
            ])
        else:
            # Old format: github.members
            team_size = len(team_config.get('github', {}).get('members', []))
        metrics['team_size'] = team_size
        metrics['score'] = MetricsCalculator.calculate_performance_score(
            metrics,
            team_metrics_list,
            team_size=team_size  # Normalize by team size
        )

    # Count wins for each team (who has the highest value in each metric)
    team_wins = {}
    metrics_to_compare = ['prs', 'reviews', 'commits', 'jira_throughput']

    for metric in metrics_to_compare:
        max_value = max([m.get(metric, 0) for m in comparison_data.values()])
        for team_name, metrics in comparison_data.items():
            if metrics.get(metric, 0) == max_value and max_value > 0:
                team_wins[team_name] = team_wins.get(team_name, 0) + 1

    # Cycle time: lower is better
    cycle_times = {team: m.get('avg_cycle_time', 0) for team, m in comparison_data.items() if m.get('avg_cycle_time', 0) > 0}
    if cycle_times:
        min_cycle_time = min(cycle_times.values())
        for team_name, cycle_time in cycle_times.items():
            if cycle_time == min_cycle_time:
                team_wins[team_name] = team_wins.get(team_name, 0) + 1

    return render_template('comparison.html',
                         comparison=comparison_data,
                         teams=cache.get('teams', {}),
                         team_configs=team_configs,
                         team_wins=team_wins,
                         config=config,
                         github_org=config.github_organization,
                         jira_server=config.jira_config.get('server'),
                         start_date=start_date,
                         days_back=config.days_back,
                         updated_at=metrics_cache['timestamp'])

def main():
    config = get_config()
    dashboard_config = config.dashboard_config

    app.run(
        debug=dashboard_config.get('debug', True),
        port=dashboard_config.get('port', 5000),
        host='0.0.0.0'
    )

if __name__ == '__main__':
    main()
