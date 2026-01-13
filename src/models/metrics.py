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
        """Calculate deployment frequency and lead time (legacy method, use calculate_dora_metrics)"""
        # Check if releases DataFrame exists and has data
        if 'releases' not in self.dfs or self.dfs['releases'].empty:
            return {
                'total_deployments': 0,
                'deployments_per_week': 0,
            }

        df = self.dfs['releases']

        # Filter to production releases only
        if 'environment' in df.columns:
            production_releases = df[df['environment'] == 'production']
        else:
            production_releases = df

        if production_releases.empty:
            return {
                'total_deployments': 0,
                'deployments_per_week': 0,
            }

        # Calculate deployment frequency
        if 'published_at' in production_releases.columns:
            production_releases['date_only'] = pd.to_datetime(production_releases['published_at']).dt.date
            days_range = (production_releases['date_only'].max() - production_releases['date_only'].min()).days or 1
        else:
            days_range = 90  # Default

        metrics = {
            'total_deployments': len(production_releases),
            'deployments_per_week': len(production_releases) / (days_range / 7) if days_range > 0 else 0,
        }

        if 'environment' in df.columns:
            metrics['deployments_by_environment'] = df['environment'].value_counts().to_dict()

        return metrics

    def calculate_dora_metrics(self, start_date: datetime = None, end_date: datetime = None,
                              incidents_df: pd.DataFrame = None,
                              issue_to_version_map: Dict = None) -> Dict[str, Any]:
        """Calculate DORA (DevOps Research and Assessment) four key metrics

        Args:
            start_date: Start of measurement period
            end_date: End of measurement period
            incidents_df: Optional DataFrame of production incidents from Jira
            issue_to_version_map: Optional dict mapping issue keys to fix versions (for Jira-based DORA tracking)

        Returns:
            Dictionary with all four DORA metrics:
            - deployment_frequency: How often code is deployed to production
            - lead_time: Time from code commit to production deployment
            - change_failure_rate: % of deployments causing failures
            - mttr: Mean time to restore service after incidents
        """
        # Get releases DataFrame
        releases_df = self.dfs.get('releases', pd.DataFrame())
        prs_df = self.dfs.get('pull_requests', pd.DataFrame())

        # Calculate date range
        if not start_date or not end_date:
            # Use data-driven date range
            if not releases_df.empty and 'published_at' in releases_df.columns:
                dates = pd.to_datetime(releases_df['published_at'])
                end_date = dates.max()
                start_date = dates.min()
            elif not prs_df.empty and 'created_at' in prs_df.columns:
                dates = pd.to_datetime(prs_df['created_at'])
                end_date = dates.max()
                start_date = dates.min()
            else:
                # Default to 90 days
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)

        days_in_period = (end_date - start_date).days or 1

        # 1. DEPLOYMENT FREQUENCY
        deployment_frequency = self._calculate_deployment_frequency(
            releases_df, start_date, end_date, days_in_period
        )

        # 2. LEAD TIME FOR CHANGES
        lead_time = self._calculate_lead_time_for_changes(
            releases_df, prs_df, start_date, end_date,
            issue_to_version_map=issue_to_version_map  # Pass through for Jira version mapping
        )

        # 3. CHANGE FAILURE RATE (requires incident data)
        change_failure_rate = self._calculate_change_failure_rate(
            releases_df, incidents_df
        )

        # 4. MEAN TIME TO RESTORE (requires incident data)
        mttr = self._calculate_mttr(incidents_df)

        # Calculate overall DORA performance level
        dora_level = self._calculate_dora_performance_level(
            deployment_frequency, lead_time, change_failure_rate, mttr
        )

        return {
            'deployment_frequency': deployment_frequency,
            'lead_time': lead_time,
            'change_failure_rate': change_failure_rate,
            'mttr': mttr,
            'dora_level': dora_level,
            'measurement_period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'days': days_in_period
            }
        }

    def _calculate_deployment_frequency(self, releases_df: pd.DataFrame,
                                       start_date: datetime, end_date: datetime,
                                       days_in_period: int) -> Dict[str, Any]:
        """Calculate deployment frequency metric"""
        if releases_df.empty or 'environment' not in releases_df.columns:
            return {
                'total_deployments': 0,
                'per_day': 0,
                'per_week': 0,
                'per_month': 0,
                'level': 'low',
                'badge_class': 'low',
                'trend': {}
            }

        # Filter to production releases only
        production_releases = releases_df[releases_df['environment'] == 'production'].copy()

        if production_releases.empty:
            return {
                'total_deployments': 0,
                'per_day': 0,
                'per_week': 0,
                'per_month': 0,
                'level': 'low',
                'badge_class': 'low',
                'trend': {}
            }

        total = len(production_releases)
        per_day = total / days_in_period if days_in_period > 0 else 0
        per_week = total / (days_in_period / 7) if days_in_period > 0 else 0
        per_month = total / (days_in_period / 30) if days_in_period > 0 else 0

        # Classify performance level
        if per_day >= 1:
            level = 'elite'
            badge_class = 'elite'
        elif per_week >= 1:
            level = 'high'
            badge_class = 'high'
        elif per_month >= 1:
            level = 'medium'
            badge_class = 'medium'
        else:
            level = 'low'
            badge_class = 'low'

        # Calculate trend (weekly breakdown)
        if 'published_at' in production_releases.columns:
            production_releases['week'] = pd.to_datetime(production_releases['published_at']).dt.to_period('W')
            weekly_counts = production_releases.groupby('week').size()
            trend = {str(k): int(v) for k, v in weekly_counts.to_dict().items()}
        else:
            trend = {}

        return {
            'total_deployments': total,
            'per_day': round(per_day, 2),
            'per_week': round(per_week, 2),
            'per_month': round(per_month, 2),
            'level': level,
            'badge_class': badge_class,
            'trend': trend
        }

    def _calculate_lead_time_for_changes(self, releases_df: pd.DataFrame,
                                         prs_df: pd.DataFrame,
                                         start_date: datetime,
                                         end_date: datetime,
                                         issue_to_version_map: Dict = None) -> Dict[str, Any]:
        """Calculate lead time for changes (PR merge to deployment)

        Args:
            releases_df: DataFrame of deployments
            prs_df: DataFrame of merged PRs
            start_date: Start of measurement period
            end_date: End of measurement period
            issue_to_version_map: Optional dict mapping issue keys to fix versions (for Jira-based tracking)
        """
        if releases_df.empty or prs_df.empty:
            return {
                'median_hours': None,
                'median_days': None,
                'p95_hours': None,
                'average_hours': None,
                'sample_size': 0,
                'level': 'low',
                'badge_class': 'low',
                'trend': {}
            }

        # Filter to production releases and merged PRs
        if 'environment' in releases_df.columns:
            production_releases = releases_df[releases_df['environment'] == 'production'].copy()
        else:
            production_releases = releases_df.copy()

        merged_prs = prs_df[prs_df['merged'] == True].copy()

        if production_releases.empty or merged_prs.empty:
            return {
                'median_hours': None,
                'median_days': None,
                'p95_hours': None,
                'average_hours': None,
                'sample_size': 0,
                'level': 'low',
                'badge_class': 'low'
            }

        # Ensure datetime columns
        if 'published_at' in production_releases.columns:
            production_releases['published_at'] = pd.to_datetime(production_releases['published_at'])
        if 'merged_at' in merged_prs.columns:
            merged_prs['merged_at'] = pd.to_datetime(merged_prs['merged_at'])

        # Calculate lead time for each PR (time to next deployment)
        lead_times = []
        for _, pr in merged_prs.iterrows():
            if pd.isna(pr['merged_at']):
                continue

            # NEW: Try Jira issue key matching first (more accurate)
            if issue_to_version_map:
                issue_key = self._extract_issue_key_from_pr(pr)

                if issue_key and issue_key in issue_to_version_map:
                    # Direct mapping: PR → Issue → Fix Version → Deployment
                    fix_version = issue_to_version_map[issue_key]
                    matching_releases = production_releases[
                        production_releases['tag_name'] == fix_version
                    ]

                    if not matching_releases.empty:
                        deploy_time = matching_releases.iloc[0]['published_at']
                        lead_time_hours = (deploy_time - pr['merged_at']).total_seconds() / 3600
                        if lead_time_hours > 0:
                            lead_times.append(lead_time_hours)
                        continue  # Skip fallback logic

            # Fallback: Find the next deployment after this PR was merged (time-based)
            next_deploys = production_releases[
                production_releases['published_at'] > pr['merged_at']
            ].sort_values('published_at')

            if not next_deploys.empty:
                next_deploy = next_deploys.iloc[0]
                lead_time_hours = (next_deploy['published_at'] - pr['merged_at']).total_seconds() / 3600
                if lead_time_hours > 0:  # Sanity check
                    lead_times.append(lead_time_hours)

        if not lead_times:
            return {
                'median_hours': None,
                'median_days': None,
                'p95_hours': None,
                'average_hours': None,
                'sample_size': 0,
                'level': 'low',
                'badge_class': 'low',
                'trend': {}
            }

        median_hours = float(pd.Series(lead_times).median())
        p95_hours = float(pd.Series(lead_times).quantile(0.95))
        average_hours = float(pd.Series(lead_times).mean())

        # Classify performance level
        if median_hours < 24:
            level = 'elite'
            badge_class = 'elite'
        elif median_hours < 168:  # 1 week
            level = 'high'
            badge_class = 'high'
        elif median_hours < 720:  # 1 month
            level = 'medium'
            badge_class = 'medium'
        else:
            level = 'low'
            badge_class = 'low'

        # Calculate trend (weekly breakdown of median lead time)
        trend = {}
        if merged_prs is not None and not merged_prs.empty and 'merged_at' in merged_prs.columns:
            # Create temporary dataframe with PR merge dates and lead times
            pr_lead_times = []
            for _, pr in merged_prs.iterrows():
                if pd.isna(pr['merged_at']):
                    continue

                # Find lead time for this PR (same logic as above)
                pr_lead_time = None

                # Try Jira-based matching
                if issue_to_version_map:
                    issue_key = self._extract_issue_key_from_pr(pr)
                    if issue_key and issue_key in issue_to_version_map:
                        fix_version = issue_to_version_map[issue_key]
                        matching_releases = production_releases[
                            production_releases['tag_name'] == fix_version
                        ]
                        if not matching_releases.empty:
                            deploy_time = matching_releases.iloc[0]['published_at']
                            pr_lead_time = (deploy_time - pr['merged_at']).total_seconds() / 3600

                # Fallback to time-based
                if pr_lead_time is None:
                    next_deploys = production_releases[
                        production_releases['published_at'] > pr['merged_at']
                    ].sort_values('published_at')
                    if not next_deploys.empty:
                        next_deploy = next_deploys.iloc[0]
                        pr_lead_time = (next_deploy['published_at'] - pr['merged_at']).total_seconds() / 3600

                if pr_lead_time is not None and pr_lead_time > 0:
                    pr_lead_times.append({
                        'merged_at': pr['merged_at'],
                        'lead_time_hours': pr_lead_time
                    })

            if pr_lead_times:
                lead_times_df = pd.DataFrame(pr_lead_times)
                lead_times_df['week'] = pd.to_datetime(lead_times_df['merged_at']).dt.to_period('W')

                # Calculate median lead time per week
                weekly_medians = lead_times_df.groupby('week')['lead_time_hours'].median()
                trend = {str(k): round(float(v), 1) for k, v in weekly_medians.to_dict().items()}

        return {
            'median_hours': round(median_hours, 1),
            'median_days': round(median_hours / 24, 1),
            'p95_hours': round(p95_hours, 1),
            'p95_days': round(p95_hours / 24, 1),
            'average_hours': round(average_hours, 1),
            'average_days': round(average_hours / 24, 1),
            'sample_size': len(lead_times),
            'level': level,
            'badge_class': badge_class,
            'trend': trend
        }

    def _extract_issue_key_from_pr(self, pr: pd.Series) -> str:
        """Extract Jira issue key from PR title or branch

        Looks for patterns like:
        - "[PROJ-123] Add feature"
        - "PROJ-123: Fix bug"
        - "feature/PROJ-123-description"

        Args:
            pr: PR data series

        Returns:
            Issue key (e.g., "PROJ-123") or None
        """
        import re

        # Pattern: PROJECT-123 format
        pattern = r'([A-Z]+-\d+)'

        # Check title
        if 'title' in pr and pd.notna(pr['title']):
            match = re.search(pattern, str(pr['title']))
            if match:
                return match.group(1)

        # Check branch name (if available)
        if 'branch' in pr and pd.notna(pr['branch']):
            match = re.search(pattern, str(pr['branch']))
            if match:
                return match.group(1)

        return None

    def _calculate_change_failure_rate(self, releases_df: pd.DataFrame,
                                       incidents_df: pd.DataFrame = None) -> Dict[str, Any]:
        """Calculate change failure rate (% of deployments causing incidents)"""
        if releases_df.empty:
            return {
                'rate_percent': None,
                'failed_deployments': 0,
                'total_deployments': 0,
                'level': 'low',
                'badge_class': 'low',
                'trend': {}
            }

        # Filter to production releases
        if 'environment' in releases_df.columns:
            production_releases = releases_df[releases_df['environment'] == 'production'].copy()
        else:
            production_releases = releases_df.copy()

        total_deployments = len(production_releases)

        if total_deployments == 0:
            return {
                'rate_percent': None,
                'failed_deployments': 0,
                'total_deployments': 0,
                'level': 'low',
                'badge_class': 'low',
                'trend': {}
            }

        # Without incident data, we can't calculate failure rate
        if incidents_df is None or incidents_df.empty:
            return {
                'rate_percent': None,
                'failed_deployments': None,
                'total_deployments': total_deployments,
                'level': 'unknown',
                'badge_class': 'low',
                'note': 'Incident data not available',
                'trend': {}
            }

        # Correlate incidents to deployments
        # Method 1: Direct tag matching (if incident has related_deployment field)
        # Method 2: Time-based correlation (incident created within 24h of deployment)

        deployments_with_incidents = set()
        correlation_window_hours = 24

        # Ensure datetime columns
        if 'published_at' in production_releases.columns:
            production_releases['published_at'] = pd.to_datetime(production_releases['published_at'])

        incidents_df = incidents_df.copy()
        if 'created' in incidents_df.columns:
            incidents_df['created'] = pd.to_datetime(incidents_df['created'])

        for _, incident in incidents_df.iterrows():
            incident_created = incident.get('created')
            if pd.isna(incident_created):
                continue

            # Method 1: Check for direct deployment tag reference
            related_deployment = incident.get('related_deployment')
            if related_deployment and 'tag_name' in production_releases.columns:
                # Match exact Fix Version name: "Live - 6/Oct/2025"
                matching_deploys = production_releases[
                    production_releases['tag_name'] == related_deployment
                ]
                for deploy_tag in matching_deploys['tag_name']:
                    deployments_with_incidents.add(deploy_tag)

            # Method 2: Time-based correlation (incident within correlation window after deployment)
            if 'published_at' in production_releases.columns:
                for _, deploy in production_releases.iterrows():
                    deploy_time = deploy['published_at']
                    if pd.notna(deploy_time):
                        # Check if incident occurred within window after deployment
                        time_diff_hours = (incident_created - deploy_time).total_seconds() / 3600
                        if 0 <= time_diff_hours <= correlation_window_hours:
                            deployments_with_incidents.add(deploy.get('tag_name', ''))

        failed_deployments = len(deployments_with_incidents)
        cfr = (failed_deployments / total_deployments) * 100 if total_deployments > 0 else 0

        # Classify performance level (DORA thresholds)
        if cfr < 15:
            level = 'elite'
            badge_class = 'elite'
        elif cfr < 16:
            level = 'high'
            badge_class = 'high'
        elif cfr < 30:
            level = 'medium'
            badge_class = 'medium'
        else:
            level = 'low'
            badge_class = 'low'

        # Calculate trend (weekly breakdown of failure rate)
        trend = {}
        if not production_releases.empty and 'published_at' in production_releases.columns:
            production_releases['week'] = pd.to_datetime(production_releases['published_at']).dt.to_period('W')

            # Count total deployments per week
            weekly_total = production_releases.groupby('week').size()

            # Count failed deployments per week
            failed_releases = production_releases[
                production_releases['tag_name'].isin(deployments_with_incidents)
            ]
            weekly_failed = failed_releases.groupby('week').size() if not failed_releases.empty else pd.Series()

            # Calculate CFR per week
            for week in weekly_total.index:
                total = weekly_total[week]
                failed = weekly_failed.get(week, 0)
                cfr_week = (failed / total * 100) if total > 0 else 0
                trend[str(week)] = round(cfr_week, 1)

        return {
            'rate_percent': round(cfr, 1),
            'failed_deployments': failed_deployments,
            'total_deployments': total_deployments,
            'incidents_count': len(incidents_df),
            'level': level,
            'badge_class': badge_class,
            'correlation_window_hours': correlation_window_hours,
            'trend': trend
        }

    def _calculate_mttr(self, incidents_df: pd.DataFrame = None) -> Dict[str, Any]:
        """Calculate Mean Time to Restore (incident resolution time)"""
        if incidents_df is None or incidents_df.empty:
            return {
                'median_hours': None,
                'median_days': None,
                'average_hours': None,
                'p95_hours': None,
                'sample_size': 0,
                'level': 'unknown',
                'badge_class': 'low',
                'note': 'Incident data not available',
                'trend': {}
            }

        # Calculate resolution times for resolved incidents
        resolution_times = []

        for _, incident in incidents_df.iterrows():
            # Check for resolution_time_hours field (from Jira collector)
            if 'resolution_time_hours' in incident and pd.notna(incident['resolution_time_hours']):
                resolution_times.append(float(incident['resolution_time_hours']))
            # Fallback: calculate from created/resolved dates
            elif 'created' in incident and 'resolved' in incident:
                created = incident['created']
                resolved = incident['resolved']
                if pd.notna(created) and pd.notna(resolved):
                    created_dt = pd.to_datetime(created)
                    resolved_dt = pd.to_datetime(resolved)
                    hours = (resolved_dt - created_dt).total_seconds() / 3600
                    if hours > 0:  # Sanity check
                        resolution_times.append(hours)

        if not resolution_times:
            return {
                'median_hours': None,
                'median_days': None,
                'average_hours': None,
                'p95_hours': None,
                'sample_size': 0,
                'level': 'unknown',
                'badge_class': 'low',
                'note': 'No resolved incidents in period',
                'trend': {}
            }

        # Calculate statistics
        median_hours = float(pd.Series(resolution_times).median())
        average_hours = float(pd.Series(resolution_times).mean())
        p95_hours = float(pd.Series(resolution_times).quantile(0.95))

        # Classify performance level (DORA thresholds)
        if median_hours < 1:
            level = 'elite'
            badge_class = 'elite'
        elif median_hours < 24:
            level = 'high'
            badge_class = 'high'
        elif median_hours < 168:  # 1 week
            level = 'medium'
            badge_class = 'medium'
        else:
            level = 'low'
            badge_class = 'low'

        # Calculate trend (weekly breakdown of median MTTR)
        trend = {}
        if not incidents_df.empty and 'resolved' in incidents_df.columns:
            # Create temporary dataframe with resolved incidents and their resolution times
            incident_times = []
            for _, incident in incidents_df.iterrows():
                resolved_dt = incident.get('resolved')
                if pd.notna(resolved_dt):
                    # Get resolution time for this incident
                    if 'resolution_time_hours' in incident and pd.notna(incident['resolution_time_hours']):
                        res_time = float(incident['resolution_time_hours'])
                    elif 'created' in incident and pd.notna(incident['created']):
                        created_dt = pd.to_datetime(incident['created'])
                        resolved_dt_parsed = pd.to_datetime(resolved_dt)
                        res_time = (resolved_dt_parsed - created_dt).total_seconds() / 3600
                    else:
                        continue

                    if res_time > 0:
                        incident_times.append({
                            'resolved': resolved_dt,
                            'resolution_time_hours': res_time
                        })

            if incident_times:
                incidents_trend_df = pd.DataFrame(incident_times)
                incidents_trend_df['week'] = pd.to_datetime(incidents_trend_df['resolved']).dt.to_period('W')

                # Calculate median resolution time per week
                weekly_medians = incidents_trend_df.groupby('week')['resolution_time_hours'].median()
                trend = {str(k): round(float(v), 1) for k, v in weekly_medians.to_dict().items()}

        return {
            'median_hours': round(median_hours, 1),
            'median_days': round(median_hours / 24, 1),
            'average_hours': round(average_hours, 1),
            'average_days': round(average_hours / 24, 1),
            'p95_hours': round(p95_hours, 1),
            'p95_days': round(p95_hours / 24, 1),
            'sample_size': len(resolution_times),
            'level': level,
            'badge_class': badge_class,
            'trend': trend
        }

    def _calculate_dora_performance_level(self, deployment_freq: Dict,
                                          lead_time: Dict,
                                          cfr: Dict,
                                          mttr: Dict) -> Dict[str, str]:
        """Calculate overall DORA performance level based on all four metrics"""
        # Count metrics by level
        levels = {
            'elite': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }

        for metric in [deployment_freq, lead_time, cfr, mttr]:
            level = metric.get('level', 'low')
            if level in levels:
                levels[level] += 1

        # Determine overall level (must excel in multiple areas)
        if levels['elite'] >= 3:
            overall_level = 'Elite'
            description = 'Top performers! Fastest delivery with highest stability.'
        elif levels['elite'] >= 2 or (levels['elite'] + levels['high']) >= 3:
            overall_level = 'High'
            description = 'Strong performance across all DORA metrics.'
        elif levels['low'] <= 1:
            overall_level = 'Medium'
            description = 'Good foundation, opportunities to improve velocity.'
        else:
            overall_level = 'Low'
            description = 'Focus on automation and reducing cycle times.'

        return {
            'level': overall_level,
            'description': description,
            'breakdown': levels
        }

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

    def calculate_team_metrics(self, team_name: str, team_config: Dict, jira_filter_results: Dict = None,
                              issue_to_version_map: Dict = None) -> Dict:
        """Calculate team-level metrics

        Args:
            team_name: Name of the team
            team_config: Team configuration with members
            jira_filter_results: Results from Jira filter collection
            issue_to_version_map: Optional dict mapping issue keys to fix versions (for Jira-based DORA tracking)

        Returns:
            Dictionary with team metrics
        """
        # Extract GitHub members - support both new unified format and old format
        github_members = []
        if 'members' in team_config and isinstance(team_config.get('members'), list):
            # New format: unified members list
            for member in team_config['members']:
                if isinstance(member, dict) and member.get('github'):
                    github_members.append(member['github'])
        else:
            # Old format: separate arrays under github key
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
            # Handle empty DataFrames gracefully
            if not team_dfs['pull_requests'].empty and 'author' in team_dfs['pull_requests'].columns:
                member_prs = team_dfs['pull_requests'][team_dfs['pull_requests']['author'] == member]
            else:
                member_prs = pd.DataFrame()

            if not team_dfs['reviews'].empty and 'reviewer' in team_dfs['reviews'].columns:
                member_reviews = team_dfs['reviews'][team_dfs['reviews']['reviewer'] == member]
            else:
                member_reviews = pd.DataFrame()

            if not team_dfs['commits'].empty and 'author' in team_dfs['commits'].columns:
                member_commits = team_dfs['commits'][team_dfs['commits']['author'] == member]
            else:
                member_commits = pd.DataFrame()

            member_trends[member] = {
                'prs': len(member_prs),
                'reviews': len(member_reviews),
                'commits': len(member_commits),
                'lines_added': member_commits['additions'].sum() if not member_commits.empty and 'additions' in member_commits.columns else 0,
                'lines_deleted': member_commits['deletions'].sum() if not member_commits.empty and 'deletions' in member_commits.columns else 0,
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
                        created_dt = pd.to_datetime(created_date, utc=True)
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
                        resolved_dt = pd.to_datetime(resolved_date, utc=True)
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
                            created_dt = pd.to_datetime(created_date, utc=True)
                            if created_dt >= ninety_days_ago:
                                week = created_dt.strftime('%Y-W%U')
                                scope_by_week_created[week] = scope_by_week_created.get(week, 0) + 1
                        except:
                            pass  # Skip invalid dates

                    resolved_date = issue.get('resolved')
                    if resolved_date:
                        try:
                            resolved_dt = pd.to_datetime(resolved_date, utc=True)
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

        # Calculate DORA metrics (releases are team-level, not filtered to individual members)
        # Create temporary calculator with releases included
        dora_dfs = {
            'pull_requests': team_dfs['pull_requests'],
            'releases': self.dfs.get('releases', pd.DataFrame()),  # Use full team releases
            'commits': team_dfs['commits']
        }
        dora_calculator = MetricsCalculator(dora_dfs)

        # Convert incidents from jira_filter_results to DataFrame for DORA calculation
        incidents_df = None
        if jira_filter_results and 'incidents' in jira_filter_results:
            incidents_list = jira_filter_results['incidents']
            if incidents_list:
                incidents_df = pd.DataFrame(incidents_list)
                print(f"   - Passing {len(incidents_df)} incidents to DORA calculation")

        dora_metrics = dora_calculator.calculate_dora_metrics(
            issue_to_version_map=issue_to_version_map,  # Pass through for lead time calculation
            incidents_df=incidents_df  # Pass incidents for CFR & MTTR
        )

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
            'jira': jira_metrics,
            'dora': dora_metrics
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
                    jira_df['resolved'] = pd.to_datetime(jira_df['resolved'], errors='coerce', utc=True)

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

    @staticmethod
    def normalize(value, min_val, max_val):
        """Normalize a value to 0-100 scale"""
        if max_val == min_val:
            return 50.0  # All values equal, return middle score
        return ((value - min_val) / (max_val - min_val)) * 100

    @staticmethod
    def calculate_performance_score(metrics, all_metrics_list, team_size=None, weights=None):
        """
        Calculate overall performance score (0-100) for a team or person.

        Args:
            metrics: Dict with individual metrics (prs, reviews, commits, etc.)
            all_metrics_list: List of all metrics dicts for normalization
            team_size: Optional team size for normalizing volume metrics (per-capita)
            weights: Optional dict of metric weights (defaults to config or balanced defaults)

        Returns:
            Float score between 0-100
        """
        if weights is None:
            # Try to load from config, fall back to defaults
            try:
                from ..config import Config
                config = Config()
                weights = config.performance_weights
            except Exception:
                # Fall back to default weights if config not available
                weights = {
                    'prs': 0.20,
                    'reviews': 0.20,
                    'commits': 0.15,
                    'cycle_time': 0.15,  # Lower is better
                    'jira_completed': 0.20,
                    'merge_rate': 0.10
                }

        # If team_size provided, normalize volume metrics to per-capita before scoring
        if team_size and team_size > 0:
            metrics = metrics.copy()  # Don't modify original
            metrics['prs'] = metrics.get('prs', 0) / team_size
            metrics['reviews'] = metrics.get('reviews', 0) / team_size
            metrics['commits'] = metrics.get('commits', 0) / team_size
            metrics['jira_completed'] = metrics.get('jira_completed', 0) / team_size

            # Also normalize all_metrics_list for comparison
            all_metrics_list = [
                {
                    **m,
                    'prs': m.get('prs', 0) / m.get('team_size', team_size) if m.get('team_size', team_size) > 0 else 0,
                    'reviews': m.get('reviews', 0) / m.get('team_size', team_size) if m.get('team_size', team_size) > 0 else 0,
                    'commits': m.get('commits', 0) / m.get('team_size', team_size) if m.get('team_size', team_size) > 0 else 0,
                    'jira_completed': m.get('jira_completed', 0) / m.get('team_size', team_size) if m.get('team_size', team_size) > 0 else 0,
                }
                for m in all_metrics_list
            ]

        # Extract all values for normalization
        prs_values = [m.get('prs', 0) for m in all_metrics_list]
        reviews_values = [m.get('reviews', 0) for m in all_metrics_list]
        commits_values = [m.get('commits', 0) for m in all_metrics_list]
        cycle_time_values = [m.get('cycle_time', 0) for m in all_metrics_list if m.get('cycle_time', 0) > 0]
        jira_values = [m.get('jira_completed', 0) for m in all_metrics_list]
        merge_rate_values = [m.get('merge_rate', 0) for m in all_metrics_list]

        # Normalize each metric
        score = 0.0

        if prs_values and max(prs_values) > 0:
            prs_score = MetricsCalculator.normalize(
                metrics.get('prs', 0),
                min(prs_values),
                max(prs_values)
            )
            score += prs_score * weights['prs']

        if reviews_values and max(reviews_values) > 0:
            reviews_score = MetricsCalculator.normalize(
                metrics.get('reviews', 0),
                min(reviews_values),
                max(reviews_values)
            )
            score += reviews_score * weights['reviews']

        if commits_values and max(commits_values) > 0:
            commits_score = MetricsCalculator.normalize(
                metrics.get('commits', 0),
                min(commits_values),
                max(commits_values)
            )
            score += commits_score * weights['commits']

        # Cycle time: lower is better, so invert the score
        if cycle_time_values and metrics.get('cycle_time', 0) > 0:
            cycle_time_score = MetricsCalculator.normalize(
                metrics.get('cycle_time', 0),
                min(cycle_time_values),
                max(cycle_time_values)
            )
            score += (100 - cycle_time_score) * weights['cycle_time']

        if jira_values and max(jira_values) > 0:
            jira_score = MetricsCalculator.normalize(
                metrics.get('jira_completed', 0),
                min(jira_values),
                max(jira_values)
            )
            score += jira_score * weights['jira_completed']

        if merge_rate_values and max(merge_rate_values) > 0:
            merge_rate_score = MetricsCalculator.normalize(
                metrics.get('merge_rate', 0),
                min(merge_rate_values),
                max(merge_rate_values)
            )
            score += merge_rate_score * weights['merge_rate']

        return round(score, 1)
