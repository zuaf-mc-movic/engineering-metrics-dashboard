"""Performance scoring module for calculating team and person performance scores.

This module provides utilities for calculating composite performance scores
based on multiple metrics including GitHub activity, Jira throughput, and DORA metrics.
"""

from typing import Dict, List


class PerformanceScorer:
    """Utilities for calculating performance scores from metrics."""

    @staticmethod
    def normalize(value: float, min_val: float, max_val: float) -> float:
        """Normalize a value to 0-100 scale.

        Args:
            value: The value to normalize
            min_val: Minimum value in the range
            max_val: Maximum value in the range

        Returns:
            Normalized value between 0-100
        """
        if max_val == min_val:
            return 50.0  # All values equal, return middle score
        return ((value - min_val) / (max_val - min_val)) * 100

    @staticmethod
    def load_performance_weights(weights: Optional[Dict] = None) -> Dict[str, float]:
        """Load performance weights from config or use defaults.

        Args:
            weights: Optional dict of metric weights

        Returns:
            Dictionary of metric weights that sum to 1.0
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
                    "prs": 0.15,
                    "reviews": 0.15,
                    "commits": 0.10,
                    "cycle_time": 0.10,  # Lower is better
                    "jira_completed": 0.15,
                    "merge_rate": 0.05,
                    # DORA metrics
                    "deployment_frequency": 0.10,  # Higher is better
                    "lead_time": 0.10,  # Lower is better
                    "change_failure_rate": 0.05,  # Lower is better
                    "mttr": 0.05,  # Lower is better
                }
        return weights

    @staticmethod
    def normalize_team_size(metrics: Dict, all_metrics_list: List[Dict], team_size: int) -> tuple:
        """Normalize volume metrics to per-capita for fair team comparison.

        Args:
            metrics: Dict with individual metrics
            all_metrics_list: List of all metrics dicts
            team_size: Team size for normalization

        Returns:
            Tuple of (normalized_metrics, normalized_all_metrics_list)
        """
        if not team_size or team_size <= 0:
            return metrics, all_metrics_list

        metrics = metrics.copy()  # Don't modify original
        metrics["prs"] = metrics.get("prs", 0) / team_size
        metrics["reviews"] = metrics.get("reviews", 0) / team_size
        metrics["commits"] = metrics.get("commits", 0) / team_size
        metrics["jira_completed"] = metrics.get("jira_completed", 0) / team_size

        # Also normalize all_metrics_list for comparison
        normalized_all = [
            {
                **m,
                "prs": m.get("prs", 0) / m.get("team_size", team_size) if m.get("team_size", team_size) > 0 else 0,
                "reviews": (
                    m.get("reviews", 0) / m.get("team_size", team_size) if m.get("team_size", team_size) > 0 else 0
                ),
                "commits": (
                    m.get("commits", 0) / m.get("team_size", team_size) if m.get("team_size", team_size) > 0 else 0
                ),
                "jira_completed": (
                    m.get("jira_completed", 0) / m.get("team_size", team_size)
                    if m.get("team_size", team_size) > 0
                    else 0
                ),
            }
            for m in all_metrics_list
        ]
        return metrics, normalized_all

    @staticmethod
    def extract_normalization_values(all_metrics_list: List[Dict]) -> Dict[str, List]:
        """Extract min/max values for normalization.

        Args:
            all_metrics_list: List of all metrics dicts

        Returns:
            Dictionary mapping metric names to lists of values
        """
        return {
            "prs": [m.get("prs", 0) for m in all_metrics_list],
            "reviews": [m.get("reviews", 0) for m in all_metrics_list],
            "commits": [m.get("commits", 0) for m in all_metrics_list],
            "cycle_time": [m.get("cycle_time", 0) for m in all_metrics_list if m.get("cycle_time", 0) > 0],
            "jira_completed": [m.get("jira_completed", 0) for m in all_metrics_list],
            "merge_rate": [m.get("merge_rate", 0) for m in all_metrics_list],
            "deployment_frequency": [
                m.get("deployment_frequency", 0) for m in all_metrics_list if m.get("deployment_frequency") is not None
            ],
            "lead_time": [
                m.get("lead_time", 0)
                for m in all_metrics_list
                if m.get("lead_time") is not None and m.get("lead_time", 0) > 0
            ],
            "change_failure_rate": [
                m.get("change_failure_rate", 0) for m in all_metrics_list if m.get("change_failure_rate") is not None
            ],
            "mttr": [m.get("mttr", 0) for m in all_metrics_list if m.get("mttr") is not None and m.get("mttr", 0) > 0],
        }

    @staticmethod
    def calculate_weighted_score(metrics: Dict, norm_values: Dict[str, List], weights: Dict[str, float]) -> float:
        """Calculate weighted score from normalized metrics.

        Args:
            metrics: Dict with individual metrics
            norm_values: Dict mapping metric names to lists of values for normalization
            weights: Dict of metric weights

        Returns:
            Weighted score (0-100 scale before rounding)
        """
        score = 0.0

        # PRs: higher is better
        if norm_values["prs"] and max(norm_values["prs"]) > 0:
            prs_score = PerformanceScorer.normalize(
                metrics.get("prs", 0), min(norm_values["prs"]), max(norm_values["prs"])
            )
            score += prs_score * weights["prs"]

        # Reviews: higher is better
        if norm_values["reviews"] and max(norm_values["reviews"]) > 0:
            reviews_score = PerformanceScorer.normalize(
                metrics.get("reviews", 0), min(norm_values["reviews"]), max(norm_values["reviews"])
            )
            score += reviews_score * weights["reviews"]

        # Commits: higher is better
        if norm_values["commits"] and max(norm_values["commits"]) > 0:
            commits_score = PerformanceScorer.normalize(
                metrics.get("commits", 0), min(norm_values["commits"]), max(norm_values["commits"])
            )
            score += commits_score * weights["commits"]

        # Cycle time: lower is better (inverted)
        if norm_values["cycle_time"] and metrics.get("cycle_time", 0) > 0:
            cycle_time_score = PerformanceScorer.normalize(
                metrics.get("cycle_time", 0), min(norm_values["cycle_time"]), max(norm_values["cycle_time"])
            )
            score += (100 - cycle_time_score) * weights["cycle_time"]

        # Jira completed: higher is better
        if norm_values["jira_completed"] and max(norm_values["jira_completed"]) > 0:
            jira_score = PerformanceScorer.normalize(
                metrics.get("jira_completed", 0), min(norm_values["jira_completed"]), max(norm_values["jira_completed"])
            )
            score += jira_score * weights["jira_completed"]

        # Merge rate: higher is better
        if norm_values["merge_rate"] and max(norm_values["merge_rate"]) > 0:
            merge_rate_score = PerformanceScorer.normalize(
                metrics.get("merge_rate", 0), min(norm_values["merge_rate"]), max(norm_values["merge_rate"])
            )
            score += merge_rate_score * weights["merge_rate"]

        # DORA Metrics
        # Deployment Frequency: higher is better
        if "deployment_frequency" in weights and weights["deployment_frequency"] > 0:
            if (
                norm_values["deployment_frequency"]
                and max(norm_values["deployment_frequency"]) > 0
                and metrics.get("deployment_frequency") is not None
            ):
                deployment_freq_score = PerformanceScorer.normalize(
                    metrics.get("deployment_frequency", 0),
                    min(norm_values["deployment_frequency"]),
                    max(norm_values["deployment_frequency"]),
                )
                score += deployment_freq_score * weights["deployment_frequency"]

        # Lead Time: lower is better (inverted)
        if "lead_time" in weights and weights["lead_time"] > 0:
            if norm_values["lead_time"] and metrics.get("lead_time") is not None and metrics.get("lead_time", 0) > 0:
                lead_time_score = PerformanceScorer.normalize(
                    metrics.get("lead_time", 0), min(norm_values["lead_time"]), max(norm_values["lead_time"])
                )
                score += (100 - lead_time_score) * weights["lead_time"]

        # Change Failure Rate: lower is better (inverted)
        if "change_failure_rate" in weights and weights["change_failure_rate"] > 0:
            if (
                norm_values["change_failure_rate"]
                and max(norm_values["change_failure_rate"]) > 0
                and metrics.get("change_failure_rate") is not None
            ):
                cfr_score = PerformanceScorer.normalize(
                    metrics.get("change_failure_rate", 0),
                    min(norm_values["change_failure_rate"]),
                    max(norm_values["change_failure_rate"]),
                )
                score += (100 - cfr_score) * weights["change_failure_rate"]

        # MTTR: lower is better (inverted)
        if "mttr" in weights and weights["mttr"] > 0:
            if norm_values["mttr"] and metrics.get("mttr") is not None and metrics.get("mttr", 0) > 0:
                mttr_score = PerformanceScorer.normalize(
                    metrics.get("mttr", 0), min(norm_values["mttr"]), max(norm_values["mttr"])
                )
                score += (100 - mttr_score) * weights["mttr"]

        return score

    @staticmethod
    def calculate_performance_score(
        metrics: Dict, all_metrics_list: List[Dict], team_size: Optional[int] = None, weights: Optional[Dict] = None
    ) -> float:
        """Calculate overall performance score (0-100) for a team or person.

        This is the main entry point for performance scoring.

        Args:
            metrics: Dict with individual metrics (prs, reviews, commits, etc.)
            all_metrics_list: List of all metrics dicts for normalization
            team_size: Optional team size for normalizing volume metrics (per-capita)
            weights: Optional dict of metric weights (defaults to config or balanced defaults)

        Returns:
            Float score between 0-100
        """
        # Load weights
        weights = PerformanceScorer.load_performance_weights(weights)

        # Normalize for team size if provided
        metrics, all_metrics_list = PerformanceScorer.normalize_team_size(metrics, all_metrics_list, team_size)

        # Extract normalization values
        norm_values = PerformanceScorer.extract_normalization_values(all_metrics_list)

        # Calculate weighted score
        score = PerformanceScorer.calculate_weighted_score(metrics, norm_values, weights)

        return round(score, 1)
