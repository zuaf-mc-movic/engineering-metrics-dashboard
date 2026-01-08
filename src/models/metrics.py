import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List
import warnings

# Suppress pandas timezone conversion warnings
warnings.filterwarnings('ignore', message='Converting to PeriodArray/Index representation will drop timezone information')


class MetricsCalculator:
    def __init__(self, dataframes: Dict[str, pd.DataFrame]):
        self.dfs = dataframes

    def calculate_pr_metrics(self):
        """Calculate PR-related metrics"""
        if self.dfs['pull_requests'].empty:
            return {
                'total_prs': 0,
                'merged_prs': 0,
                'open_prs': 0,
                'closed_unmerged_prs': 0,
                'merge_rate': 0,
                'avg_cycle_time_hours': None,
                'median_cycle_time_hours': None,
                'avg_time_to_first_review_hours': None,
                'avg_pr_size': 0,
                'pr_size_distribution': {}
            }

        df = self.dfs['pull_requests']

        metrics = {
            'total_prs': len(df),
            'merged_prs': len(df[df['merged'] == True]),
            'open_prs': len(df[df['state'] == 'open']),
            'closed_unmerged_prs': len(df[(df['state'] == 'closed') & (df['merged'] == False)]),
            'avg_cycle_time_hours': df['cycle_time_hours'].mean(),
            'median_cycle_time_hours': df['cycle_time_hours'].median(),
            'avg_time_to_first_review_hours': df['time_to_first_review_hours'].mean(),
            'avg_pr_size': (df['additions'] + df['deletions']).mean(),
            'merge_rate': len(df[df['merged'] == True]) / len(df) if len(df) > 0 else 0,
        }

        # PR size distribution
        df['size'] = df['additions'] + df['deletions']
        metrics['pr_size_distribution'] = {
            'small (<100 lines)': len(df[df['size'] < 100]),
            'medium (100-500 lines)': len(df[(df['size'] >= 100) & (df['size'] < 500)]),
            'large (500-1000 lines)': len(df[(df['size'] >= 500) & (df['size'] < 1000)]),
            'xlarge (>1000 lines)': len(df[df['size'] >= 1000]),
        }

        return metrics

    def calculate_review_metrics(self):
        """Calculate review-related metrics"""
        if self.dfs['reviews'].empty:
            return {
                'total_reviews': 0,
                'unique_reviewers': 0,
                'avg_reviews_per_pr': 0,
                'top_reviewers': {}
            }

        df = self.dfs['reviews']

        metrics = {
            'total_reviews': len(df),
            'unique_reviewers': df['reviewer'].nunique(),
            'avg_reviews_per_pr': len(df) / self.dfs['pull_requests']['pr_number'].nunique()
                if not self.dfs['pull_requests'].empty else 0,
        }

        # Top reviewers
        top_reviewers = df['reviewer'].value_counts().head(10)
        metrics['top_reviewers'] = top_reviewers.to_dict()

        # Review engagement (who reviews whose code)
        if 'pr_author' in df.columns:
            engagement = df.groupby(['reviewer', 'pr_author']).size().reset_index(name='count')
            metrics['cross_team_reviews'] = len(engagement)

        return metrics

    def calculate_contributor_metrics(self):
        """Calculate contributor activity metrics"""
        if self.dfs['commits'].empty:
            return {
                'total_commits': 0,
                'unique_contributors': 0,
                'avg_commits_per_day': 0,
                'total_lines_added': 0,
                'total_lines_deleted': 0,
                'top_contributors': {},
                'daily_commit_count': {}
            }

        df = self.dfs['commits']

        metrics = {
            'total_commits': len(df),
            'unique_contributors': df['author'].nunique(),
            'avg_commits_per_day': len(df) / 90,
            'total_lines_added': df['additions'].sum(),
            'total_lines_deleted': df['deletions'].sum(),
        }

        # Top contributors
        top_contributors = df.groupby('author').agg({
            'sha': 'count',
            'additions': 'sum',
            'deletions': 'sum'
        }).sort_values('sha', ascending=False).head(10)

        metrics['top_contributors'] = top_contributors.to_dict('index')

        # Commit activity by date
        df['date_only'] = pd.to_datetime(df['date']).dt.date
        daily_commits = df.groupby('date_only').size()
        # Convert date keys to strings for JSON serialization
        metrics['daily_commit_count'] = {str(k): v for k, v in daily_commits.to_dict().items()}

        return metrics

    def calculate_deployment_metrics(self):
        """Calculate deployment frequency and lead time"""
        if self.dfs['deployments'].empty:
            return {
                'total_deployments': 0,
                'deployments_per_week': 0,
            }

        df = self.dfs['deployments']

        # Calculate deployment frequency
        df['date_only'] = pd.to_datetime(df['created_at']).dt.date
        days_range = (df['date_only'].max() - df['date_only'].min()).days or 1

        metrics = {
            'total_deployments': len(df),
            'deployments_per_week': len(df) / (days_range / 7) if days_range > 0 else 0,
            'deployments_by_environment': df['environment'].value_counts().to_dict(),
        }

        return metrics

    def calculate_jira_metrics(self):
        """Calculate Jira-related metrics"""
        if 'jira_issues' not in self.dfs or self.dfs['jira_issues'].empty:
            return {}

        df = self.dfs['jira_issues']

        metrics = {
            'total_issues': len(df),
            'resolved_issues': len(df[df['resolved'].notna()]),
            'open_issues': len(df[df['resolved'].isna()]),
        }

        # Average cycle time for resolved issues
        resolved_df = df[df['cycle_time_hours'].notna()]
        if not resolved_df.empty:
            metrics['avg_cycle_time_hours'] = resolved_df['cycle_time_hours'].mean()
            metrics['median_cycle_time_hours'] = resolved_df['cycle_time_hours'].median()
        else:
            metrics['avg_cycle_time_hours'] = None
            metrics['median_cycle_time_hours'] = None

        # Issues by type
        if 'type' in df.columns:
            metrics['issues_by_type'] = df['type'].value_counts().to_dict()

        # Issues by status
        if 'status' in df.columns:
            metrics['issues_by_status'] = df['status'].value_counts().to_dict()

        # Issues by assignee
        if 'assignee' in df.columns:
            top_assignees = df['assignee'].value_counts().head(10)
            metrics['top_assignees'] = top_assignees.to_dict()

        return metrics

    def calculate_team_metrics(self, team_name: str, team_config: Dict, jira_filter_results: Dict = None) -> Dict:
        """Calculate team-level metrics

        Args:
            team_name: Name of the team
            team_config: Team configuration with members
            jira_filter_results: Results from Jira filter collection

        Returns:
            Dictionary with team metrics
        """
        github_members = team_config.get('github', {}).get('members', [])

        # Filter dataframes to team members
        team_dfs = {
            'pull_requests': self.dfs['pull_requests'][
                self.dfs['pull_requests']['author'].isin(github_members)
            ] if not self.dfs['pull_requests'].empty else pd.DataFrame(),

            'reviews': self.dfs['reviews'][
                self.dfs['reviews']['reviewer'].isin(github_members)
            ] if not self.dfs['reviews'].empty else pd.DataFrame(),

            'commits': self.dfs['commits'][
                self.dfs['commits']['author'].isin(github_members)
            ] if not self.dfs['commits'].empty else pd.DataFrame(),
        }

        # Calculate basic GitHub metrics
        pr_count = len(team_dfs['pull_requests'])
        review_count = len(team_dfs['reviews'])
        commit_count = len(team_dfs['commits'])

        # Calculate per-member trends
        member_trends = {}
        for member in github_members:
            member_prs = team_dfs['pull_requests'][team_dfs['pull_requests']['author'] == member]
            member_reviews = team_dfs['reviews'][team_dfs['reviews']['reviewer'] == member]
            member_commits = team_dfs['commits'][team_dfs['commits']['author'] == member]

            member_trends[member] = {
                'prs': len(member_prs),
                'reviews': len(member_reviews),
                'commits': len(member_commits),
                'lines_added': member_commits['additions'].sum() if not member_commits.empty else 0,
                'lines_deleted': member_commits['deletions'].sum() if not member_commits.empty else 0,
            }

        # Process Jira filter results
        jira_metrics = {}
        if jira_filter_results:
            # Throughput from completed items
            completed_issues = jira_filter_results.get('completed_12weeks', [])
            if completed_issues:
                # Calculate throughput by week
                df_completed = pd.DataFrame(completed_issues)
                if not df_completed.empty and 'resolved' in df_completed.columns:
                    # Remove duplicates based on issue key (keep first occurrence)
                    original_count = len(df_completed)
                    df_completed = df_completed.drop_duplicates(subset=['key'], keep='first')
                    dedup_count = len(df_completed)

                    if original_count != dedup_count:
                        print(f"  INFO: Removed {original_count - dedup_count} duplicate issues from throughput")

                    df_completed['resolved_date'] = pd.to_datetime(df_completed['resolved'])
                    df_completed['week'] = df_completed['resolved_date'].dt.to_period('W')
                    weekly_counts = df_completed.groupby('week').size()

                    # Count issues by type for pie chart
                    type_breakdown = {}
                    for issue in completed_issues:
                        issue_type = issue.get('type', 'Unknown')
                        type_breakdown[issue_type] = type_breakdown.get(issue_type, 0) + 1

                    jira_metrics['throughput'] = {
                        'weekly_avg': weekly_counts.mean() if len(weekly_counts) > 0 else 0,
                        'total_completed': len(df_completed),  # Now deduplicated count
                        'by_week': {str(k): int(v) for k, v in weekly_counts.to_dict().items()},
                        'by_type': type_breakdown
                    }

            # WIP statistics
            wip_issues = jira_filter_results.get('wip', [])
            if wip_issues:
                ages = [issue.get('days_in_current_status', 0) for issue in wip_issues
                       if issue.get('days_in_current_status') is not None]

                # Count WIP items by status
                status_breakdown = {}
                for issue in wip_issues:
                    status = issue.get('status', 'Unknown')
                    status_breakdown[status] = status_breakdown.get(status, 0) + 1

                jira_metrics['wip'] = {
                    'count': len(wip_issues),
                    'avg_age_days': sum(ages) / len(ages) if ages else 0,
                    'age_distribution': {
                        '0-3 days': len([a for a in ages if 0 <= a <= 3]),
                        '4-7 days': len([a for a in ages if 4 <= a <= 7]),
                        '8-14 days': len([a for a in ages if 8 <= a <= 14]),
                        '15+ days': len([a for a in ages if a >= 15])
                    },
                    'by_status': status_breakdown
                }

            # Flagged/blocked items
            flagged_issues = jira_filter_results.get('flagged_blocked', [])
            jira_metrics['flagged'] = {
                'count': len(flagged_issues),
                'issues': [{
                    'key': issue['key'],
                    'summary': issue['summary'],
                    'assignee': issue.get('assignee', 'Unassigned'),
                    'days_blocked': issue.get('days_in_current_status', 0)
                } for issue in flagged_issues[:10]]  # Top 10
            }

            # Created vs Resolved
            bugs_created = jira_filter_results.get('bugs_created', [])
            bugs_resolved = jira_filter_results.get('bugs_resolved', [])

            # Bugs: Created vs Resolved trends (last 90 days)
            from datetime import datetime, timedelta, timezone
            ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

            bugs_by_week_created = {}
            for issue in bugs_created:
                created_date = issue.get('created')
                if created_date:
                    try:
                        created_dt = pd.to_datetime(created_date)
                        if created_dt >= ninety_days_ago:
                            week = created_dt.strftime('%Y-W%U')
                            bugs_by_week_created[week] = bugs_by_week_created.get(week, 0) + 1
                    except:
                        pass  # Skip invalid dates

            bugs_by_week_resolved = {}
            for issue in bugs_resolved:
                resolved_date = issue.get('resolved')
                if resolved_date:
                    try:
                        resolved_dt = pd.to_datetime(resolved_date)
                        if resolved_dt >= ninety_days_ago:
                            week = resolved_dt.strftime('%Y-W%U')
                            bugs_by_week_resolved[week] = bugs_by_week_resolved.get(week, 0) + 1
                    except:
                        pass  # Skip invalid dates

            jira_metrics['bugs'] = {
                'created': len(bugs_created),
                'resolved': len(bugs_resolved),
                'net': len(bugs_created) - len(bugs_resolved),
                'trend_created': bugs_by_week_created if bugs_by_week_created else None,
                'trend_resolved': bugs_by_week_resolved if bugs_by_week_resolved else None
            }

            # Scope: Created vs Resolved trends (last 90 days)
            scope_issues = jira_filter_results.get('scope', [])
            if scope_issues:
                scope_by_week_created = {}
                scope_by_week_resolved = {}

                for issue in scope_issues:
                    created_date = issue.get('created')
                    if created_date:
                        try:
                            created_dt = pd.to_datetime(created_date)
                            if created_dt >= ninety_days_ago:
                                week = created_dt.strftime('%Y-W%U')
                                scope_by_week_created[week] = scope_by_week_created.get(week, 0) + 1
                        except:
                            pass  # Skip invalid dates

                    resolved_date = issue.get('resolved')
                    if resolved_date:
                        try:
                            resolved_dt = pd.to_datetime(resolved_date)
                            if resolved_dt >= ninety_days_ago:
                                week = resolved_dt.strftime('%Y-W%U')
                                scope_by_week_resolved[week] = scope_by_week_resolved.get(week, 0) + 1
                        except:
                            pass  # Skip invalid dates

                jira_metrics['scope'] = {
                    'total': len(scope_issues),
                    'trend_created': scope_by_week_created if scope_by_week_created else None,
                    'trend_resolved': scope_by_week_resolved if scope_by_week_resolved else None
                }
            else:
                # Always create scope entry even if no data
                jira_metrics['scope'] = {
                    'total': 0,
                    'trend_created': None,
                    'trend_resolved': None
                }

        return {
            'team_name': team_name,
            'github': {
                'pr_count': pr_count,
                'review_count': review_count,
                'commit_count': commit_count,
                'avg_cycle_time': team_dfs['pull_requests']['cycle_time_hours'].mean()
                                 if not team_dfs['pull_requests'].empty else 0,
                'member_trends': member_trends
            },
            'jira': jira_metrics
        }

    def calculate_person_metrics(self, username: str, github_data: Dict, jira_data: List = None,
                                 start_date: datetime = None, end_date: datetime = None) -> Dict:
        """Calculate person-level metrics

        Args:
            username: GitHub username
            github_data: Dictionary with PR, review, commit data
            jira_data: Optional list of Jira issues for this person
            start_date: Period start date
            end_date: Period end date

        Returns:
            Dictionary with person metrics
        """
        # Convert to DataFrames
        prs_df = pd.DataFrame(github_data.get('pull_requests', []))
        reviews_df = pd.DataFrame(github_data.get('reviews', []))
        commits_df = pd.DataFrame(github_data.get('commits', []))

        # GitHub metrics
        github_metrics = {
            'prs_created': len(prs_df),
            'prs_merged': len(prs_df[prs_df['merged'] == True]) if not prs_df.empty else 0,
            'merge_rate': (len(prs_df[prs_df['merged'] == True]) / len(prs_df)
                          if len(prs_df) > 0 else 0),
            'reviews_given': len(reviews_df),
            'prs_reviewed': reviews_df['pr_number'].nunique() if not reviews_df.empty else 0,
            'commits': len(commits_df),
            'lines_added': commits_df['additions'].sum() if not commits_df.empty else 0,
            'lines_deleted': commits_df['deletions'].sum() if not commits_df.empty else 0,
            'avg_pr_cycle_time': prs_df['cycle_time_hours'].mean() if not prs_df.empty else 0,
            'avg_time_to_review': prs_df['time_to_first_review_hours'].mean() if not prs_df.empty else 0,
        }

        # Jira metrics
        jira_metrics = {}
        if jira_data:
            jira_df = pd.DataFrame(jira_data)
            if not jira_df.empty:
                # Convert resolved dates to datetime for comparison
                if 'resolved' in jira_df.columns and start_date:
                    jira_df['resolved'] = pd.to_datetime(jira_df['resolved'], errors='coerce')

                # Filter resolved issues to only those resolved in the time window
                if start_date:
                    resolved = jira_df[
                        (jira_df['resolved'].notna()) &
                        (jira_df['resolved'] >= start_date)
                    ]
                else:
                    resolved = jira_df[jira_df['resolved'].notna()]

                jira_metrics = {
                    'completed': len(resolved),
                    'in_progress': len(jira_df[jira_df['resolved'].isna()]),
                    'avg_cycle_time': resolved['cycle_time_hours'].mean() if not resolved.empty else 0,
                    'types': jira_df['type'].value_counts().to_dict() if 'type' in jira_df.columns else {}
                }

        return {
            'username': username,
            'period': {
                'start': start_date.isoformat() if start_date else None,
                'end': end_date.isoformat() if end_date else None
            },
            'github': github_metrics,
            'jira': jira_metrics
        }

    def calculate_person_trends(self, github_data: Dict, period: str = 'weekly') -> Dict:
        """Calculate time-series trends for person metrics

        Args:
            github_data: Raw GitHub data (PRs, reviews, commits)
            period: Grouping period ('daily', 'weekly', 'monthly')

        Returns:
            Dictionary with trend data for charts
        """
        trends = {
            'pr_trend': [],
            'review_trend': [],
            'commit_trend': [],
            'lines_changed_trend': []
        }

        # PR trend
        if github_data.get('pull_requests'):
            prs_df = pd.DataFrame(github_data['pull_requests'])
            if not prs_df.empty and 'created_at' in prs_df.columns:
                prs_df['created_at'] = pd.to_datetime(prs_df['created_at'])
                prs_df['period'] = prs_df['created_at'].dt.strftime('%Y-W%U')
                pr_counts = prs_df.groupby('period').size()
                trends['pr_trend'] = [
                    {'period': p, 'count': int(c)}
                    for p, c in pr_counts.items()
                ]

        # Review trend
        if github_data.get('reviews'):
            reviews_df = pd.DataFrame(github_data['reviews'])
            if not reviews_df.empty and 'submitted_at' in reviews_df.columns:
                reviews_df['submitted_at'] = pd.to_datetime(reviews_df['submitted_at'])
                reviews_df['period'] = reviews_df['submitted_at'].dt.strftime('%Y-W%U')
                review_counts = reviews_df.groupby('period').size()
                trends['review_trend'] = [
                    {'period': p, 'count': int(c)}
                    for p, c in review_counts.items()
                ]

        # Commit trend
        if github_data.get('commits'):
            commits_df = pd.DataFrame(github_data['commits'])
            # Check for both 'date' and 'committed_date' field names
            date_field = 'date' if 'date' in commits_df.columns else 'committed_date'
            if not commits_df.empty and date_field in commits_df.columns:
                commits_df['commit_date'] = pd.to_datetime(commits_df[date_field], utc=True)
                commits_df['period'] = commits_df['commit_date'].dt.strftime('%Y-W%U')
                commit_counts = commits_df.groupby('period').size()
                trends['commit_trend'] = [
                    {'period': p, 'count': int(c)}
                    for p, c in commit_counts.items()
                ]

                # Lines changed trend
                if 'additions' in commits_df.columns and 'deletions' in commits_df.columns:
                    lines_agg = commits_df.groupby('period').agg({
                        'additions': 'sum',
                        'deletions': 'sum'
                    })
                    trends['lines_changed_trend'] = [
                        {
                            'period': p,
                            'additions': int(row['additions']),
                            'deletions': int(row['deletions'])
                        }
                        for p, row in lines_agg.iterrows()
                    ]

        return trends

    def calculate_time_period_comparison(self, person_metrics_list: List[Dict]) -> Dict:
        """Compare metrics across multiple time periods

        Args:
            person_metrics_list: List of person metrics for different periods

        Returns:
            Dictionary with period comparisons and trends
        """
        if not person_metrics_list:
            return {}

        comparisons = []

        for metrics in person_metrics_list:
            period_name = metrics.get('period_name', 'Unknown')
            github = metrics.get('github', {})

            comparisons.append({
                'period': period_name,
                'prs': github.get('prs_created', 0),
                'reviews': github.get('reviews_given', 0),
                'commits': github.get('commits', 0),
                'lines_changed': github.get('lines_added', 0) + github.get('lines_deleted', 0)
            })

        # Calculate trends (current vs previous)
        trends = {}
        if len(comparisons) >= 2:
            current = comparisons[0]
            previous = comparisons[1]

            for key in ['prs', 'reviews', 'commits']:
                curr_val = current.get(key, 0)
                prev_val = previous.get(key, 0)

                if prev_val > 0:
                    change_percent = ((curr_val - prev_val) / prev_val) * 100
                    direction = 'up' if change_percent > 5 else ('down' if change_percent < -5 else 'stable')
                else:
                    change_percent = 100 if curr_val > 0 else 0
                    direction = 'up' if curr_val > 0 else 'stable'

                trends[key] = {
                    'direction': direction,
                    'change_percent': change_percent
                }

        return {
            'periods': comparisons,
            'trends': trends
        }

    def calculate_team_comparison(self, team_metrics_dict: Dict) -> Dict:
        """Compare metrics across teams

        Args:
            team_metrics_dict: Dictionary mapping team names to their metrics

        Returns:
            Dictionary with team comparison data
        """
        comparison = {}

        for team_name, metrics in team_metrics_dict.items():
            github = metrics.get('github', {})
            jira = metrics.get('jira', {})

            comparison[team_name] = {
                'prs': github.get('pr_count', 0),
                'reviews': github.get('review_count', 0),
                'commits': github.get('commit_count', 0),
                'avg_cycle_time': github.get('avg_cycle_time', 0),
                'jira_throughput': jira.get('throughput', {}).get('weekly_avg', 0),
                'jira_wip': jira.get('wip', {}).get('count', 0),
                'jira_flagged': jira.get('flagged', {}).get('count', 0)
            }

        return comparison

    def get_all_metrics(self):
        """Get all calculated metrics"""
        return {
            'pr_metrics': self.calculate_pr_metrics(),
            'review_metrics': self.calculate_review_metrics(),
            'contributor_metrics': self.calculate_contributor_metrics(),
            'deployment_metrics': self.calculate_deployment_metrics(),
            'jira_metrics': self.calculate_jira_metrics(),
            'updated_at': datetime.now().isoformat(),
        }
