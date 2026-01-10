from jira import JIRA
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Any
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class JiraCollector:
    def __init__(self, server: str, username: str, api_token: str,
                 project_keys: List[str], team_members: List[str] = None, days_back: int = 90,
                 verify_ssl: bool = True, timeout: int = 120):
        """Initialize Jira collector

        Args:
            server: Jira server URL
            username: Jira username (used for logging)
            api_token: Jira API token/Bearer token
            project_keys: List of project keys to collect from
            team_members: List of team member usernames
            days_back: Number of days to look back
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds (default: 120)
        """
        options = {
            'server': server,
            'verify': verify_ssl,
            'timeout': timeout,  # Add configurable timeout
            'headers': {'Authorization': f'Bearer {api_token}'}
        }
        self.jira = JIRA(options=options)
        self.project_keys = project_keys
        self.team_members = team_members or []
        self.days_back = days_back
        self.since_date = datetime.now() - timedelta(days=days_back)

    def collect_all_metrics(self):
        """Collect all metrics from Jira"""
        all_data = {
            'issues': [],
            'sprints': [],
            'worklogs': []
        }

        for project_key in self.project_keys:
            print(f"Collecting Jira metrics for project {project_key}...")

            all_data['issues'].extend(self.collect_issue_metrics(project_key))
            all_data['worklogs'].extend(self.collect_worklog_metrics(project_key))

        return all_data

    def collect_issue_metrics(self, project_key: str):
        """Collect issue metrics"""
        issues = []

        # Build JQL query with team member filter if specified
        jql = f'project = {project_key} AND (created >= -{self.days_back}d OR resolved >= -{self.days_back}d OR (statusCategory != Done AND updated >= -{self.days_back}d))'
        if self.team_members:
            members_str = ', '.join(self.team_members)
            jql += f' AND (assignee in ({members_str}) OR reporter in ({members_str}))'
        jql += ' ORDER BY updated DESC'

        try:
            jira_issues = self.jira.search_issues(jql, maxResults=1000, expand='changelog')

            for issue in jira_issues:
                issue_data = {
                    'key': issue.key,
                    'project': project_key,
                    'type': issue.fields.issuetype.name,
                    'status': issue.fields.status.name,
                    'priority': issue.fields.priority.name if issue.fields.priority else None,
                    'assignee': issue.fields.assignee.name if issue.fields.assignee else None,
                    'reporter': issue.fields.reporter.name if issue.fields.reporter else None,
                    'created': issue.fields.created,
                    'updated': issue.fields.updated,
                    'resolved': issue.fields.resolutiondate,
                    'summary': issue.fields.summary,
                    'story_points': getattr(issue.fields, 'customfield_10016', None),
                }

                # Calculate cycle time (created to resolved)
                if issue.fields.resolutiondate:
                    created = datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z')
                    resolved = datetime.strptime(issue.fields.resolutiondate, '%Y-%m-%dT%H:%M:%S.%f%z')
                    issue_data['cycle_time_hours'] = (resolved - created).total_seconds() / 3600
                else:
                    issue_data['cycle_time_hours'] = None

                # Get time in each status from changelog
                status_times = self._calculate_status_times(issue)
                issue_data.update(status_times)

                issues.append(issue_data)

        except Exception as e:
            print(f"Error collecting issues for {project_key}: {e}")

        return issues

    def _calculate_status_times(self, issue):
        """Calculate time spent in each status"""
        status_times = {
            'time_in_todo_hours': 0,
            'time_in_progress_hours': 0,
            'time_in_review_hours': 0,
        }

        if not hasattr(issue, 'changelog'):
            return status_times

        current_status = None
        last_transition_time = datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z')

        for history in issue.changelog.histories:
            for item in history.items:
                if item.field == 'status':
                    transition_time = datetime.strptime(history.created, '%Y-%m-%dT%H:%M:%S.%f%z')

                    if current_status:
                        time_diff = (transition_time - last_transition_time).total_seconds() / 3600

                        if 'to do' in current_status.lower() or 'backlog' in current_status.lower():
                            status_times['time_in_todo_hours'] += time_diff
                        elif 'in progress' in current_status.lower() or 'doing' in current_status.lower():
                            status_times['time_in_progress_hours'] += time_diff
                        elif 'review' in current_status.lower() or 'testing' in current_status.lower():
                            status_times['time_in_review_hours'] += time_diff

                    current_status = item.toString
                    last_transition_time = transition_time

        # Add time in current status
        if current_status:
            time_diff = (datetime.now(last_transition_time.tzinfo) - last_transition_time).total_seconds() / 3600

            if 'to do' in current_status.lower() or 'backlog' in current_status.lower():
                status_times['time_in_todo_hours'] += time_diff
            elif 'in progress' in current_status.lower() or 'doing' in current_status.lower():
                status_times['time_in_progress_hours'] += time_diff
            elif 'review' in current_status.lower() or 'testing' in current_status.lower():
                status_times['time_in_review_hours'] += time_diff

        return status_times

    def collect_worklog_metrics(self, project_key: str):
        """Collect worklog (time tracking) metrics"""
        worklogs = []

        jql = f'project = {project_key} AND worklogDate >= -{self.days_back}d'

        try:
            issues = self.jira.search_issues(jql, maxResults=1000)

            for issue in issues:
                issue_worklogs = self.jira.worklogs(issue.key)

                for worklog in issue_worklogs:
                    worklogs.append({
                        'issue_key': issue.key,
                        'project': project_key,
                        'author': worklog.author.name,
                        'time_spent_hours': worklog.timeSpentSeconds / 3600,
                        'started': worklog.started,
                    })

        except Exception as e:
            print(f"Error collecting worklogs for {project_key}: {e}")

        return worklogs

    def collect_person_issues(self, jira_username: str, days_back: int = 90, expand_changelog: bool = True) -> List[Dict]:
        """Collect all Jira issues for a specific person.

        Args:
            jira_username: Jira username (assignee)
            days_back: Number of days to look back (default: 90)
            expand_changelog: Whether to expand changelog (default: True, can cause timeouts)

        Returns:
            List of issue dictionaries with all fields
        """
        issues = []

        try:
            # Build JQL to find all issues assigned to this person
            # Use created/resolved/updated to capture:
            # - New issues created recently (created >= -Xd)
            # - Old issues resolved recently (resolved >= -Xd)
            # - Issues still in progress (statusCategory != Done AND updated >= -Xd)
            # Note: Filtering 'updated' to non-Done items prevents noise from bulk administrative updates
            jql = f'assignee = "{jira_username}" AND (created >= -{days_back}d OR resolved >= -{days_back}d OR (statusCategory != Done AND updated >= -{days_back}d)) ORDER BY updated DESC'

            print(f"  Querying Jira for {jira_username}: {jql}")

            # Execute query with optional changelog for status transitions
            expand = 'changelog' if expand_changelog else None
            jira_issues = self.jira.search_issues(jql, maxResults=1000, expand=expand)

            for issue in jira_issues:
                issue_data = {
                    'key': issue.key,
                    'project': issue.fields.project.key,
                    'type': issue.fields.issuetype.name,
                    'status': issue.fields.status.name,
                    'priority': issue.fields.priority.name if issue.fields.priority else None,
                    'assignee': issue.fields.assignee.name if issue.fields.assignee else None,
                    'reporter': issue.fields.reporter.name if issue.fields.reporter else None,
                    'created': issue.fields.created,
                    'updated': issue.fields.updated,
                    'resolved': issue.fields.resolutiondate,
                    'summary': issue.fields.summary,
                    'story_points': getattr(issue.fields, 'customfield_10016', None),
                    'labels': issue.fields.labels if hasattr(issue.fields, 'labels') else [],
                    'flagged': any('blocked' in label.lower() or 'impediment' in label.lower()
                                  for label in getattr(issue.fields, 'labels', []))
                }

                # Calculate cycle time (created to resolved)
                if issue.fields.resolutiondate:
                    created = datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z')
                    resolved = datetime.strptime(issue.fields.resolutiondate, '%Y-%m-%dT%H:%M:%S.%f%z')
                    issue_data['cycle_time_hours'] = (resolved - created).total_seconds() / 3600
                else:
                    issue_data['cycle_time_hours'] = None

                # Calculate time in current status (for WIP items)
                if issue.fields.resolutiondate is None:
                    updated = datetime.strptime(issue.fields.updated, '%Y-%m-%dT%H:%M:%S.%f%z')
                    now = datetime.now(updated.tzinfo)
                    issue_data['days_in_current_status'] = (now - updated).days
                else:
                    issue_data['days_in_current_status'] = None

                # Get time in each status from changelog
                status_times = self._calculate_status_times(issue)
                issue_data.update(status_times)

                issues.append(issue_data)

        except Exception as e:
            print(f"  Error collecting issues for {jira_username}: {e}")
            raise  # Re-raise so caller can handle

        return issues

    def collect_filter_issues(self, filter_id: int, add_time_constraint: bool = False):
        """Execute filter by ID and return issues

        Args:
            filter_id: Jira filter ID
            add_time_constraint: If True, adds (created >= -90d OR resolved >= -90d) to JQL

        Returns:
            List of issue dictionaries
        """
        issues = []

        try:
            # Get filter and execute its JQL
            jira_filter = self.jira.filter(filter_id)
            jql = jira_filter.jql if hasattr(jira_filter, 'jql') else None

            if not jql:
                print(f"Warning: Could not get JQL for filter {filter_id}")
                return issues

            print(f"  Executing filter {filter_id}: {jira_filter.name}")

            # Add time constraint if requested (for scope filters that return too many results)
            if add_time_constraint:
                # Insert the time constraint before ORDER BY if present, or at the end
                if 'ORDER BY' in jql.upper():
                    parts = jql.split('ORDER BY')
                    jql = f"{parts[0].strip()} AND (created >= -90d OR resolved >= -90d) ORDER BY {parts[1].strip()}"
                else:
                    jql = f"{jql} AND (created >= -90d OR resolved >= -90d)"
                print(f"  Added time constraint: (created >= -90d OR resolved >= -90d)")

            # Execute the filter's JQL
            jira_issues = self.jira.search_issues(jql, maxResults=1000, expand='changelog')

            # DEBUG: Log raw count
            print(f"  DEBUG: Retrieved {len(jira_issues)} issues from Jira")

            # DEBUG: Check for duplicates
            issue_keys = [issue.key for issue in jira_issues]
            unique_keys = set(issue_keys)
            if len(issue_keys) != len(unique_keys):
                duplicates = [k for k in issue_keys if issue_keys.count(k) > 1]
                print(f"  WARNING: Found {len(issue_keys) - len(unique_keys)} duplicate issues!")
                print(f"  Duplicate keys: {set(duplicates)}")

            for issue in jira_issues:
                issue_data = {
                    'key': issue.key,
                    'project': issue.fields.project.key,
                    'type': issue.fields.issuetype.name,
                    'status': issue.fields.status.name,
                    'priority': issue.fields.priority.name if issue.fields.priority else None,
                    'assignee': issue.fields.assignee.name if issue.fields.assignee else None,
                    'reporter': issue.fields.reporter.name if issue.fields.reporter else None,
                    'created': issue.fields.created,
                    'updated': issue.fields.updated,
                    'resolved': issue.fields.resolutiondate,
                    'summary': issue.fields.summary,
                    'story_points': getattr(issue.fields, 'customfield_10016', None),
                    'labels': issue.fields.labels if hasattr(issue.fields, 'labels') else [],
                    'flagged': any('blocked' in label.lower() or 'impediment' in label.lower()
                                  for label in getattr(issue.fields, 'labels', []))
                }

                # Calculate cycle time
                if issue.fields.resolutiondate:
                    created = datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z')
                    resolved = datetime.strptime(issue.fields.resolutiondate, '%Y-%m-%dT%H:%M:%S.%f%z')
                    issue_data['cycle_time_hours'] = (resolved - created).total_seconds() / 3600
                else:
                    issue_data['cycle_time_hours'] = None

                # Calculate time in current status (for WIP items)
                if issue.fields.resolutiondate is None:
                    updated = datetime.strptime(issue.fields.updated, '%Y-%m-%dT%H:%M:%S.%f%z')
                    now = datetime.now(updated.tzinfo)
                    issue_data['days_in_current_status'] = (now - updated).days
                else:
                    issue_data['days_in_current_status'] = None

                # Get time in each status
                status_times = self._calculate_status_times(issue)
                issue_data.update(status_times)

                issues.append(issue_data)

        except Exception as e:
            print(f"Error collecting filter {filter_id}: {e}")

        return issues

    def collect_team_filters(self, filter_ids: Dict[str, int]):
        """Batch collect all team filters

        Args:
            filter_ids: Dictionary mapping filter names to filter IDs
                       Example: {'completed_12weeks': 12345, 'wip': 12346}

        Returns:
            Dictionary mapping filter names to lists of issues
        """
        filter_results = {}

        # Filters that should have time constraints added (they return too many results otherwise)
        filters_needing_time_constraint = ['scope', 'bugs']

        for filter_name, filter_id in filter_ids.items():
            print(f"Collecting filter '{filter_name}' (ID: {filter_id})...")

            # Add time constraint for scope/bugs filters to avoid timeouts
            add_time_constraint = filter_name in filters_needing_time_constraint
            issues = self.collect_filter_issues(filter_id, add_time_constraint=add_time_constraint)

            filter_results[filter_name] = issues
            print(f"  Found {len(issues)} issues")

        return filter_results

    def calculate_throughput(self, issues: List) -> Dict:
        """Calculate throughput from completed issues

        Args:
            issues: List of issue dictionaries

        Returns:
            Dictionary with throughput metrics
        """
        if not issues:
            return {'weekly_throughput': 0, 'total_completed': 0}

        df = pd.DataFrame(issues)

        # Filter to resolved issues
        df_resolved = df[df['resolved'].notna()].copy()

        if df_resolved.empty:
            return {'weekly_throughput': 0, 'total_completed': 0}

        # Convert resolved date to datetime
        df_resolved['resolved_date'] = pd.to_datetime(df_resolved['resolved'])
        df_resolved['week'] = df_resolved['resolved_date'].dt.to_period('W')

        # Count issues per week
        weekly_counts = df_resolved.groupby('week').size()

        return {
            'weekly_throughput': weekly_counts.mean() if len(weekly_counts) > 0 else 0,
            'total_completed': len(df_resolved),
            'by_week': weekly_counts.to_dict()
        }

    def calculate_time_since_wip(self, issues: List) -> Dict:
        """Calculate days in WIP status

        Args:
            issues: List of WIP issue dictionaries

        Returns:
            Dictionary with WIP age metrics
        """
        if not issues:
            return {'avg_days': 0, 'max_days': 0, 'distribution': {}}

        ages = [issue.get('days_in_current_status', 0) for issue in issues if issue.get('days_in_current_status') is not None]

        if not ages:
            return {'avg_days': 0, 'max_days': 0, 'distribution': {}}

        # Create age distribution buckets
        distribution = {
            '0-3 days': len([a for a in ages if 0 <= a <= 3]),
            '4-7 days': len([a for a in ages if 4 <= a <= 7]),
            '8-14 days': len([a for a in ages if 8 <= a <= 14]),
            '15+ days': len([a for a in ages if a >= 15])
        }

        return {
            'avg_days': sum(ages) / len(ages) if ages else 0,
            'max_days': max(ages) if ages else 0,
            'min_days': min(ages) if ages else 0,
            'distribution': distribution
        }

    def get_flagged_issues(self, issues: List) -> List[Dict]:
        """Extract flagged/blocked issues

        Args:
            issues: List of issue dictionaries

        Returns:
            List of flagged issues with key info
        """
        flagged = []

        for issue in issues:
            if issue.get('flagged'):
                flagged.append({
                    'key': issue['key'],
                    'summary': issue['summary'],
                    'assignee': issue.get('assignee', 'Unassigned'),
                    'status': issue['status'],
                    'days_blocked': issue.get('days_in_current_status', 0)
                })

        return flagged

    def get_dataframes(self):
        """Return all metrics as pandas DataFrames"""
        data = self.collect_all_metrics()

        return {
            'issues': pd.DataFrame(data['issues']),
            'worklogs': pd.DataFrame(data['worklogs']),
        }
