import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.logging import get_logger

from .dora_metrics import DORAMetrics
from .jira_metrics import JiraMetrics
from .performance_scoring import PerformanceScorer

# Suppress pandas timezone conversion warnings
warnings.filterwarnings(
    "ignore", message="Converting to PeriodArray/Index representation will drop timezone information"
)


class MetricsCalculator(DORAMetrics, JiraMetrics):
    def __init__(self, dataframes: Dict[str, pd.DataFrame]):
        self.dfs = dataframes
        self.out = get_logger("team_metrics.models.metrics")

    def calculate_pr_metrics(self):
        """Calculate PR-related metrics"""
        if self.dfs["pull_requests"].empty:
            return {
                "total_prs": 0,
                "merged_prs": 0,
                "open_prs": 0,
                "closed_unmerged_prs": 0,
                "merge_rate": 0,
                "avg_cycle_time_hours": None,
                "median_cycle_time_hours": None,
                "avg_time_to_first_review_hours": None,
                "avg_pr_size": 0,
                "pr_size_distribution": {},
            }

        df = self.dfs["pull_requests"]

        metrics = {
            "total_prs": len(df),
            "merged_prs": len(df[df["merged"]]),
            "open_prs": len(df[df["state"] == "open"]),
            "closed_unmerged_prs": len(df[(df["state"] == "closed") & (~df["merged"])]),
            "avg_cycle_time_hours": df["cycle_time_hours"].mean(),
            "median_cycle_time_hours": df["cycle_time_hours"].median(),
            "avg_time_to_first_review_hours": df["time_to_first_review_hours"].mean(),
            "avg_pr_size": (df["additions"] + df["deletions"]).mean(),
            "merge_rate": len(df[df["merged"]]) / len(df) if len(df) > 0 else 0,
        }

        # PR size distribution
        df["size"] = df["additions"] + df["deletions"]
        metrics["pr_size_distribution"] = {
            "small (<100 lines)": len(df[df["size"] < 100]),
            "medium (100-500 lines)": len(df[(df["size"] >= 100) & (df["size"] < 500)]),
            "large (500-1000 lines)": len(df[(df["size"] >= 500) & (df["size"] < 1000)]),
            "xlarge (>1000 lines)": len(df[df["size"] >= 1000]),
        }

        return metrics

    def calculate_review_metrics(self):
        """Calculate review-related metrics"""
        if self.dfs["reviews"].empty:
            return {"total_reviews": 0, "unique_reviewers": 0, "avg_reviews_per_pr": 0, "top_reviewers": {}}

        df = self.dfs["reviews"]

        metrics = {
            "total_reviews": len(df),
            "unique_reviewers": df["reviewer"].nunique(),
            "avg_reviews_per_pr": (
                len(df) / self.dfs["pull_requests"]["pr_number"].nunique() if not self.dfs["pull_requests"].empty else 0
            ),
        }

        # Top reviewers
        top_reviewers = df["reviewer"].value_counts().head(10)
        metrics["top_reviewers"] = top_reviewers.to_dict()

        # Review engagement (who reviews whose code)
        if "pr_author" in df.columns:
            engagement = df.groupby(["reviewer", "pr_author"]).size().reset_index(name="count")
            metrics["cross_team_reviews"] = len(engagement)

        return metrics

    def calculate_contributor_metrics(self):
        """Calculate contributor activity metrics"""
        if self.dfs["commits"].empty:
            return {
                "total_commits": 0,
                "unique_contributors": 0,
                "avg_commits_per_day": 0,
                "total_lines_added": 0,
                "total_lines_deleted": 0,
                "top_contributors": {},
                "daily_commit_count": {},
            }

        df = self.dfs["commits"]

        metrics = {
            "total_commits": len(df),
            "unique_contributors": df["author"].nunique(),
            "avg_commits_per_day": len(df) / 90,
            "total_lines_added": df["additions"].sum(),
            "total_lines_deleted": df["deletions"].sum(),
        }

        # Top contributors
        top_contributors = (
            df.groupby("author")
            .agg({"sha": "count", "additions": "sum", "deletions": "sum"})
            .sort_values("sha", ascending=False)
            .head(10)
        )

        metrics["top_contributors"] = top_contributors.to_dict("index")

        # Commit activity by date
        df["date_only"] = pd.to_datetime(df["date"]).dt.date
        daily_commits = df.groupby("date_only").size()
        # Convert date keys to strings for JSON serialization
        metrics["daily_commit_count"] = {str(k): v for k, v in daily_commits.to_dict().items()}

        return metrics

    def calculate_deployment_metrics(self):
        """Calculate deployment frequency and lead time (legacy method, use calculate_dora_metrics)"""
        # Check if releases DataFrame exists and has data
        if "releases" not in self.dfs or self.dfs["releases"].empty:
            return {
                "total_deployments": 0,
                "deployments_per_week": 0,
            }

        df = self.dfs["releases"]

        # Filter to production releases only
        if "environment" in df.columns:
            production_releases = df[df["environment"] == "production"]
        else:
            production_releases = df

        if production_releases.empty:
            return {
                "total_deployments": 0,
                "deployments_per_week": 0,
            }

        # Calculate deployment frequency
        if "published_at" in production_releases.columns:
            production_releases["date_only"] = pd.to_datetime(production_releases["published_at"]).dt.date
            days_range = (production_releases["date_only"].max() - production_releases["date_only"].min()).days or 1
        else:
            days_range = 90  # Default

        metrics = {
            "total_deployments": len(production_releases),
            "deployments_per_week": len(production_releases) / (days_range / 7) if days_range > 0 else 0,
        }

        if "environment" in df.columns:
            metrics["deployments_by_environment"] = df["environment"].value_counts().to_dict()

        return metrics

    def _extract_github_members(self, team_config: Dict) -> List[str]:
        """Extract GitHub usernames from team configuration.

        Args:
            team_config: Team configuration with members

        Returns:
            List of GitHub usernames
        """
        github_members = []
        if "members" in team_config and isinstance(team_config.get("members"), list):
            # New format: unified members list
            for member in team_config["members"]:
                if isinstance(member, dict) and member.get("github"):
                    github_members.append(member["github"])
        else:
            # Old format: separate arrays under github key
            github_members = team_config.get("github", {}).get("members", [])
        return github_members

    def _filter_team_github_data(self, github_members: List[str]) -> Dict[str, pd.DataFrame]:
        """Filter GitHub data to include only team members.

        Args:
            github_members: List of GitHub usernames

        Returns:
            Dictionary with filtered DataFrames for pull_requests, reviews, and commits
        """
        return {
            "pull_requests": (
                self.dfs["pull_requests"][self.dfs["pull_requests"]["author"].isin(github_members)]
                if not self.dfs["pull_requests"].empty
                else pd.DataFrame()
            ),
            "reviews": (
                self.dfs["reviews"][self.dfs["reviews"]["reviewer"].isin(github_members)]
                if not self.dfs["reviews"].empty
                else pd.DataFrame()
            ),
            "commits": (
                self.dfs["commits"][self.dfs["commits"]["author"].isin(github_members)]
                if not self.dfs["commits"].empty
                else pd.DataFrame()
            ),
        }

    def _calculate_member_trends(self, team_dfs: Dict[str, pd.DataFrame], github_members: List[str]) -> Dict:
        """Calculate per-member GitHub activity breakdown.

        Args:
            team_dfs: Filtered DataFrames for the team
            github_members: List of GitHub usernames

        Returns:
            Dictionary mapping member names to their activity metrics
        """
        member_trends = {}
        for member in github_members:
            # Handle empty DataFrames gracefully
            if not team_dfs["pull_requests"].empty and "author" in team_dfs["pull_requests"].columns:
                member_prs = team_dfs["pull_requests"][team_dfs["pull_requests"]["author"] == member]
            else:
                member_prs = pd.DataFrame()

            if not team_dfs["reviews"].empty and "reviewer" in team_dfs["reviews"].columns:
                member_reviews = team_dfs["reviews"][team_dfs["reviews"]["reviewer"] == member]
            else:
                member_reviews = pd.DataFrame()

            if not team_dfs["commits"].empty and "author" in team_dfs["commits"].columns:
                member_commits = team_dfs["commits"][team_dfs["commits"]["author"] == member]
            else:
                member_commits = pd.DataFrame()

            member_trends[member] = {
                "prs": len(member_prs),
                "reviews": len(member_reviews),
                "commits": len(member_commits),
                "lines_added": (
                    member_commits["additions"].sum()
                    if not member_commits.empty and "additions" in member_commits.columns
                    else 0
                ),
                "lines_deleted": (
                    member_commits["deletions"].sum()
                    if not member_commits.empty and "deletions" in member_commits.columns
                    else 0
                ),
            }
        return member_trends

    def calculate_team_metrics(
        self,
        team_name: str,
        team_config: Dict,
        jira_filter_results: Optional[Dict] = None,
        issue_to_version_map: Optional[Dict] = None,
        dora_config: Optional[Dict] = None,
    ) -> Dict:
        """Calculate team-level metrics

        Args:
            team_name: Name of the team
            team_config: Team configuration with members
            jira_filter_results: Results from Jira filter collection
            issue_to_version_map: Optional dict mapping issue keys to fix versions (for Jira-based DORA tracking)
            dora_config: Optional DORA metrics configuration (max_lead_time_days, cfr_correlation_window_hours)

        Returns:
            Dictionary with team metrics
        """
        # Default DORA config if not provided
        if dora_config is None:
            dora_config = {"max_lead_time_days": 180, "cfr_correlation_window_hours": 24}
        # Extract GitHub members
        github_members = self._extract_github_members(team_config)

        # Filter team data
        team_dfs = self._filter_team_github_data(github_members)

        # Calculate basic GitHub metrics
        pr_count = len(team_dfs["pull_requests"])
        review_count = len(team_dfs["reviews"])
        commit_count = len(team_dfs["commits"])

        # Calculate per-member trends
        member_trends = self._calculate_member_trends(team_dfs, github_members)

        # Process Jira metrics
        jira_metrics = self._process_jira_metrics(jira_filter_results)

        # Calculate DORA metrics (releases are team-level, not filtered to individual members)
        # Create temporary calculator with releases included
        dora_dfs = {
            "pull_requests": team_dfs["pull_requests"],
            "releases": self.dfs.get("releases", pd.DataFrame()),  # Use full team releases
            "commits": team_dfs["commits"],
        }
        dora_calculator = MetricsCalculator(dora_dfs)

        # Convert incidents from jira_filter_results to DataFrame for DORA calculation
        incidents_df = None
        if jira_filter_results and "incidents" in jira_filter_results:
            incidents_list = jira_filter_results["incidents"]
            if incidents_list:
                incidents_df = pd.DataFrame(incidents_list)
                self.out.info(f"Passing {len(incidents_df)} incidents to DORA calculation", indent=2)

        dora_metrics = dora_calculator.calculate_dora_metrics(
            issue_to_version_map=issue_to_version_map,  # Pass through for lead time calculation
            incidents_df=incidents_df,  # Pass incidents for CFR & MTTR
            max_lead_time_days=dora_config.get("max_lead_time_days", 180),
            cfr_correlation_window_hours=dora_config.get("cfr_correlation_window_hours", 24),
        )

        # Convert releases DataFrame to list of dicts for caching
        raw_releases = []
        releases_df = self.dfs.get("releases", pd.DataFrame())
        if not releases_df.empty:
            raw_releases = releases_df.to_dict("records")

        return {
            "team_name": team_name,
            "github": {
                "pr_count": pr_count,
                "review_count": review_count,
                "commit_count": commit_count,
                "avg_cycle_time": (
                    team_dfs["pull_requests"]["cycle_time_hours"].mean() if not team_dfs["pull_requests"].empty else 0
                ),
                "member_trends": member_trends,
            },
            "jira": jira_metrics,
            "dora": dora_metrics,
            "raw_releases": raw_releases,  # Add releases to cache
        }

    def calculate_person_metrics(
        self,
        username: str,
        github_data: Dict,
        jira_data: Optional[List] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
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
        prs_df = pd.DataFrame(github_data.get("pull_requests", []))
        reviews_df = pd.DataFrame(github_data.get("reviews", []))
        commits_df = pd.DataFrame(github_data.get("commits", []))

        # GitHub metrics
        github_metrics = {
            "prs_created": len(prs_df),
            "prs_merged": len(prs_df[prs_df["merged"]]) if not prs_df.empty else 0,
            "merge_rate": (len(prs_df[prs_df["merged"]]) / len(prs_df) if len(prs_df) > 0 else 0),
            "reviews_given": len(reviews_df),
            "prs_reviewed": reviews_df["pr_number"].nunique() if not reviews_df.empty else 0,
            "commits": len(commits_df),
            "lines_added": commits_df["additions"].sum() if not commits_df.empty else 0,
            "lines_deleted": commits_df["deletions"].sum() if not commits_df.empty else 0,
            "avg_pr_cycle_time": prs_df["cycle_time_hours"].mean() if not prs_df.empty else 0,
            "avg_time_to_review": prs_df["time_to_first_review_hours"].mean() if not prs_df.empty else 0,
        }

        # Jira metrics
        jira_metrics = {}
        if jira_data:
            jira_df = pd.DataFrame(jira_data)
            if not jira_df.empty:
                # Convert resolved dates to datetime for comparison
                if "resolved" in jira_df.columns and start_date:
                    jira_df["resolved"] = pd.to_datetime(jira_df["resolved"], errors="coerce", utc=True)

                # Filter resolved issues to only those resolved in the time window
                if start_date:
                    resolved = jira_df[(jira_df["resolved"].notna()) & (jira_df["resolved"] >= start_date)]
                else:
                    resolved = jira_df[jira_df["resolved"].notna()]

                jira_metrics = {
                    "completed": len(resolved),
                    "in_progress": len(jira_df[jira_df["resolved"].isna()]),
                    "avg_cycle_time": resolved["cycle_time_hours"].mean() if not resolved.empty else 0,
                    "types": jira_df["type"].value_counts().to_dict() if "type" in jira_df.columns else {},
                }

        return {
            "username": username,
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "github": github_metrics,
            "jira": jira_metrics,
        }

    def calculate_person_trends(self, github_data: Dict, period: str = "weekly") -> Dict:
        """Calculate time-series trends for person metrics

        Args:
            github_data: Raw GitHub data (PRs, reviews, commits)
            period: Grouping period ('daily', 'weekly', 'monthly')

        Returns:
            Dictionary with trend data for charts
        """
        trends: Dict[str, List[Any]] = {
            "pr_trend": [],
            "review_trend": [],
            "commit_trend": [],
            "lines_changed_trend": [],
        }

        # PR trend
        if github_data.get("pull_requests"):
            prs_df = pd.DataFrame(github_data["pull_requests"])
            if not prs_df.empty and "created_at" in prs_df.columns:
                prs_df["created_at"] = pd.to_datetime(prs_df["created_at"])
                prs_df["period"] = prs_df["created_at"].dt.strftime("%Y-W%U")
                pr_counts = prs_df.groupby("period").size()
                trends["pr_trend"] = [{"period": p, "count": int(c)} for p, c in pr_counts.items()]

        # Review trend
        if github_data.get("reviews"):
            reviews_df = pd.DataFrame(github_data["reviews"])
            if not reviews_df.empty and "submitted_at" in reviews_df.columns:
                reviews_df["submitted_at"] = pd.to_datetime(reviews_df["submitted_at"])
                reviews_df["period"] = reviews_df["submitted_at"].dt.strftime("%Y-W%U")
                review_counts = reviews_df.groupby("period").size()
                trends["review_trend"] = [{"period": p, "count": int(c)} for p, c in review_counts.items()]

        # Commit trend
        if github_data.get("commits"):
            commits_df = pd.DataFrame(github_data["commits"])
            # Check for both 'date' and 'committed_date' field names
            date_field = "date" if "date" in commits_df.columns else "committed_date"
            if not commits_df.empty and date_field in commits_df.columns:
                commits_df["commit_date"] = pd.to_datetime(commits_df[date_field], utc=True)
                commits_df["period"] = commits_df["commit_date"].dt.strftime("%Y-W%U")
                commit_counts = commits_df.groupby("period").size()
                trends["commit_trend"] = [{"period": p, "count": int(c)} for p, c in commit_counts.items()]

                # Lines changed trend
                if "additions" in commits_df.columns and "deletions" in commits_df.columns:
                    lines_agg = commits_df.groupby("period").agg({"additions": "sum", "deletions": "sum"})
                    trends["lines_changed_trend"] = [
                        {"period": p, "additions": int(row["additions"]), "deletions": int(row["deletions"])}
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
            period_name = metrics.get("period_name", "Unknown")
            github = metrics.get("github", {})

            comparisons.append(
                {
                    "period": period_name,
                    "prs": github.get("prs_created", 0),
                    "reviews": github.get("reviews_given", 0),
                    "commits": github.get("commits", 0),
                    "lines_changed": github.get("lines_added", 0) + github.get("lines_deleted", 0),
                }
            )

        # Calculate trends (current vs previous)
        trends = {}
        if len(comparisons) >= 2:
            current = comparisons[0]
            previous = comparisons[1]

            for key in ["prs", "reviews", "commits"]:
                curr_val = current.get(key, 0)
                prev_val = previous.get(key, 0)

                if prev_val > 0:
                    change_percent = ((curr_val - prev_val) / prev_val) * 100
                    direction = "up" if change_percent > 5 else ("down" if change_percent < -5 else "stable")
                else:
                    change_percent = 100 if curr_val > 0 else 0
                    direction = "up" if curr_val > 0 else "stable"

                trends[key] = {"direction": direction, "change_percent": change_percent}

        return {"periods": comparisons, "trends": trends}

    def calculate_team_comparison(self, team_metrics_dict: Dict) -> Dict:
        """Compare metrics across teams

        Args:
            team_metrics_dict: Dictionary mapping team names to their metrics

        Returns:
            Dictionary with team comparison data
        """
        comparison = {}

        for team_name, metrics in team_metrics_dict.items():
            github = metrics.get("github", {})
            jira = metrics.get("jira", {})
            dora = metrics.get("dora", {})

            comparison[team_name] = {
                "prs": github.get("pr_count", 0),
                "reviews": github.get("review_count", 0),
                "commits": github.get("commit_count", 0),
                "avg_cycle_time": github.get("avg_cycle_time", 0),
                "jira_throughput": jira.get("throughput", {}).get("weekly_avg", 0),
                "jira_wip": jira.get("wip", {}).get("count", 0),
                "jira_flagged": jira.get("flagged", {}).get("count", 0),
                # DORA Metrics
                "dora_deployment_freq": dora.get("deployment_frequency", {}).get("per_week", 0),
                "dora_lead_time": dora.get("lead_time", {}).get("median_days", 0),
                "dora_cfr": dora.get("change_failure_rate", {}).get("rate_percent", 0),
                "dora_mttr": dora.get("mttr", {}).get("median_days", 0),
                "dora_level": dora.get("dora_level", {}).get("level", "low"),
                "dora_deployment_count": dora.get("deployment_frequency", {}).get("count", 0),
            }

        return comparison

    def get_all_metrics(self):
        """Get all calculated metrics"""
        return {
            "pr_metrics": self.calculate_pr_metrics(),
            "review_metrics": self.calculate_review_metrics(),
            "contributor_metrics": self.calculate_contributor_metrics(),
            "deployment_metrics": self.calculate_deployment_metrics(),
            "jira_metrics": self.calculate_jira_metrics(),
            "updated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def normalize(value, min_val, max_val):
        """Normalize a value to 0-100 scale.

        Delegates to PerformanceScorer.normalize()
        """
        return PerformanceScorer.normalize(value, min_val, max_val)

    @staticmethod
    def _load_performance_weights(weights: Optional[Dict] = None) -> Dict[str, float]:
        """Load performance weights from config or use defaults.

        Delegates to PerformanceScorer.load_performance_weights()
        """
        return PerformanceScorer.load_performance_weights(weights)

    @staticmethod
    def _normalize_team_size(metrics: Dict, all_metrics_list: List[Dict], team_size: int) -> tuple:
        """Normalize volume metrics to per-capita for fair team comparison.

        Delegates to PerformanceScorer.normalize_team_size()
        """
        return PerformanceScorer.normalize_team_size(metrics, all_metrics_list, team_size)

    @staticmethod
    def _extract_normalization_values(all_metrics_list: List[Dict]) -> Dict[str, List]:
        """Extract min/max values for normalization.

        Delegates to PerformanceScorer.extract_normalization_values()
        """
        return PerformanceScorer.extract_normalization_values(all_metrics_list)

    @staticmethod
    def _calculate_weighted_score(metrics: Dict, norm_values: Dict[str, list], weights: Dict[str, float]) -> float:
        """Calculate weighted score from normalized metrics.

        Delegates to PerformanceScorer.calculate_weighted_score()
        """
        return PerformanceScorer.calculate_weighted_score(metrics, norm_values, weights)

    @staticmethod
    def calculate_performance_score(metrics, all_metrics_list, team_size=None, weights=None):
        """Calculate overall performance score (0-100) for a team or person.

        Delegates to PerformanceScorer.calculate_performance_score()

        Args:
            metrics: Dict with individual metrics (prs, reviews, commits, etc.)
            all_metrics_list: List of all metrics dicts for normalization
            team_size: Optional team size for normalizing volume metrics (per-capita)
            weights: Optional dict of metric weights (defaults to config or balanced defaults)

        Returns:
            Float score between 0-100
        """
        return PerformanceScorer.calculate_performance_score(metrics, all_metrics_list, team_size, weights)
