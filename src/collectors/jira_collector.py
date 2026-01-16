from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, cast

import pandas as pd
import urllib3
from jira import JIRA, Issue

from src.utils.logging import get_logger

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class JiraCollector:
    def __init__(
        self,
        server: str,
        username: str,
        api_token: str,
        project_keys: List[str],
        team_members: Optional[List[str]] = None,
        days_back: int = 90,
        verify_ssl: bool = True,
        timeout: int = 120,
    ):
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
            "server": server,
            "verify": verify_ssl,
            "timeout": timeout,  # Add configurable timeout
            "headers": {"Authorization": f"Bearer {api_token}"},
        }
        self.jira = JIRA(options=options)
        self.project_keys = project_keys
        self.team_members = team_members or []
        self.days_back = days_back
        # Make since_date timezone-aware (UTC) for comparison with Fix Version dates
        from datetime import timezone

        self.since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        self.out = get_logger("team_metrics.collectors.jira")

    def collect_all_metrics(self):
        """Collect all metrics from Jira"""
        all_data: Dict[str, List[Any]] = {"issues": [], "sprints": [], "worklogs": []}

        for project_key in self.project_keys:
            self.out.info(f"Collecting Jira metrics for project {project_key}...")

            all_data["issues"].extend(self.collect_issue_metrics(project_key))
            all_data["worklogs"].extend(self.collect_worklog_metrics(project_key))

        return all_data

    def collect_issue_metrics(self, project_key: str):
        """Collect issue metrics"""
        issues = []

        # Build JQL query with team member filter if specified
        jql = f"project = {project_key} AND (created >= -{self.days_back}d OR resolved >= -{self.days_back}d OR (statusCategory != Done AND updated >= -{self.days_back}d))"
        if self.team_members:
            members_str = ", ".join(self.team_members)
            jql += f" AND (assignee in ({members_str}) OR reporter in ({members_str}))"
        jql += " ORDER BY updated DESC"

        try:
            jira_issues = cast(List[Issue], self.jira.search_issues(jql, maxResults=1000, expand="changelog"))

            for issue in jira_issues:
                issue_data = {
                    "key": issue.key,
                    "project": project_key,
                    "type": issue.fields.issuetype.name,
                    "status": issue.fields.status.name,
                    "priority": issue.fields.priority.name if issue.fields.priority else None,
                    "assignee": issue.fields.assignee.name if issue.fields.assignee else None,
                    "reporter": issue.fields.reporter.name if issue.fields.reporter else None,
                    "created": issue.fields.created,
                    "updated": issue.fields.updated,
                    "resolved": issue.fields.resolutiondate,
                    "summary": issue.fields.summary,
                    "story_points": getattr(issue.fields, "customfield_10016", None),
                    "fix_versions": (
                        [v.name for v in issue.fields.fixVersions] if hasattr(issue.fields, "fixVersions") else []
                    ),
                }

                # Calculate cycle time (created to resolved)
                if issue.fields.resolutiondate:
                    created = datetime.strptime(issue.fields.created, "%Y-%m-%dT%H:%M:%S.%f%z")
                    resolved = datetime.strptime(issue.fields.resolutiondate, "%Y-%m-%dT%H:%M:%S.%f%z")
                    issue_data["cycle_time_hours"] = (resolved - created).total_seconds() / 3600
                else:
                    issue_data["cycle_time_hours"] = None

                # Get time in each status from changelog
                status_times = self._calculate_status_times(issue)
                issue_data.update(status_times)

                issues.append(issue_data)

        except Exception as e:
            self.out.error(f"Error collecting issues for {project_key}: {e}")

        return issues

    def _calculate_status_times(self, issue):
        """Calculate time spent in each status"""
        status_times = {
            "time_in_todo_hours": 0.0,
            "time_in_progress_hours": 0.0,
            "time_in_review_hours": 0.0,
        }

        if not hasattr(issue, "changelog"):
            return status_times

        current_status = None
        last_transition_time = datetime.strptime(issue.fields.created, "%Y-%m-%dT%H:%M:%S.%f%z")

        for history in issue.changelog.histories:
            for item in history.items:
                if item.field == "status":
                    transition_time = datetime.strptime(history.created, "%Y-%m-%dT%H:%M:%S.%f%z")

                    if current_status:
                        time_diff = (transition_time - last_transition_time).total_seconds() / 3600

                        if "to do" in current_status.lower() or "backlog" in current_status.lower():
                            status_times["time_in_todo_hours"] += time_diff
                        elif "in progress" in current_status.lower() or "doing" in current_status.lower():
                            status_times["time_in_progress_hours"] += time_diff
                        elif "review" in current_status.lower() or "testing" in current_status.lower():
                            status_times["time_in_review_hours"] += time_diff

                    current_status = item.toString
                    last_transition_time = transition_time

        # Add time in current status
        if current_status:
            time_diff = (datetime.now(last_transition_time.tzinfo) - last_transition_time).total_seconds() / 3600

            if "to do" in current_status.lower() or "backlog" in current_status.lower():
                status_times["time_in_todo_hours"] += time_diff
            elif "in progress" in current_status.lower() or "doing" in current_status.lower():
                status_times["time_in_progress_hours"] += time_diff
            elif "review" in current_status.lower() or "testing" in current_status.lower():
                status_times["time_in_review_hours"] += time_diff

        return status_times

    def collect_worklog_metrics(self, project_key: str):
        """Collect worklog (time tracking) metrics"""
        worklogs = []

        jql = f"project = {project_key} AND worklogDate >= -{self.days_back}d"

        try:
            issues = self.jira.search_issues(jql, maxResults=1000)

            for issue in issues:
                issue_worklogs = self.jira.worklogs(issue.key)

                for worklog in issue_worklogs:
                    worklogs.append(
                        {
                            "issue_key": issue.key,
                            "project": project_key,
                            "author": worklog.author.name,
                            "time_spent_hours": worklog.timeSpentSeconds / 3600,
                            "started": worklog.started,
                        }
                    )

        except Exception as e:
            self.out.error(f"Error collecting worklogs for {project_key}: {e}")

        return worklogs

    def collect_person_issues(
        self, jira_username: str, days_back: int = 90, expand_changelog: bool = True
    ) -> List[Dict]:
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

            self.out.info(f"Querying Jira for {jira_username}: {jql}", indent=1)

            # Execute query with optional changelog for status transitions
            expand = "changelog" if expand_changelog else None
            jira_issues = cast(List[Issue], self.jira.search_issues(jql, maxResults=1000, expand=expand))

            for issue in jira_issues:
                issue_data = {
                    "key": issue.key,
                    "project": issue.fields.project.key,
                    "type": issue.fields.issuetype.name,
                    "status": issue.fields.status.name,
                    "priority": issue.fields.priority.name if issue.fields.priority else None,
                    "assignee": issue.fields.assignee.name if issue.fields.assignee else None,
                    "reporter": issue.fields.reporter.name if issue.fields.reporter else None,
                    "created": issue.fields.created,
                    "updated": issue.fields.updated,
                    "resolved": issue.fields.resolutiondate,
                    "summary": issue.fields.summary,
                    "story_points": getattr(issue.fields, "customfield_10016", None),
                    "labels": issue.fields.labels if hasattr(issue.fields, "labels") else [],
                    "flagged": any(
                        "blocked" in label.lower() or "impediment" in label.lower()
                        for label in getattr(issue.fields, "labels", [])
                    ),
                }

                # Calculate cycle time (created to resolved)
                if issue.fields.resolutiondate:
                    created = datetime.strptime(issue.fields.created, "%Y-%m-%dT%H:%M:%S.%f%z")
                    resolved = datetime.strptime(issue.fields.resolutiondate, "%Y-%m-%dT%H:%M:%S.%f%z")
                    issue_data["cycle_time_hours"] = (resolved - created).total_seconds() / 3600
                else:
                    issue_data["cycle_time_hours"] = None

                # Calculate time in current status (for WIP items)
                if issue.fields.resolutiondate is None:
                    updated = datetime.strptime(issue.fields.updated, "%Y-%m-%dT%H:%M:%S.%f%z")
                    now = datetime.now(updated.tzinfo)
                    issue_data["days_in_current_status"] = (now - updated).days
                else:
                    issue_data["days_in_current_status"] = None

                # Get time in each status from changelog
                status_times = self._calculate_status_times(issue)
                issue_data.update(status_times)

                issues.append(issue_data)

        except Exception as e:
            self.out.error(f"Error collecting issues for {jira_username}: {e}", indent=1)
            raise  # Re-raise so caller can handle

        return issues

    def collect_filter_issues(self, filter_id: int, add_time_constraint: bool = False):
        """Execute filter by ID and return issues

        Args:
            filter_id: Jira filter ID
            add_time_constraint: If True, adds dynamic time constraint based on days_back

        Returns:
            List of issue dictionaries
        """
        issues: List[Dict] = []

        try:
            # Get filter and execute its JQL
            jira_filter = self.jira.filter(str(filter_id))
            jql = jira_filter.jql if hasattr(jira_filter, "jql") else None

            if not jql:
                self.out.warning(f"Could not get JQL for filter {filter_id}")
                return issues

            self.out.info(f"Executing filter {filter_id}: {jira_filter.name}", indent=1)

            # Add time constraint if requested (for scope filters that return too many results)
            if add_time_constraint:
                time_clause = f"(created >= -{self.days_back}d OR resolved >= -{self.days_back}d)"
                # Insert the time constraint before ORDER BY if present, or at the end
                if "ORDER BY" in jql.upper():
                    parts = jql.split("ORDER BY")
                    jql = f"{parts[0].strip()} AND {time_clause} ORDER BY {parts[1].strip()}"
                else:
                    jql = f"{jql} AND {time_clause}"
                self.out.info(f"Added time constraint: {time_clause}", indent=1)

            # Execute the filter's JQL
            jira_issues = cast(List[Issue], self.jira.search_issues(jql, maxResults=1000, expand="changelog"))

            for issue in jira_issues:
                issue_data = {
                    "key": issue.key,
                    "project": issue.fields.project.key,
                    "type": issue.fields.issuetype.name,
                    "status": issue.fields.status.name,
                    "priority": issue.fields.priority.name if issue.fields.priority else None,
                    "assignee": issue.fields.assignee.name if issue.fields.assignee else None,
                    "reporter": issue.fields.reporter.name if issue.fields.reporter else None,
                    "created": issue.fields.created,
                    "updated": issue.fields.updated,
                    "resolved": issue.fields.resolutiondate,
                    "summary": issue.fields.summary,
                    "story_points": getattr(issue.fields, "customfield_10016", None),
                    "labels": issue.fields.labels if hasattr(issue.fields, "labels") else [],
                    "flagged": any(
                        "blocked" in label.lower() or "impediment" in label.lower()
                        for label in getattr(issue.fields, "labels", [])
                    ),
                    "fix_versions": (
                        [v.name for v in issue.fields.fixVersions] if hasattr(issue.fields, "fixVersions") else []
                    ),
                }

                # Calculate cycle time
                if issue.fields.resolutiondate:
                    created = datetime.strptime(issue.fields.created, "%Y-%m-%dT%H:%M:%S.%f%z")
                    resolved = datetime.strptime(issue.fields.resolutiondate, "%Y-%m-%dT%H:%M:%S.%f%z")
                    issue_data["cycle_time_hours"] = (resolved - created).total_seconds() / 3600
                else:
                    issue_data["cycle_time_hours"] = None

                # Calculate time in current status (for WIP items)
                if issue.fields.resolutiondate is None:
                    updated = datetime.strptime(issue.fields.updated, "%Y-%m-%dT%H:%M:%S.%f%z")
                    now = datetime.now(updated.tzinfo)
                    issue_data["days_in_current_status"] = (now - updated).days
                else:
                    issue_data["days_in_current_status"] = None

                # Get time in each status
                status_times = self._calculate_status_times(issue)
                issue_data.update(status_times)

                issues.append(issue_data)

        except Exception as e:
            self.out.error(f"Error collecting filter {filter_id}: {e}")

        return issues

    def _collect_single_filter(self, filter_name: str, filter_id: int) -> tuple:
        """Collect issues for a single filter (for parallel execution)

        Args:
            filter_name: Name of the filter (e.g., 'bugs', 'wip')
            filter_id: JIRA filter ID

        Returns:
            Tuple of (filter_name, issues_list, error_message)
            - On success: (filter_name, issues, None)
            - On failure: (filter_name, [], error_string)
        """
        try:
            # Determine if time constraint needed
            filters_needing_time_constraint = ["scope", "bugs"]
            add_time_constraint = filter_name in filters_needing_time_constraint

            # Collect issues
            issues = self.collect_filter_issues(filter_id, add_time_constraint=add_time_constraint)

            return (filter_name, issues, None)

        except Exception as e:
            import traceback

            error_detail = f"{e}\n{traceback.format_exc()}"
            return (filter_name, [], error_detail)

    def collect_team_filters(
        self, filter_ids: Dict[str, int], parallel: bool = True, max_workers: int = 4
    ) -> Dict[str, List]:
        """Collect all team filters (with optional parallelization)

        Args:
            filter_ids: Dictionary mapping filter names to filter IDs
                       Example: {'completed_12weeks': 12345, 'wip': 12346}
            parallel: Whether to use parallel collection (default: True)
            max_workers: Number of concurrent filter collections (default: 4)

        Returns:
            Dictionary mapping filter names to lists of issues
        """
        filter_results: Dict[str, List[Dict]] = {}

        # Determine if we should use parallel collection
        use_parallel = parallel and len(filter_ids) > 1

        if use_parallel:
            self.out.info(f"Collecting {len(filter_ids)} filters in parallel ({max_workers} workers)", emoji="⚡")
            self.out.info("")

            # Limit workers to filter count
            actual_workers = min(len(filter_ids), max_workers)

            with ThreadPoolExecutor(max_workers=actual_workers) as executor:
                # Submit all filter collection jobs
                futures = {
                    executor.submit(self._collect_single_filter, filter_name, filter_id): filter_name
                    for filter_name, filter_id in filter_ids.items()
                }

                # Collect results as they complete
                completed = 0
                total = len(filter_ids)

                for future in as_completed(futures):
                    filter_name = futures[future]
                    completed += 1

                    try:
                        result_filter_name, issues, error = future.result()

                        if error:
                            # Log error but continue
                            self.out.error(
                                f"[{datetime.now().strftime('%H:%M:%S')}] "
                                f"Progress: {completed}/{total} - ✗ {filter_name}: {error[:80]}"
                            )
                            filter_results[filter_name] = []
                        else:
                            # Success
                            percent = (completed / total) * 100 if total > 0 else 0
                            self.out.info(
                                f"[{datetime.now().strftime('%H:%M:%S')}] "
                                f"Progress: {completed}/{total} ({percent:.1f}%) - "
                                f"✓ {filter_name} ({len(issues)} issues)"
                            )
                            filter_results[filter_name] = issues

                    except Exception as e:
                        # Unexpected error in future handling
                        self.out.error(
                            f"[{datetime.now().strftime('%H:%M:%S')}] "
                            f"Progress: {completed}/{total} - ✗ {filter_name}: {e}"
                        )
                        filter_results[filter_name] = []

            self.out.info("")  # Blank line after progress

        else:
            # Sequential fallback
            self.out.info(f"Collecting {len(filter_ids)} filters sequentially", emoji="ℹ️")
            self.out.info("")

            # Filters that should have time constraints added
            filters_needing_time_constraint = ["scope", "bugs"]

            for filter_name, filter_id in filter_ids.items():
                self.out.info(f"Collecting filter '{filter_name}' (ID: {filter_id})...")

                add_time_constraint = filter_name in filters_needing_time_constraint
                issues = self.collect_filter_issues(filter_id, add_time_constraint=add_time_constraint)

                filter_results[filter_name] = issues
                self.out.info(f"Found {len(issues)} issues", indent=1)

        return filter_results

    def calculate_throughput(self, issues: List) -> Dict:
        """Calculate throughput from completed issues

        Args:
            issues: List of issue dictionaries

        Returns:
            Dictionary with throughput metrics
        """
        if not issues:
            return {"weekly_throughput": 0, "total_completed": 0}

        df = pd.DataFrame(issues)

        # Filter to resolved issues
        df_resolved = df[df["resolved"].notna()].copy()

        if df_resolved.empty:
            return {"weekly_throughput": 0, "total_completed": 0}

        # Convert resolved date to datetime
        df_resolved["resolved_date"] = pd.to_datetime(df_resolved["resolved"])
        df_resolved["week"] = df_resolved["resolved_date"].dt.to_period("W")

        # Count issues per week
        weekly_counts = df_resolved.groupby("week").size()

        return {
            "weekly_throughput": weekly_counts.mean() if len(weekly_counts) > 0 else 0,
            "total_completed": len(df_resolved),
            "by_week": weekly_counts.to_dict(),
        }

    def calculate_time_since_wip(self, issues: List) -> Dict:
        """Calculate days in WIP status

        Args:
            issues: List of WIP issue dictionaries

        Returns:
            Dictionary with WIP age metrics
        """
        if not issues:
            return {"avg_days": 0, "max_days": 0, "distribution": {}}

        ages = [
            issue.get("days_in_current_status", 0)
            for issue in issues
            if issue.get("days_in_current_status") is not None
        ]

        if not ages:
            return {"avg_days": 0, "max_days": 0, "distribution": {}}

        # Create age distribution buckets
        distribution = {
            "0-3 days": len([a for a in ages if 0 <= a <= 3]),
            "4-7 days": len([a for a in ages if 4 <= a <= 7]),
            "8-14 days": len([a for a in ages if 8 <= a <= 14]),
            "15+ days": len([a for a in ages if a >= 15]),
        }

        return {
            "avg_days": sum(ages) / len(ages) if ages else 0,
            "max_days": max(ages) if ages else 0,
            "min_days": min(ages) if ages else 0,
            "distribution": distribution,
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
            if issue.get("flagged"):
                flagged.append(
                    {
                        "key": issue["key"],
                        "summary": issue["summary"],
                        "assignee": issue.get("assignee", "Unassigned"),
                        "status": issue["status"],
                        "days_blocked": issue.get("days_in_current_status", 0),
                    }
                )

        return flagged

    def collect_incidents(
        self,
        filter_id: Optional[int] = None,
        project_keys: Optional[List[str]] = None,
        correlation_window_hours: int = 24,
    ) -> List[Dict]:
        """Collect production incidents from Jira

        Incidents can be identified by:
        - Specific Jira filter (if filter_id provided)
        - Issue type = "Incident" or "Bug" with priority Blocker/Critical
        - Labels containing "production", "incident", "outage", "p1", "sev1"

        Args:
            filter_id: Optional Jira filter ID for incidents
            project_keys: List of project keys to search (uses self.project_keys if None)
            correlation_window_hours: Hours after deployment to correlate incidents (default: 24)

        Returns:
            List of incident dictionaries with resolution times and deployment correlation
        """
        incidents = []

        if filter_id:
            # Use specific incident filter
            self.out.info(f"Collecting incidents from filter {filter_id}...")
            incidents = self.collect_filter_issues(filter_id, add_time_constraint=True)
        else:
            # Build JQL to find production incidents
            projects = project_keys or self.project_keys
            project_clause = " OR ".join([f"project = {pk}" for pk in projects])

            # Incident identification criteria
            jql = f"({project_clause}) AND "
            jql += f"(created >= -{self.days_back}d OR resolved >= -{self.days_back}d) AND ("

            # Criteria 1: Issue type is Incident
            jql += 'issuetype = "Incident" OR '

            # Criteria 2: High priority bugs (Blocker, Critical)
            jql += '(issuetype = "Bug" AND priority in (Blocker, Critical, Highest)) OR '

            # Criteria 3: Production-related labels
            jql += 'labels in (production, incident, outage, p1, sev1, "production-incident")'

            jql += ") ORDER BY created DESC"

            self.out.info(f"Collecting incidents with JQL: {jql[:150]}...")

            try:
                jira_issues = cast(List[Issue], self.jira.search_issues(jql, maxResults=500, expand="changelog"))
                self.out.info(f"Found {len(jira_issues)} potential incidents", indent=1)

                for issue in jira_issues:
                    incident_data = {
                        "key": issue.key,
                        "project": issue.fields.project.key,
                        "type": issue.fields.issuetype.name,
                        "status": issue.fields.status.name,
                        "priority": issue.fields.priority.name if issue.fields.priority else None,
                        "assignee": issue.fields.assignee.name if issue.fields.assignee else None,
                        "reporter": issue.fields.reporter.name if issue.fields.reporter else None,
                        "created": issue.fields.created,
                        "updated": issue.fields.updated,
                        "resolved": issue.fields.resolutiondate,
                        "summary": issue.fields.summary,
                        "labels": issue.fields.labels if hasattr(issue.fields, "labels") else [],
                        "description": issue.fields.description if hasattr(issue.fields, "description") else None,
                        "fix_versions": (
                            [v.name for v in issue.fields.fixVersions] if hasattr(issue.fields, "fixVersions") else []
                        ),
                    }

                    # Calculate incident resolution time (MTTR)
                    if issue.fields.resolutiondate:
                        created = datetime.strptime(issue.fields.created, "%Y-%m-%dT%H:%M:%S.%f%z")
                        resolved = datetime.strptime(issue.fields.resolutiondate, "%Y-%m-%dT%H:%M:%S.%f%z")
                        incident_data["resolution_time_hours"] = (resolved - created).total_seconds() / 3600
                        incident_data["resolution_time_days"] = incident_data["resolution_time_hours"] / 24
                    else:
                        incident_data["resolution_time_hours"] = None
                        incident_data["resolution_time_days"] = None

                    # Extract deployment tag from description or labels
                    incident_data["related_deployment"] = self._extract_deployment_tag(incident_data)

                    # Mark as production incident
                    incident_data["is_production"] = self._is_production_incident(incident_data)

                    incidents.append(incident_data)

            except Exception as e:
                self.out.error(f"Error collecting incidents: {e}")

        # Filter to production incidents only
        production_incidents = [i for i in incidents if i.get("is_production", True)]
        self.out.info(f"Production incidents: {len(production_incidents)}", indent=1)

        return production_incidents

    def _extract_deployment_tag(self, incident: Dict) -> Optional[str]:
        """Extract deployment/release tag from incident

        Looks for version patterns like v1.2.3, release-123, etc. in:
        - Labels
        - Summary
        - Description

        Args:
            incident: Incident dictionary

        Returns:
            Deployment tag string or None
        """
        import re

        # Version patterns to search for
        patterns = [
            r"(Live|Beta)\s*-\s*\d{1,2}/[A-Za-z]{3}/\d{4}",  # Live - 6/Oct/2025 (Jira Fix Version format)
            r"v\d+\.\d+\.\d+",  # v1.2.3
            r"release-\d+",  # release-123
            r"version[:\s]+\d+\.\d+\.\d+",  # version: 1.2.3
            r"\d+\.\d+\.\d+",  # 1.2.3
        ]

        # Check labels first
        labels = incident.get("labels", [])
        for label in labels:
            for pattern in patterns:
                match = re.search(pattern, label, re.IGNORECASE)
                if match:
                    return match.group(0)

        # Check summary
        summary = incident.get("summary", "")
        for pattern in patterns:
            match = re.search(pattern, summary, re.IGNORECASE)
            if match:
                return match.group(0)

        # Check description
        description = incident.get("description", "")
        if description:
            for pattern in patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    return match.group(0)

        return None

    def _is_production_incident(self, incident: Dict) -> bool:
        """Determine if incident is production-related

        Checks for production indicators in:
        - Labels (production, prod, p1, sev1, incident, outage)
        - Issue type (Incident)
        - Priority (Blocker, Critical)

        Args:
            incident: Incident dictionary

        Returns:
            True if production incident
        """
        # Check issue type
        issue_type = incident.get("type", "").lower()
        if "incident" in issue_type:
            return True

        # Check priority
        priority = incident.get("priority", "").lower()
        if priority in ["blocker", "critical", "highest"]:
            return True

        # Check labels
        labels = [l.lower() for l in incident.get("labels", [])]
        production_keywords = ["production", "prod", "p1", "sev1", "incident", "outage", "production-incident"]

        for keyword in production_keywords:
            if any(keyword in label for label in labels):
                return True

        # Check summary/description for production keywords
        summary = incident.get("summary", "").lower()
        description = str(incident.get("description", "")).lower()

        for keyword in production_keywords:
            if keyword in summary or keyword in description:
                return True

        return False

    def collect_releases_from_fix_versions(self, project_keys: Optional[List[str]] = None) -> List[Dict]:
        """Collect releases from Jira Fix Versions instead of GitHub Releases

        Parses Fix Version names in format:
        - "Live - 6/Oct/2025" → production deployment
        - "Beta - 6/Oct/2025" → staging deployment

        Args:
            project_keys: List of Jira project keys to query (uses self.project_keys if None)

        Returns:
            List of release dictionaries matching DORA metrics structure
        """
        import re

        projects = project_keys or self.project_keys
        releases = []

        for project_key in projects:
            try:
                # Query all versions for this project
                jira_versions = self.jira.project_versions(project_key)

                self.out.info(f"Found {len(jira_versions)} versions in project {project_key}", indent=1)

                # Track what happens to each version
                matched_count = 0
                skipped_pattern = 0
                skipped_date = 0
                skipped_unreleased = 0
                skipped_future = 0

                for version in jira_versions:
                    # Parse version name: "Live - 6/Oct/2025"
                    release_data = self._parse_fix_version_name(version.name)

                    if not release_data:
                        skipped_pattern += 1
                        continue  # Skip non-matching versions

                    # Check if version is released (not just planned)
                    if not getattr(version, "released", False):
                        skipped_unreleased += 1
                        continue  # Skip unreleased/planned versions

                    # Also check releaseDate if available (must be in the past)
                    release_date = getattr(version, "releaseDate", None)
                    if release_date:
                        try:
                            # releaseDate format: "2026-01-15" (string)
                            from datetime import timezone

                            release_dt = datetime.strptime(release_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            now = datetime.now(timezone.utc)
                            if release_dt > now:
                                skipped_future += 1
                                continue  # Skip future releases (scheduled but not yet happened)
                        except (ValueError, AttributeError):
                            pass  # If date parsing fails, just use released flag

                    # Filter by date range
                    if release_data["published_at"] < self.since_date:
                        skipped_date += 1
                        continue

                    # Add project context
                    release_data["project"] = project_key
                    release_data["version_id"] = version.id
                    release_data["version_name"] = version.name

                    # Find related issues for this version (filtered by team if team_members specified)
                    release_data["related_issues"] = self._get_issues_for_version(
                        project_key, version.name, team_members=self.team_members
                    )
                    release_data["team_issue_count"] = len(release_data["related_issues"])

                    releases.append(release_data)
                    matched_count += 1

                # Informative logging
                if matched_count == 0:
                    self.out.warning(f"No released versions matched in {project_key}", indent=1)
                    if skipped_pattern > 0:
                        self.out.info(f"{skipped_pattern} versions didn't match 'Live - D/MMM/YYYY' format", indent=2)
                        self.out.info(f"Run 'python verify_jira_versions.py' to see version names", indent=2)
                    if skipped_unreleased > 0:
                        self.out.info(f"{skipped_unreleased} versions not yet released", indent=2)
                    if skipped_future > 0:
                        self.out.info(f"{skipped_future} versions scheduled for future", indent=2)
                    if skipped_date > 0:
                        self.out.info(f"{skipped_date} versions were outside the {self.days_back}-day window", indent=2)
                else:
                    self.out.success(f"Matched {matched_count} released versions", indent=1)
                    if skipped_pattern > 0:
                        self.out.info(f"(Skipped {skipped_pattern} non-matching versions)", indent=2)
                    if skipped_unreleased > 0:
                        self.out.info(f"(Skipped {skipped_unreleased} unreleased versions)", indent=2)
                    if skipped_future > 0:
                        self.out.info(f"(Skipped {skipped_future} future-dated versions)", indent=2)
                    if skipped_date > 0:
                        self.out.info(f"(Skipped {skipped_date} old versions)", indent=2)

            except Exception as e:
                self.out.error(f"Error collecting versions for {project_key}: {e}", indent=1)
                continue

        self.out.info(f"Total releases collected: {len(releases)}", indent=1)
        self.out.info(f"Production: {len([r for r in releases if r['environment'] == 'production'])}", indent=2)
        self.out.info(f"Staging: {len([r for r in releases if r['environment'] == 'staging'])}", indent=2)

        return releases

    def _parse_fix_version_name(self, version_name: str) -> Optional[Dict]:
        """Parse Jira Fix Version name into release structure

        Supported formats:
        - "Live - 6/Oct/2025" (production)
        - "Beta - 15/Jan/2026" (staging)
        - "Preview - 20/Jan/2026" (staging/preview)
        - "Beta WebTC - 28/Aug/2023" (staging with product name)
        - "Website - 26/Jan/2012" (production)
        - "RA_Web_YYYY_MM_DD" (LENS8 project, production)

        Args:
            version_name: Jira Fix Version name

        Returns:
            Release dict or None if pattern doesn't match
        """
        import re

        # Pattern 1: "Live - 6/Oct/2025", "Beta WebTC - 28/Aug/2023", "Website - 26/Jan/2012"
        # Pattern 2: "RA_Web_YYYY_MM_DD" (LENS8 project)
        # Try Pattern 1 first (Live/Beta/Website/Preview format)
        pattern1 = r"^(Live|Beta|Website|Preview)(?:\s+\w+)?\s+-\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})$"
        match = re.match(pattern1, version_name, re.IGNORECASE)

        if match:
            env_type = match.group(1).lower()  # "live", "beta", "website", or "preview"
            day = int(match.group(2))  # 6
            month_name = match.group(3)  # "Oct"
            year = int(match.group(4))  # 2025

            # Parse date
            try:
                date_str = f"{day}/{month_name}/{year}"
                published_at = datetime.strptime(date_str, "%d/%b/%Y")

                # Make timezone-aware (UTC)
                from datetime import timezone

                published_at = published_at.replace(tzinfo=timezone.utc)

            except ValueError as e:
                self.out.warning(f"Could not parse date from '{version_name}': {e}", indent=1)
                return None

            # Determine environment:
            # - "live" and "website" → production
            # - "beta" and "preview" → staging
            is_production = env_type in ["live", "website"]
            is_prerelease = env_type in ["beta", "preview"]

        else:
            # Try Pattern 2 (RA_Web_YYYY_MM_DD format)
            pattern2 = r"^RA_Web_(\d{4})_(\d{2})_(\d{2})$"
            match = re.match(pattern2, version_name, re.IGNORECASE)

            if not match:
                return None  # No pattern matched

            year = int(match.group(1))  # 2025
            month = int(match.group(2))  # 12
            day = int(match.group(3))  # 25

            # Parse date
            try:
                from datetime import timezone

                published_at = datetime(year, month, day, tzinfo=timezone.utc)
            except ValueError as e:
                self.out.warning(f"Could not parse date from '{version_name}': {e}", indent=1)
                return None

            # RA_Web releases are production
            is_production = True
            is_prerelease = False

        # Map to DORA structure
        return {
            "tag_name": version_name,
            "release_name": version_name,
            "published_at": published_at,
            "created_at": published_at,  # Same as published for Jira versions
            "environment": "production" if is_production else "staging",
            "author": "jira",  # Jira versions don't have author
            "commit_sha": None,  # No direct git mapping
            "committed_date": published_at,
            "is_prerelease": is_prerelease,
        }

    def _get_issues_for_version(
        self, project_key: str, version_name: str, team_members: Optional[List[str]] = None
    ) -> List[str]:
        """Get list of issue keys associated with this Fix Version

        Args:
            project_key: Jira project key
            version_name: Fix Version name
            team_members: Optional list of team member Jira usernames to filter by

        Returns:
            List of issue keys (e.g., ['PROJ-123', 'PROJ-124'])
        """
        try:
            # JQL: Find all issues with this fixVersion
            jql = f'project = {project_key} AND fixVersion = "{version_name}"'

            # Filter by team membership (assignee or reporter)
            try:
                if team_members and len(team_members) > 0:
                    # Escape usernames for JQL (wrap in quotes if they contain spaces)
                    # Filter out None/empty values first
                    valid_members = []
                    for m in team_members:
                        if m is not None and str(m).strip():
                            valid_members.append(str(m))

                    if valid_members:
                        # Build members string, quoting names with spaces
                        quoted_members = []
                        for m in valid_members:
                            if m and " " in m:
                                quoted_members.append(f'"{m}"')
                            elif m:  # Only add non-empty strings
                                quoted_members.append(m)

                        if quoted_members:
                            members_str = ", ".join(quoted_members)
                            jql += f" AND (assignee in ({members_str}) OR reporter in ({members_str}))"
            except Exception as e:
                # If team_members processing fails, skip filtering
                pass

            # Note: We only need issue keys, but specifying fields='key' can cause
            # the Jira library to hit malformed data. Using default fields works around this.
            issues = cast(List[Issue], self.jira.search_issues(jql, maxResults=1000))

            # Handle None response from Jira API
            if issues is None:
                return []

            return [issue.key for issue in issues]

        except Exception as e:
            self.out.warning(f"Could not fetch issues for version '{version_name}': {e}", indent=1)
            return []

    def get_dataframes(self):
        """Return all metrics as pandas DataFrames"""
        data = self.collect_all_metrics()

        return {
            "issues": pd.DataFrame(data["issues"]),
            "worklogs": pd.DataFrame(data["worklogs"]),
        }
