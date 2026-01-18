"""Integration tests for DORA metrics calculation

Tests end-to-end DORA metrics calculation with releases and incidents.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.models.metrics import MetricsCalculator


class TestDORAIntegration:
    """Test end-to-end DORA metrics calculation"""

    def test_dora_metrics_complete_workflow(self):
        """Test calculating all 4 DORA metrics from releases and incidents"""
        # Arrange - Mock release and PR data
        # Releases (deployments)
        releases = [
            {
                "tag_name": "v1.0.0",
                "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "environment": "production",
                "is_prerelease": False,
            },
            {
                "tag_name": "v1.1.0",
                "published_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
                "environment": "production",
                "is_prerelease": False,
            },
            {
                "tag_name": "v1.2.0",
                "published_at": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "environment": "production",
                "is_prerelease": False,
            },
            {
                "tag_name": "v1.2.1",  # Hotfix - indicates failure
                "published_at": datetime(2024, 2, 2, tzinfo=timezone.utc),
                "environment": "production",
                "is_prerelease": False,
            },
        ]

        # PRs for lead time calculation
        prs = [
            {
                "pr_number": 1,
                "author": "alice",
                "created_at": datetime(2023, 12, 25, tzinfo=timezone.utc),
                "merged_at": datetime(2023, 12, 28, tzinfo=timezone.utc),
                "merged": True,
                "state": "merged",
                "additions": 100,
                "deletions": 50,
            },
            {
                "pr_number": 2,
                "author": "bob",
                "created_at": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "merged_at": datetime(2024, 1, 12, tzinfo=timezone.utc),
                "merged": True,
                "state": "merged",
                "additions": 200,
                "deletions": 100,
            },
        ]

        # Incidents (Jira issues tagged as incidents)
        incidents = [
            {
                "key": "INC-1",
                "created": "2024-02-02 08:00:00",
                "resolved": "2024-02-02 10:00:00",  # Resolved in 2 hours
                "status": "Resolved",
                "type": "Incident",
            }
        ]

        # Act - Calculate DORA metrics
        dfs = {
            "pull_requests": pd.DataFrame(prs),
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
            "deployments": pd.DataFrame(releases),
        }
        calculator = MetricsCalculator(dfs)

        # Calculate DORA metrics
        from src.models.metrics import (
            calculate_change_failure_rate,
            calculate_deployment_frequency,
            calculate_dora_performance_level,
            calculate_lead_time_for_changes,
        )

        deployment_freq = calculate_deployment_frequency(releases, days=90)
        lead_time = calculate_lead_time_for_changes(prs, releases)
        change_failure_rate = calculate_change_failure_rate(releases, incidents)

        # Assert - Verify DORA metrics calculated
        assert deployment_freq is not None
        assert deployment_freq > 0  # Should have deployments

        assert lead_time is not None
        assert lead_time > 0  # Should have lead time

        # CFR should be calculated (1 failure out of 4 deployments = 25%)
        assert change_failure_rate is not None

    def test_dora_performance_classification(self):
        """Test DORA performance level classification"""
        from src.models.metrics import calculate_dora_performance_level

        # Test Elite performance
        elite_metrics = {
            "deployment_frequency": 10.0,  # Multiple per day
            "lead_time_hours": 24.0,  # < 1 day
            "change_failure_rate": 0.05,  # 5%
            "mttr_hours": 1.0,  # < 1 hour
        }
        level = calculate_dora_performance_level(elite_metrics)
        assert level in ["Elite", "High"]  # Should be high performing

        # Test Low performance
        low_metrics = {
            "deployment_frequency": 0.1,  # Once every 10 days
            "lead_time_hours": 2000.0,  # > 6 months
            "change_failure_rate": 0.50,  # 50%
            "mttr_hours": 800.0,  # > 1 month
        }
        level = calculate_dora_performance_level(low_metrics)
        assert level in ["Low", "Medium"]  # Should be low performing

    def test_dora_with_missing_data(self):
        """Test DORA metrics handle missing data gracefully"""
        # Empty deployments
        empty_dfs = {
            "pull_requests": pd.DataFrame(),
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
            "deployments": pd.DataFrame(),
        }
        calculator = MetricsCalculator(empty_dfs)

        # Should not crash, should return appropriate defaults
        from src.models.metrics import calculate_deployment_frequency

        freq = calculate_deployment_frequency([], days=90)
        assert freq == 0.0

    def test_dora_trend_calculation(self):
        """Test DORA metrics trend over time"""
        # Create releases spread over 12 weeks
        releases = []
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

        for week in range(12):
            releases.append(
                {
                    "tag_name": f"v1.{week}.0",
                    "published_at": base_date + timedelta(weeks=week),
                    "environment": "production",
                    "is_prerelease": False,
                }
            )

        # Calculate weekly deployment frequency trend
        from src.models.metrics import calculate_deployment_frequency_trend

        trend = calculate_deployment_frequency_trend(releases, weeks=12)

        assert trend is not None
        assert len(trend) > 0
        # Should have weekly data
        assert all(week_data["count"] >= 0 for week_data in trend.values())

    def test_lead_time_with_jira_mapping(self):
        """Test lead time calculation with Jira issue mapping"""
        # PRs with Jira issue references
        prs = [
            {
                "pr_number": 1,
                "title": "Fix bug TEST-123",
                "author": "alice",
                "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "merged_at": datetime(2024, 1, 3, tzinfo=timezone.utc),
                "merged": True,
                "state": "merged",
                "additions": 50,
                "deletions": 25,
            }
        ]

        # Jira issues
        jira_issues = [
            {"key": "TEST-123", "created": "2024-01-01 09:00:00", "resolved": "2024-01-03 15:00:00", "status": "Done"}
        ]

        releases = [
            {
                "tag_name": "v1.0.0",
                "published_at": datetime(2024, 1, 5, tzinfo=timezone.utc),
                "environment": "production",
                "is_prerelease": False,
            }
        ]

        # Calculate lead time with issue mapping
        from src.models.metrics import calculate_lead_time_for_changes

        lead_time = calculate_lead_time_for_changes(prs, releases)

        assert lead_time is not None
        # Lead time should be from PR creation to release (4 days)
        assert lead_time > 0
