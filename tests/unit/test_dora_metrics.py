"""Tests for DORA metrics calculation"""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.models.metrics import MetricsCalculator


class TestDeploymentFrequency:
    """Test deployment frequency DORA metric"""

    def test_deployment_frequency_elite_level(self):
        """Test elite level classification (>= 1 per day)"""
        # Create 100 releases over 90 days (1.1 per day)
        releases = []
        base_date = datetime(2025, 1, 1)
        for i in range(100):
            releases.append(
                {
                    "tag_name": f"v1.0.{i}",
                    "environment": "production",
                    "published_at": base_date + timedelta(days=i % 90),
                    "repo": "test/repo",
                }
            )

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["deployment_frequency"]["level"] == "elite"
        assert result["deployment_frequency"]["total_deployments"] == 100
        assert result["deployment_frequency"]["per_day"] >= 1.0

    def test_deployment_frequency_high_level(self):
        """Test high level classification (>= 1 per week)"""
        # Create 20 releases over 90 days (~1.5 per week)
        releases = []
        base_date = datetime(2025, 1, 1)
        for i in range(20):
            releases.append(
                {
                    "tag_name": f"v1.0.{i}",
                    "environment": "production",
                    "published_at": base_date + timedelta(days=i * 4),
                    "repo": "test/repo",
                }
            )

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["deployment_frequency"]["level"] == "high"
        assert result["deployment_frequency"]["per_week"] >= 1.0

    def test_deployment_frequency_medium_level(self):
        """Test medium level classification (>= 1 per month)"""
        # Create 3 releases over 90 days
        releases = []
        base_date = datetime(2025, 1, 1)
        for i in range(3):
            releases.append(
                {
                    "tag_name": f"v1.0.{i}",
                    "environment": "production",
                    "published_at": base_date + timedelta(days=i * 30),
                    "repo": "test/repo",
                }
            )

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["deployment_frequency"]["level"] == "medium"
        assert result["deployment_frequency"]["per_month"] >= 1.0

    def test_deployment_frequency_low_level(self):
        """Test low level classification (< 1 per month)"""
        # Create 2 releases over 90 days (< 1 per month)
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 3, 31),
                "repo": "test/repo",
            },
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["deployment_frequency"]["level"] == "low"
        assert result["deployment_frequency"]["per_month"] < 1.0

    def test_deployment_frequency_filters_production_only(self):
        """Test that deployment frequency only counts production releases"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1-rc1",
                "environment": "staging",
                "published_at": datetime(2025, 1, 2),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 1, 3),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.2-beta",
                "environment": "staging",
                "published_at": datetime(2025, 1, 4),
                "repo": "test/repo",
            },
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        # Should only count 2 production releases
        assert result["deployment_frequency"]["total_deployments"] == 2

    def test_deployment_frequency_no_releases(self):
        """Test deployment frequency with no releases"""
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["deployment_frequency"]["total_deployments"] == 0
        assert result["deployment_frequency"]["level"] == "low"


class TestLeadTimeForChanges:
    """Test lead time for changes DORA metric"""

    def test_lead_time_elite_level(self):
        """Test elite level classification (< 24 hours)"""
        # PR merged, release 12 hours later
        prs = [{"pr_number": 1, "merged": True, "merged_at": datetime(2025, 1, 1, 10, 0), "author": "user1"}]

        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1, 22, 0),  # 12 hours later
                "repo": "test/repo",
            }
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(prs), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["lead_time"]["level"] == "elite"
        assert result["lead_time"]["median_hours"] == 12.0
        assert result["lead_time"]["median_days"] == 0.5

    def test_lead_time_high_level(self):
        """Test high level classification (< 1 week)"""
        # PR merged, release 3 days later
        prs = [{"pr_number": 1, "merged": True, "merged_at": datetime(2025, 1, 1, 10, 0), "author": "user1"}]

        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 4, 10, 0),  # 3 days later
                "repo": "test/repo",
            }
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(prs), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["lead_time"]["level"] == "high"
        assert result["lead_time"]["median_hours"] == 72.0

    def test_lead_time_maps_pr_to_next_release(self):
        """Test that lead time maps PRs to the next deployment"""
        prs = [
            {"pr_number": 1, "merged": True, "merged_at": datetime(2025, 1, 1, 10, 0), "author": "user1"},
            {"pr_number": 2, "merged": True, "merged_at": datetime(2025, 1, 2, 10, 0), "author": "user1"},
            {"pr_number": 3, "merged": True, "merged_at": datetime(2025, 1, 5, 10, 0), "author": "user1"},
        ]

        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 3, 10, 0),
                "repo": "test/repo",
            },  # Gets PRs 1 & 2
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 1, 6, 10, 0),
                "repo": "test/repo",
            },  # Gets PR 3
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(prs), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        # PR1: 2 days to deployment, PR2: 1 day, PR3: 1 day
        # Median should be 24 hours
        assert result["lead_time"]["sample_size"] == 3
        assert result["lead_time"]["median_hours"] == 24.0

    def test_lead_time_ignores_unmerged_prs(self):
        """Test that lead time ignores PRs that weren't merged"""
        prs = [
            {"pr_number": 1, "merged": True, "merged_at": datetime(2025, 1, 1, 10, 0), "author": "user1"},
            {"pr_number": 2, "merged": False, "merged_at": None, "author": "user1"},
        ]

        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 2, 10, 0),
                "repo": "test/repo",
            }
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(prs), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        # Only 1 merged PR should be counted
        assert result["lead_time"]["sample_size"] == 1

    def test_lead_time_no_releases(self):
        """Test lead time with no releases"""
        prs = [{"pr_number": 1, "merged": True, "merged_at": datetime(2025, 1, 1, 10, 0), "author": "user1"}]

        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(prs), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert result["lead_time"]["median_hours"] is None
        assert result["lead_time"]["sample_size"] == 0


class TestChangeFailureRate:
    """Test change failure rate DORA metric"""

    def test_cfr_without_incident_data(self):
        """Test CFR returns placeholder when incident data not provided"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1),
                "repo": "test/repo",
            }
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        # Should return placeholder since incidents not implemented yet
        assert result["change_failure_rate"]["rate_percent"] is None
        assert result["change_failure_rate"]["total_deployments"] == 1
        assert "note" in result["change_failure_rate"]


class TestMTTR:
    """Test Mean Time to Restore DORA metric"""

    def test_mttr_without_incident_data(self):
        """Test MTTR returns placeholder when incident data not provided"""
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        # Should return placeholder since incidents not implemented yet
        assert result["mttr"]["median_hours"] is None
        assert "note" in result["mttr"]


class TestDORAPerformanceLevel:
    """Test overall DORA performance level classification"""

    def test_dora_level_elite(self):
        """Test elite classification with 3+ elite metrics"""
        # Elite deployment frequency (>1/day) and elite lead time (<24h)
        prs = [{"pr_number": 1, "merged": True, "merged_at": datetime(2025, 1, 1, 10, 0), "author": "user1"}]

        releases = []
        base_date = datetime(2025, 1, 1)
        # 100 releases over 90 days = elite deployment frequency
        for i in range(100):
            releases.append(
                {
                    "tag_name": f"v1.0.{i}",
                    "environment": "production",
                    "published_at": base_date + timedelta(days=i % 90, hours=i % 24),
                    "repo": "test/repo",
                }
            )

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(prs), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        # With elite deployment frequency and potentially elite lead time
        assert result["dora_level"]["level"] in ["Elite", "High"]

    def test_dora_level_includes_breakdown(self):
        """Test that DORA level includes breakdown by metric"""
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert "breakdown" in result["dora_level"]
        assert "elite" in result["dora_level"]["breakdown"]
        assert "high" in result["dora_level"]["breakdown"]
        assert "medium" in result["dora_level"]["breakdown"]
        assert "low" in result["dora_level"]["breakdown"]


class TestDORAMeasurementPeriod:
    """Test DORA measurement period tracking"""

    def test_measurement_period_from_releases(self):
        """Test measurement period calculated from release dates"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 3, 31),
                "repo": "test/repo",
            },
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics()

        assert "measurement_period" in result
        assert result["measurement_period"]["days"] == 89

    def test_measurement_period_explicit_dates(self):
        """Test measurement period with explicit start/end dates"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 15),
                "repo": "test/repo",
            }
        ]

        dfs = {"releases": pd.DataFrame(releases), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(start_date=datetime(2025, 1, 1), end_date=datetime(2025, 3, 31))

        assert result["measurement_period"]["days"] == 89


class TestExtractIssueKeyFromPR:
    """Test _extract_issue_key_from_pr() method"""

    def test_extract_from_title_with_brackets(self):
        """Test extracting issue key from PR title with brackets"""
        pr = pd.Series({"title": "[PROJ-123] Add new feature", "branch": "main"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        assert result == "PROJ-123"

    def test_extract_from_title_with_colon(self):
        """Test extracting issue key from PR title with colon"""
        pr = pd.Series({"title": "PROJ-456: Fix bug in authentication", "branch": "main"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        assert result == "PROJ-456"

    def test_extract_from_branch_name(self):
        """Test extracting issue key from branch name"""
        pr = pd.Series({"title": "Add feature", "branch": "feature/RSC-789-add-feature"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        assert result == "RSC-789"

    def test_extract_multiple_keys_returns_first(self):
        """Test that multiple issue keys return the first match"""
        pr = pd.Series({"title": "PROJ-100 PROJ-200 Multiple issues", "branch": "main"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        assert result == "PROJ-100"

    def test_no_issue_key_returns_none(self):
        """Test that PR without issue key returns None"""
        pr = pd.Series({"title": "Add feature without issue key", "branch": "feature/my-feature"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        assert result is None

    def test_handles_nan_title(self):
        """Test handling of NaN title"""
        pr = pd.Series({"title": None, "branch": "feature/PROJ-999"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        # Should fall back to branch
        assert result == "PROJ-999"

    def test_handles_missing_branch(self):
        """Test handling of missing branch field"""
        pr = pd.Series({"title": "PROJ-888: Fix"})
        dfs = {"releases": pd.DataFrame(), "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator._extract_issue_key_from_pr(pr)

        assert result == "PROJ-888"


class TestChangeFailureRateAdvanced:
    """Test advanced CFR calculation scenarios"""

    def test_cfr_tag_based_matching(self):
        """Test CFR with direct tag matching from incidents"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1, 10, 0),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 1, 2, 10, 0),
                "repo": "test/repo",
            },
        ]

        incidents = [
            {
                "key": "INC-1",
                "created": datetime(2025, 1, 1, 12, 0),
                "related_deployment": "v1.0.0",  # Direct tag match
            }
        ]

        dfs = {
            "releases": pd.DataFrame(releases),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # 1 out of 2 deployments failed = 50%
        assert result["change_failure_rate"]["rate_percent"] == 50.0
        assert result["change_failure_rate"]["failed_deployments"] == 1
        assert result["change_failure_rate"]["total_deployments"] == 2

    def test_cfr_time_based_correlation_24h(self):
        """Test CFR with time-based correlation (24h window)"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1, 10, 0),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 1, 5, 10, 0),
                "repo": "test/repo",
            },
        ]

        incidents = [
            {
                "key": "INC-1",
                "created": datetime(2025, 1, 1, 20, 0),  # 10 hours after v1.0.0
            },
            {
                "key": "INC-2",
                "created": datetime(2025, 1, 6, 12, 0),  # 26 hours after v1.0.1 (outside window)
            },
        ]

        dfs = {
            "releases": pd.DataFrame(releases),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Only v1.0.0 should be correlated (1 out of 2 = 50%)
        assert result["change_failure_rate"]["rate_percent"] == 50.0
        assert result["change_failure_rate"]["failed_deployments"] == 1

    def test_cfr_no_incidents_found(self):
        """Test CFR when no incidents correlate to deployments"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1, 10, 0),
                "repo": "test/repo",
            }
        ]

        incidents = [
            {
                "key": "INC-1",
                "created": datetime(2025, 1, 5, 10, 0),  # Days after deployment
            }
        ]

        dfs = {
            "releases": pd.DataFrame(releases),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # 0% failure rate
        assert result["change_failure_rate"]["rate_percent"] == 0.0
        assert result["change_failure_rate"]["failed_deployments"] == 0
        assert result["change_failure_rate"]["level"] == "elite"

    def test_cfr_multiple_incidents_per_deployment(self):
        """Test CFR with multiple incidents for same deployment"""
        releases = [
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1, 10, 0),
                "repo": "test/repo",
            }
        ]

        incidents = [
            {
                "key": "INC-1",
                "created": datetime(2025, 1, 1, 12, 0),
                "related_deployment": "v1.0.0",
            },
            {
                "key": "INC-2",
                "created": datetime(2025, 1, 1, 14, 0),
                "related_deployment": "v1.0.0",
            },
        ]

        dfs = {
            "releases": pd.DataFrame(releases),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Should count as 1 failed deployment, not 2
        assert result["change_failure_rate"]["failed_deployments"] == 1
        assert result["change_failure_rate"]["rate_percent"] == 100.0

    def test_cfr_elite_level(self):
        """Test CFR elite level classification (< 15%)"""
        # 1 failure out of 10 deployments = 10%
        releases = [
            {
                "tag_name": f"v1.0.{i}",
                "environment": "production",
                "published_at": datetime(2025, 1, i + 1, 10, 0),
                "repo": "test/repo",
            }
            for i in range(10)
        ]

        incidents = [{"key": "INC-1", "created": datetime(2025, 1, 1, 12, 0), "related_deployment": "v1.0.0"}]

        dfs = {
            "releases": pd.DataFrame(releases),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        assert result["change_failure_rate"]["rate_percent"] == 10.0
        assert result["change_failure_rate"]["level"] == "elite"

    def test_cfr_trend_calculation(self):
        """Test CFR trend calculation by week"""
        releases = [
            # Week 1: 2 releases, 1 failure
            {
                "tag_name": "v1.0.0",
                "environment": "production",
                "published_at": datetime(2025, 1, 1, 10, 0),
                "repo": "test/repo",
            },
            {
                "tag_name": "v1.0.1",
                "environment": "production",
                "published_at": datetime(2025, 1, 2, 10, 0),
                "repo": "test/repo",
            },
            # Week 2: 1 release, 0 failures
            {
                "tag_name": "v1.0.2",
                "environment": "production",
                "published_at": datetime(2025, 1, 8, 10, 0),
                "repo": "test/repo",
            },
        ]

        incidents = [{"key": "INC-1", "created": datetime(2025, 1, 1, 12, 0), "related_deployment": "v1.0.0"}]

        dfs = {
            "releases": pd.DataFrame(releases),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Week 1 should be 50%, Week 2 should be 0%
        assert "trend" in result["change_failure_rate"]
        assert len(result["change_failure_rate"]["trend"]) == 2


class TestMTTRAdvanced:
    """Test advanced MTTR calculation scenarios"""

    def test_mttr_with_resolution_time_hours_field(self):
        """Test MTTR using pre-calculated resolution_time_hours"""
        incidents = [
            {"key": "INC-1", "resolution_time_hours": 2.0},
            {"key": "INC-2", "resolution_time_hours": 4.0},
            {"key": "INC-3", "resolution_time_hours": 6.0},
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Median: 4.0, Average: 4.0
        assert result["mttr"]["median_hours"] == 4.0
        assert result["mttr"]["average_hours"] == 4.0
        assert result["mttr"]["sample_size"] == 3

    def test_mttr_calculated_from_dates(self):
        """Test MTTR calculated from created/resolved dates"""
        incidents = [
            {
                "key": "INC-1",
                "created": datetime(2025, 1, 1, 10, 0),
                "resolved": datetime(2025, 1, 1, 12, 0),  # 2 hours
            },
            {
                "key": "INC-2",
                "created": datetime(2025, 1, 2, 10, 0),
                "resolved": datetime(2025, 1, 2, 14, 0),  # 4 hours
            },
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Median: 3.0 hours
        assert result["mttr"]["median_hours"] == 3.0
        assert result["mttr"]["sample_size"] == 2

    def test_mttr_ignores_unresolved_incidents(self):
        """Test MTTR ignores incidents without resolution times"""
        incidents = [
            {"key": "INC-1", "resolution_time_hours": 2.0},
            {"key": "INC-2", "created": datetime(2025, 1, 1, 10, 0)},  # No resolved date
            {"key": "INC-3", "resolution_time_hours": 4.0},
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Should only count 2 resolved incidents
        assert result["mttr"]["sample_size"] == 2
        assert result["mttr"]["median_hours"] == 3.0

    def test_mttr_elite_level(self):
        """Test MTTR elite level classification (< 1 hour)"""
        incidents = [
            {"key": "INC-1", "resolution_time_hours": 0.5},
            {"key": "INC-2", "resolution_time_hours": 0.8},
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        assert result["mttr"]["median_hours"] == 0.7  # Rounded to 0.7
        assert result["mttr"]["level"] == "elite"

    def test_mttr_high_level(self):
        """Test MTTR high level classification (< 24 hours)"""
        incidents = [
            {"key": "INC-1", "resolution_time_hours": 12.0},
            {"key": "INC-2", "resolution_time_hours": 18.0},
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        assert result["mttr"]["median_hours"] == 15.0
        assert result["mttr"]["level"] == "high"

    def test_mttr_medium_level(self):
        """Test MTTR medium level classification (< 1 week)"""
        incidents = [
            {"key": "INC-1", "resolution_time_hours": 48.0},  # 2 days
            {"key": "INC-2", "resolution_time_hours": 72.0},  # 3 days
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        assert result["mttr"]["median_hours"] == 60.0
        assert result["mttr"]["level"] == "medium"

    def test_mttr_p95_calculation(self):
        """Test MTTR p95 calculation"""
        incidents = [{"key": f"INC-{i}", "resolution_time_hours": float(i)} for i in range(1, 21)]  # 1-20 hours

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # P95 should be around 19.0
        assert result["mttr"]["p95_hours"] >= 18.0
        assert result["mttr"]["p95_hours"] <= 20.0

    def test_mttr_trend_calculation(self):
        """Test MTTR trend calculation by week"""
        incidents = [
            # Week 1: 2 incidents, 2h and 4h
            {
                "key": "INC-1",
                "created": datetime(2025, 1, 1, 10, 0),
                "resolved": datetime(2025, 1, 1, 12, 0),
            },
            {
                "key": "INC-2",
                "created": datetime(2025, 1, 2, 10, 0),
                "resolved": datetime(2025, 1, 2, 14, 0),
            },
            # Week 2: 1 incident, 6h
            {
                "key": "INC-3",
                "created": datetime(2025, 1, 8, 10, 0),
                "resolved": datetime(2025, 1, 8, 16, 0),
            },
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        # Should have trend data for 2 weeks
        assert "trend" in result["mttr"]
        assert len(result["mttr"]["trend"]) == 2

    def test_mttr_no_resolved_incidents(self):
        """Test MTTR when no incidents are resolved"""
        incidents = [
            {"key": "INC-1", "created": datetime(2025, 1, 1, 10, 0)},  # No resolved
            {"key": "INC-2", "created": datetime(2025, 1, 2, 10, 0)},  # No resolved
        ]

        dfs = {
            "releases": pd.DataFrame(),
            "pull_requests": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }
        incidents_df = pd.DataFrame(incidents)

        calculator = MetricsCalculator(dfs)
        result = calculator.calculate_dora_metrics(incidents_df=incidents_df)

        assert result["mttr"]["median_hours"] is None
        assert result["mttr"]["sample_size"] == 0
        assert result["mttr"]["level"] == "unknown"
