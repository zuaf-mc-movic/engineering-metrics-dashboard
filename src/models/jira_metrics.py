"""Jira metrics processing module.

This module provides methods for processing Jira filter results and calculating
Jira-related metrics like throughput, WIP, bugs, and cycle times.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pandas as pd


class JiraMetrics:
    """Mixin class providing Jira metrics calculation methods.

    This class is designed to be mixed into MetricsCalculator and requires:
    - self.dfs: Dict of DataFrames (jira_issues, etc.)
    - self.out: Logger instance
    """

    # Attributes provided by parent class (MetricsCalculator)
    dfs: Dict[str, pd.DataFrame]
    out: Any  # Logger instance

    def calculate_jira_metrics(self) -> Dict:
        """Calculate Jira-related metrics from jira_issues DataFrame."""
        if "jira_issues" not in self.dfs or self.dfs["jira_issues"].empty:
            return {}

        df = self.dfs["jira_issues"]

        metrics: Dict[str, Any] = {
            "total_issues": len(df),
            "resolved_issues": len(df[df["resolved"].notna()]),
            "open_issues": len(df[df["resolved"].isna()]),
        }

        # Average cycle time for resolved issues
        resolved_df = df[df["cycle_time_hours"].notna()]
        if not resolved_df.empty:
            metrics["avg_cycle_time_hours"] = resolved_df["cycle_time_hours"].mean()
            metrics["median_cycle_time_hours"] = resolved_df["cycle_time_hours"].median()
        else:
            metrics["avg_cycle_time_hours"] = 0.0
            metrics["median_cycle_time_hours"] = 0.0

        # Issues by type
        if "type" in df.columns:
            metrics["issues_by_type"] = df["type"].value_counts().to_dict()

        # Issues by status
        if "status" in df.columns:
            metrics["issues_by_status"] = df["status"].value_counts().to_dict()

        # Issues by assignee
        if "assignee" in df.columns:
            top_assignees = df["assignee"].value_counts().head(10)
            metrics["top_assignees"] = top_assignees.to_dict()

        return metrics

    def _process_jira_metrics(self, jira_filter_results: Optional[Dict]) -> Dict:
        """Process Jira filter results into structured metrics.

        Args:
            jira_filter_results: Results from Jira filter collection

        Returns:
            Dictionary with processed Jira metrics including:
            - throughput: Weekly average and breakdown
            - wip: Work in progress statistics
            - flagged: Blocked/flagged items
            - bugs: Created vs resolved trends
            - scope: Scope change trends
        """
        jira_metrics: Dict[str, Any] = {}
        if not jira_filter_results:
            return jira_metrics

        # Throughput from completed items
        completed_issues = jira_filter_results.get("completed", [])
        if completed_issues:
            # Calculate throughput by week
            df_completed = pd.DataFrame(completed_issues)
            if not df_completed.empty and "resolved" in df_completed.columns:
                # Remove duplicates based on issue key (keep first occurrence)
                original_count = len(df_completed)
                df_completed = df_completed.drop_duplicates(subset=["key"], keep="first")
                dedup_count = len(df_completed)

                if original_count != dedup_count:
                    self.out.info(f"Removed {original_count - dedup_count} duplicate issues from throughput", indent=2)

                df_completed["resolved_date"] = pd.to_datetime(df_completed["resolved"])
                df_completed["week"] = df_completed["resolved_date"].dt.to_period("W")
                weekly_counts = df_completed.groupby("week").size()

                # Count issues by type for pie chart
                type_breakdown: Dict[str, int] = {}
                for issue in completed_issues:
                    issue_type = issue.get("type", "Unknown")
                    type_breakdown[issue_type] = type_breakdown.get(issue_type, 0) + 1

                jira_metrics["throughput"] = {
                    "weekly_avg": weekly_counts.mean() if len(weekly_counts) > 0 else 0,
                    "total_completed": len(df_completed),  # Now deduplicated count
                    "by_week": {str(k): int(v) for k, v in weekly_counts.to_dict().items()},
                    "by_type": type_breakdown,
                }

        # WIP statistics
        wip_issues = jira_filter_results.get("wip", [])
        if wip_issues:
            ages = [
                issue.get("days_in_current_status", 0)
                for issue in wip_issues
                if issue.get("days_in_current_status") is not None
            ]

            # Count WIP items by status
            status_breakdown: Dict[str, int] = {}
            for issue in wip_issues:
                status = issue.get("status", "Unknown")
                status_breakdown[status] = status_breakdown.get(status, 0) + 1

            jira_metrics["wip"] = {
                "count": len(wip_issues),
                "avg_age_days": sum(ages) / len(ages) if ages else 0,
                "age_distribution": {
                    "0-3 days": len([a for a in ages if 0 <= a <= 3]),
                    "4-7 days": len([a for a in ages if 4 <= a <= 7]),
                    "8-14 days": len([a for a in ages if 8 <= a <= 14]),
                    "15+ days": len([a for a in ages if a >= 15]),
                },
                "by_status": status_breakdown,
            }

        # Flagged/blocked items
        flagged_issues = jira_filter_results.get("flagged_blocked", [])
        jira_metrics["flagged"] = {
            "count": len(flagged_issues),
            "issues": [
                {
                    "key": issue["key"],
                    "summary": issue["summary"],
                    "assignee": issue.get("assignee", "Unassigned"),
                    "days_blocked": issue.get("days_in_current_status", 0),
                }
                for issue in flagged_issues[:10]
            ],  # Top 10
        }

        # Created vs Resolved
        bugs_created = jira_filter_results.get("bugs_created", [])
        bugs_resolved = jira_filter_results.get("bugs_resolved", [])

        # Bugs: Created vs Resolved trends (last 90 days)
        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

        bugs_by_week_created: Dict[str, int] = {}
        for issue in bugs_created:
            created_date = issue.get("created")
            if created_date:
                try:
                    created_dt = pd.to_datetime(created_date, utc=True)
                    if created_dt >= ninety_days_ago:
                        week = created_dt.strftime("%Y-W%U")
                        bugs_by_week_created[week] = bugs_by_week_created.get(week, 0) + 1
                except:
                    pass  # Skip invalid dates

        bugs_by_week_resolved: Dict[str, int] = {}
        for issue in bugs_resolved:
            resolved_date = issue.get("resolved")
            if resolved_date:
                try:
                    resolved_dt = pd.to_datetime(resolved_date, utc=True)
                    if resolved_dt >= ninety_days_ago:
                        week = resolved_dt.strftime("%Y-W%U")
                        bugs_by_week_resolved[week] = bugs_by_week_resolved.get(week, 0) + 1
                except:
                    pass  # Skip invalid dates

        jira_metrics["bugs"] = {
            "created": len(bugs_created),
            "resolved": len(bugs_resolved),
            "net": len(bugs_created) - len(bugs_resolved),
            "trend_created": bugs_by_week_created if bugs_by_week_created else None,
            "trend_resolved": bugs_by_week_resolved if bugs_by_week_resolved else None,
        }

        # Scope: Created vs Resolved trends (last 90 days)
        scope_issues = jira_filter_results.get("scope", [])
        if scope_issues:
            scope_by_week_created: Dict[str, int] = {}
            scope_by_week_resolved: Dict[str, int] = {}

            for issue in scope_issues:
                created_date = issue.get("created")
                if created_date:
                    try:
                        created_dt = pd.to_datetime(created_date, utc=True)
                        if created_dt >= ninety_days_ago:
                            week = created_dt.strftime("%Y-W%U")
                            scope_by_week_created[week] = scope_by_week_created.get(week, 0) + 1
                    except:
                        pass  # Skip invalid dates

                resolved_date = issue.get("resolved")
                if resolved_date:
                    try:
                        resolved_dt = pd.to_datetime(resolved_date, utc=True)
                        if resolved_dt >= ninety_days_ago:
                            week = resolved_dt.strftime("%Y-W%U")
                            scope_by_week_resolved[week] = scope_by_week_resolved.get(week, 0) + 1
                    except:
                        pass  # Skip invalid dates

            jira_metrics["scope"] = {
                "total": len(scope_issues),
                "trend_created": scope_by_week_created if scope_by_week_created else None,
                "trend_resolved": scope_by_week_resolved if scope_by_week_resolved else None,
            }
        else:
            # Always create scope entry even if no data
            jira_metrics["scope"] = {"total": 0, "trend_created": None, "trend_resolved": None}

        return jira_metrics
