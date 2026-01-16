"""DORA (DevOps Research and Assessment) metrics calculation module.

This module provides methods for calculating the four key DORA metrics:
1. Deployment Frequency - How often code is deployed to production
2. Lead Time for Changes - Time from code commit to production deployment
3. Change Failure Rate - Percentage of deployments causing failures
4. Mean Time to Restore (MTTR) - Time to restore service after incidents

These metrics are used to measure DevOps performance and maturity.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd


class DORAMetrics:
    """Mixin class providing DORA metrics calculation methods.

    This class is designed to be mixed into MetricsCalculator and requires:
    - self.dfs: Dict of DataFrames (pull_requests, releases, etc.)
    """

    # Attributes provided by parent class (MetricsCalculator)
    dfs: Dict[str, pd.DataFrame]

    def calculate_dora_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        incidents_df: Optional[pd.DataFrame] = None,
        issue_to_version_map: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Calculate DORA (DevOps Research and Assessment) four key metrics.

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
        releases_df = self.dfs.get("releases", pd.DataFrame())
        prs_df = self.dfs.get("pull_requests", pd.DataFrame())

        # Calculate date range
        if not start_date or not end_date:
            # Use data-driven date range
            if not releases_df.empty and "published_at" in releases_df.columns:
                dates = pd.to_datetime(releases_df["published_at"])
                end_date = dates.max()
                start_date = dates.min()
            elif not prs_df.empty and "created_at" in prs_df.columns:
                dates = pd.to_datetime(prs_df["created_at"])
                end_date = dates.max()
                start_date = dates.min()
            else:
                # Default to 90 days
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)

        days_in_period = (end_date - start_date).days or 1

        # 1. DEPLOYMENT FREQUENCY
        deployment_frequency = self._calculate_deployment_frequency(releases_df, start_date, end_date, days_in_period)

        # 2. LEAD TIME FOR CHANGES
        lead_time = self._calculate_lead_time_for_changes(
            releases_df,
            prs_df,
            start_date,
            end_date,
            issue_to_version_map=issue_to_version_map,  # Pass through for Jira version mapping
        )

        # 3. CHANGE FAILURE RATE (requires incident data)
        change_failure_rate = self._calculate_change_failure_rate(releases_df, incidents_df)

        # 4. MEAN TIME TO RESTORE (requires incident data)
        mttr = self._calculate_mttr(incidents_df)

        # Calculate overall DORA performance level
        dora_level = self._calculate_dora_performance_level(deployment_frequency, lead_time, change_failure_rate, mttr)

        return {
            "deployment_frequency": deployment_frequency,
            "lead_time": lead_time,
            "change_failure_rate": change_failure_rate,
            "mttr": mttr,
            "dora_level": dora_level,
            "measurement_period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "days": days_in_period,
            },
        }

    def _calculate_deployment_frequency(
        self, releases_df: pd.DataFrame, start_date: datetime, end_date: datetime, days_in_period: int
    ) -> Dict[str, Any]:
        """Calculate deployment frequency metric."""
        if releases_df.empty or "environment" not in releases_df.columns:
            return {
                "total_deployments": 0,
                "per_day": 0,
                "per_week": 0,
                "per_month": 0,
                "level": "low",
                "badge_class": "low",
                "trend": {},
            }

        # Filter to production releases only
        production_releases = releases_df[releases_df["environment"] == "production"].copy()

        if production_releases.empty:
            return {
                "total_deployments": 0,
                "per_day": 0,
                "per_week": 0,
                "per_month": 0,
                "level": "low",
                "badge_class": "low",
                "trend": {},
            }

        total = len(production_releases)
        per_day = total / days_in_period if days_in_period > 0 else 0
        per_week = total / (days_in_period / 7) if days_in_period > 0 else 0
        per_month = total / (days_in_period / 30) if days_in_period > 0 else 0

        # Classify performance level
        if per_day >= 1:
            level = "elite"
            badge_class = "elite"
        elif per_week >= 1:
            level = "high"
            badge_class = "high"
        elif per_month >= 1:
            level = "medium"
            badge_class = "medium"
        else:
            level = "low"
            badge_class = "low"

        # Calculate trend (weekly breakdown)
        if "published_at" in production_releases.columns:
            production_releases["week"] = pd.to_datetime(production_releases["published_at"]).dt.to_period("W")
            weekly_counts = production_releases.groupby("week").size()
            trend = {str(k): int(v) for k, v in weekly_counts.to_dict().items()}
        else:
            trend = {}

        return {
            "total_deployments": total,
            "per_day": round(per_day, 2),
            "per_week": round(per_week, 2),
            "per_month": round(per_month, 2),
            "level": level,
            "badge_class": badge_class,
            "trend": trend,
        }

    def _calculate_lead_time_for_changes(
        self,
        releases_df: pd.DataFrame,
        prs_df: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
        issue_to_version_map: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Calculate lead time for changes (PR merge to deployment).

        Args:
            releases_df: DataFrame of deployments
            prs_df: DataFrame of merged PRs
            start_date: Start of measurement period
            end_date: End of measurement period
            issue_to_version_map: Optional dict mapping issue keys to fix versions (for Jira-based tracking)
        """
        if releases_df.empty or prs_df.empty:
            return {
                "median_hours": None,
                "median_days": None,
                "p95_hours": None,
                "average_hours": None,
                "sample_size": 0,
                "level": "low",
                "badge_class": "low",
                "trend": {},
            }

        # Filter to production releases and merged PRs
        if "environment" in releases_df.columns:
            production_releases = releases_df[releases_df["environment"] == "production"].copy()
        else:
            production_releases = releases_df.copy()

        merged_prs = prs_df[prs_df["merged"]].copy()

        if production_releases.empty or merged_prs.empty:
            return {
                "median_hours": None,
                "median_days": None,
                "p95_hours": None,
                "average_hours": None,
                "sample_size": 0,
                "level": "low",
                "badge_class": "low",
            }

        # Ensure datetime columns
        if "published_at" in production_releases.columns:
            production_releases["published_at"] = pd.to_datetime(production_releases["published_at"])
        if "merged_at" in merged_prs.columns:
            merged_prs["merged_at"] = pd.to_datetime(merged_prs["merged_at"])

        # Calculate lead time for each PR (time to next deployment)
        lead_times = []
        for _, pr in merged_prs.iterrows():
            if pd.isna(pr["merged_at"]):
                continue

            # NEW: Try Jira issue key matching first (more accurate)
            if issue_to_version_map:
                issue_key = self._extract_issue_key_from_pr(pr)

                if issue_key and issue_key in issue_to_version_map:
                    # Direct mapping: PR → Issue → Fix Version → Deployment
                    fix_version = issue_to_version_map[issue_key]
                    matching_releases = production_releases[production_releases["tag_name"] == fix_version]

                    if not matching_releases.empty:
                        deploy_time = matching_releases.iloc[0]["published_at"]
                        lead_time_hours = (deploy_time - pr["merged_at"]).total_seconds() / 3600
                        if lead_time_hours > 0:
                            lead_times.append(lead_time_hours)
                        continue  # Skip fallback logic

            # Fallback: Find the next deployment after this PR was merged (time-based)
            next_deploys = production_releases[production_releases["published_at"] > pr["merged_at"]].sort_values(
                "published_at"
            )

            if not next_deploys.empty:
                next_deploy = next_deploys.iloc[0]
                lead_time_hours = (next_deploy["published_at"] - pr["merged_at"]).total_seconds() / 3600
                if lead_time_hours > 0:  # Sanity check
                    lead_times.append(lead_time_hours)

        if not lead_times:
            return {
                "median_hours": None,
                "median_days": None,
                "p95_hours": None,
                "average_hours": None,
                "sample_size": 0,
                "level": "low",
                "badge_class": "low",
                "trend": {},
            }

        median_hours = float(pd.Series(lead_times).median())
        p95_hours = float(pd.Series(lead_times).quantile(0.95))
        average_hours = float(pd.Series(lead_times).mean())

        # Classify performance level
        if median_hours < 24:
            level = "elite"
            badge_class = "elite"
        elif median_hours < 168:  # 1 week
            level = "high"
            badge_class = "high"
        elif median_hours < 720:  # 1 month
            level = "medium"
            badge_class = "medium"
        else:
            level = "low"
            badge_class = "low"

        # Calculate trend (weekly breakdown of median lead time)
        trend = {}
        if merged_prs is not None and not merged_prs.empty and "merged_at" in merged_prs.columns:
            # Create temporary dataframe with PR merge dates and lead times
            pr_lead_times = []
            for _, pr in merged_prs.iterrows():
                if pd.isna(pr["merged_at"]):
                    continue

                # Find lead time for this PR (same logic as above)
                pr_lead_time = None

                # Try Jira-based matching
                if issue_to_version_map:
                    issue_key = self._extract_issue_key_from_pr(pr)
                    if issue_key and issue_key in issue_to_version_map:
                        fix_version = issue_to_version_map[issue_key]
                        matching_releases = production_releases[production_releases["tag_name"] == fix_version]
                        if not matching_releases.empty:
                            deploy_time = matching_releases.iloc[0]["published_at"]
                            pr_lead_time = (deploy_time - pr["merged_at"]).total_seconds() / 3600

                # Fallback to time-based
                if pr_lead_time is None:
                    next_deploys = production_releases[
                        production_releases["published_at"] > pr["merged_at"]
                    ].sort_values("published_at")
                    if not next_deploys.empty:
                        next_deploy = next_deploys.iloc[0]
                        pr_lead_time = (next_deploy["published_at"] - pr["merged_at"]).total_seconds() / 3600

                if pr_lead_time is not None and pr_lead_time > 0:
                    pr_lead_times.append({"merged_at": pr["merged_at"], "lead_time_hours": pr_lead_time})

            if pr_lead_times:
                lead_times_df = pd.DataFrame(pr_lead_times)
                lead_times_df["week"] = pd.to_datetime(lead_times_df["merged_at"]).dt.to_period("W")

                # Calculate median lead time per week
                weekly_medians = lead_times_df.groupby("week")["lead_time_hours"].median()
                trend = {str(k): round(float(v), 1) for k, v in weekly_medians.to_dict().items()}

        return {
            "median_hours": round(median_hours, 1),
            "median_days": round(median_hours / 24, 1),
            "p95_hours": round(p95_hours, 1),
            "p95_days": round(p95_hours / 24, 1),
            "average_hours": round(average_hours, 1),
            "average_days": round(average_hours / 24, 1),
            "sample_size": len(lead_times),
            "level": level,
            "badge_class": badge_class,
            "trend": trend,
        }

    def _extract_issue_key_from_pr(self, pr: pd.Series) -> Optional[str]:
        """Extract Jira issue key from PR title or branch.

        Looks for patterns like:
        - "[PROJ-123] Add feature"
        - "PROJ-123: Fix bug"
        - "feature/PROJ-123-description"

        Args:
            pr: PR data series

        Returns:
            Issue key (e.g., "PROJ-123") or None
        """
        # Pattern: PROJECT-123 format
        pattern = r"([A-Z]+-\d+)"

        # Check title
        if "title" in pr and pd.notna(pr["title"]):
            match = re.search(pattern, str(pr["title"]))
            if match:
                return match.group(1)

        # Check branch name (if available)
        if "branch" in pr and pd.notna(pr["branch"]):
            match = re.search(pattern, str(pr["branch"]))
            if match:
                return match.group(1)

        return None

    def _calculate_change_failure_rate(
        self, releases_df: pd.DataFrame, incidents_df: pd.DataFrame = None
    ) -> Dict[str, Any]:
        """Calculate change failure rate (% of deployments causing incidents)."""
        if releases_df.empty:
            return {
                "rate_percent": None,
                "failed_deployments": 0,
                "total_deployments": 0,
                "level": "low",
                "badge_class": "low",
                "trend": {},
            }

        # Filter to production releases
        if "environment" in releases_df.columns:
            production_releases = releases_df[releases_df["environment"] == "production"].copy()
        else:
            production_releases = releases_df.copy()

        total_deployments = len(production_releases)

        if total_deployments == 0:
            return {
                "rate_percent": None,
                "failed_deployments": 0,
                "total_deployments": 0,
                "level": "low",
                "badge_class": "low",
                "trend": {},
            }

        # Without incident data, we can't calculate failure rate
        if incidents_df is None or incidents_df.empty:
            return {
                "rate_percent": None,
                "failed_deployments": None,
                "total_deployments": total_deployments,
                "level": "unknown",
                "badge_class": "low",
                "note": "Incident data not available",
                "trend": {},
            }

        # Correlate incidents to deployments
        # Method 1: Direct tag matching (if incident has related_deployment field)
        # Method 2: Time-based correlation (incident created within 24h of deployment)

        deployments_with_incidents = set()
        correlation_window_hours = 24

        # Ensure datetime columns
        if "published_at" in production_releases.columns:
            production_releases["published_at"] = pd.to_datetime(production_releases["published_at"])

        incidents_df = incidents_df.copy()
        if "created" in incidents_df.columns:
            incidents_df["created"] = pd.to_datetime(incidents_df["created"])

        for _, incident in incidents_df.iterrows():
            incident_created = incident.get("created")
            if pd.isna(incident_created):
                continue

            # Method 1: Check for direct deployment tag reference
            related_deployment = incident.get("related_deployment")
            if related_deployment and "tag_name" in production_releases.columns:
                # Match exact Fix Version name: "Live - 6/Oct/2025"
                matching_deploys = production_releases[production_releases["tag_name"] == related_deployment]
                for deploy_tag in matching_deploys["tag_name"]:
                    deployments_with_incidents.add(deploy_tag)

            # Method 2: Time-based correlation (incident within correlation window after deployment)
            if "published_at" in production_releases.columns:
                for _, deploy in production_releases.iterrows():
                    deploy_time = deploy["published_at"]
                    if pd.notna(deploy_time):
                        # Check if incident occurred within window after deployment
                        time_diff_hours = (incident_created - deploy_time).total_seconds() / 3600
                        if 0 <= time_diff_hours <= correlation_window_hours:
                            deployments_with_incidents.add(deploy.get("tag_name", ""))

        failed_deployments = len(deployments_with_incidents)
        cfr = (failed_deployments / total_deployments) * 100 if total_deployments > 0 else 0

        # Classify performance level (DORA thresholds)
        if cfr < 15:
            level = "elite"
            badge_class = "elite"
        elif cfr < 16:
            level = "high"
            badge_class = "high"
        elif cfr < 30:
            level = "medium"
            badge_class = "medium"
        else:
            level = "low"
            badge_class = "low"

        # Calculate trend (weekly breakdown of failure rate)
        trend = {}
        if not production_releases.empty and "published_at" in production_releases.columns:
            production_releases["week"] = pd.to_datetime(production_releases["published_at"]).dt.to_period("W")

            # Count total deployments per week
            weekly_total = production_releases.groupby("week").size()

            # Count failed deployments per week
            failed_releases = production_releases[production_releases["tag_name"].isin(deployments_with_incidents)]
            weekly_failed = failed_releases.groupby("week").size() if not failed_releases.empty else pd.Series()

            # Calculate CFR per week
            for week in weekly_total.index:
                total = weekly_total[week]
                failed = weekly_failed.get(week, 0)
                cfr_week = (failed / total * 100) if total > 0 else 0
                trend[str(week)] = round(cfr_week, 1)

        return {
            "rate_percent": round(cfr, 1),
            "failed_deployments": failed_deployments,
            "total_deployments": total_deployments,
            "incidents_count": len(incidents_df),
            "level": level,
            "badge_class": badge_class,
            "correlation_window_hours": correlation_window_hours,
            "trend": trend,
        }

    def _calculate_mttr(self, incidents_df: pd.DataFrame = None) -> Dict[str, Any]:
        """Calculate Mean Time to Restore (incident resolution time)."""
        if incidents_df is None or incidents_df.empty:
            return {
                "median_hours": None,
                "median_days": None,
                "average_hours": None,
                "p95_hours": None,
                "sample_size": 0,
                "level": "unknown",
                "badge_class": "low",
                "note": "Incident data not available",
                "trend": {},
            }

        # Calculate resolution times for resolved incidents
        resolution_times = []

        for _, incident in incidents_df.iterrows():
            # Check for resolution_time_hours field (from Jira collector)
            if "resolution_time_hours" in incident and pd.notna(incident["resolution_time_hours"]):
                resolution_times.append(float(incident["resolution_time_hours"]))
            # Fallback: calculate from created/resolved dates
            elif "created" in incident and "resolved" in incident:
                created = incident["created"]
                resolved = incident["resolved"]
                if pd.notna(created) and pd.notna(resolved):
                    created_dt = pd.to_datetime(created)
                    resolved_dt = pd.to_datetime(resolved)
                    hours = (resolved_dt - created_dt).total_seconds() / 3600
                    if hours > 0:  # Sanity check
                        resolution_times.append(hours)

        if not resolution_times:
            return {
                "median_hours": None,
                "median_days": None,
                "average_hours": None,
                "p95_hours": None,
                "sample_size": 0,
                "level": "unknown",
                "badge_class": "low",
                "note": "No resolved incidents in period",
                "trend": {},
            }

        # Calculate statistics
        median_hours = float(pd.Series(resolution_times).median())
        average_hours = float(pd.Series(resolution_times).mean())
        p95_hours = float(pd.Series(resolution_times).quantile(0.95))

        # Classify performance level (DORA thresholds)
        if median_hours < 1:
            level = "elite"
            badge_class = "elite"
        elif median_hours < 24:
            level = "high"
            badge_class = "high"
        elif median_hours < 168:  # 1 week
            level = "medium"
            badge_class = "medium"
        else:
            level = "low"
            badge_class = "low"

        # Calculate trend (weekly breakdown of median MTTR)
        trend = {}
        if not incidents_df.empty and "resolved" in incidents_df.columns:
            # Create temporary dataframe with resolved incidents and their resolution times
            incident_times = []
            for _, incident in incidents_df.iterrows():
                resolved_dt = incident.get("resolved")
                if pd.notna(resolved_dt):
                    # Get resolution time for this incident
                    if "resolution_time_hours" in incident and pd.notna(incident["resolution_time_hours"]):
                        res_time = float(incident["resolution_time_hours"])
                    elif "created" in incident and pd.notna(incident["created"]):
                        created_dt = pd.to_datetime(incident["created"])
                        resolved_dt_parsed = pd.to_datetime(resolved_dt)
                        res_time = (resolved_dt_parsed - created_dt).total_seconds() / 3600
                    else:
                        continue

                    if res_time > 0:
                        incident_times.append({"resolved": resolved_dt, "resolution_time_hours": res_time})

            if incident_times:
                incidents_trend_df = pd.DataFrame(incident_times)
                incidents_trend_df["week"] = pd.to_datetime(incidents_trend_df["resolved"]).dt.to_period("W")

                # Calculate median resolution time per week
                weekly_medians = incidents_trend_df.groupby("week")["resolution_time_hours"].median()
                trend = {str(k): round(float(v), 1) for k, v in weekly_medians.to_dict().items()}

        return {
            "median_hours": round(median_hours, 1),
            "median_days": round(median_hours / 24, 1),
            "average_hours": round(average_hours, 1),
            "average_days": round(average_hours / 24, 1),
            "p95_hours": round(p95_hours, 1),
            "p95_days": round(p95_hours / 24, 1),
            "sample_size": len(resolution_times),
            "level": level,
            "badge_class": badge_class,
            "trend": trend,
        }

    def _calculate_dora_performance_level(
        self, deployment_freq: Dict, lead_time: Dict, cfr: Dict, mttr: Dict
    ) -> Dict[str, str]:
        """Calculate overall DORA performance level based on all four metrics."""
        # Count metrics by level
        levels = {"elite": 0, "high": 0, "medium": 0, "low": 0}

        for metric in [deployment_freq, lead_time, cfr, mttr]:
            level = metric.get("level", "low")
            if level in levels:
                levels[level] += 1

        # Determine overall level (must excel in multiple areas)
        if levels["elite"] >= 3:
            overall_level = "Elite"
            description = "Top performers! Fastest delivery with highest stability."
        elif levels["elite"] >= 2 or (levels["elite"] + levels["high"]) >= 3:
            overall_level = "High"
            description = "Strong performance across all DORA metrics."
        elif levels["low"] <= 1:
            overall_level = "Medium"
            description = "Good foundation, opportunities to improve velocity."
        else:
            overall_level = "Low"
            description = "Focus on automation and reducing cycle times."

        return {"level": overall_level, "description": description, "breakdown": levels}
