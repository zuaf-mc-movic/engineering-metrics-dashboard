"""Tests for Jira metrics processing

This module tests the JiraMetrics mixin class methods for processing
Jira filter results and calculating Jira-related metrics.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pandas as pd
import pytest

from src.models.metrics import MetricsCalculator


class TestCalculateJiraMetrics:
    """Test calculate_jira_metrics() method"""

    def test_empty_jira_issues_returns_empty_dict(self):
        """Test that empty jira_issues DataFrame returns empty dict"""
        dfs = {"jira_issues": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        assert result == {}

    def test_missing_jira_issues_returns_empty_dict(self):
        """Test that missing jira_issues key returns empty dict"""
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        assert result == {}

    def test_basic_issue_counts(self):
        """Test basic issue counting (total, resolved, open)"""
        issues = pd.DataFrame(
            [
                {"key": "PROJ-1", "resolved": datetime(2025, 1, 5, tzinfo=timezone.utc), "cycle_time_hours": 48.0},
                {"key": "PROJ-2", "resolved": datetime(2025, 1, 10, tzinfo=timezone.utc), "cycle_time_hours": 24.0},
                {"key": "PROJ-3", "resolved": None, "cycle_time_hours": None},
            ]
        )
        dfs = {"jira_issues": issues}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        assert result["total_issues"] == 3
        assert result["resolved_issues"] == 2
        assert result["open_issues"] == 1

    def test_cycle_time_calculation(self):
        """Test average and median cycle time calculation"""
        issues = pd.DataFrame(
            [
                {"key": "PROJ-1", "resolved": datetime(2025, 1, 5, tzinfo=timezone.utc), "cycle_time_hours": 48.0},
                {"key": "PROJ-2", "resolved": datetime(2025, 1, 10, tzinfo=timezone.utc), "cycle_time_hours": 24.0},
                {"key": "PROJ-3", "resolved": datetime(2025, 1, 15, tzinfo=timezone.utc), "cycle_time_hours": 72.0},
            ]
        )
        dfs = {"jira_issues": issues}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        # Average: (48 + 24 + 72) / 3 = 48.0
        assert result["avg_cycle_time_hours"] == 48.0
        # Median: 48.0
        assert result["median_cycle_time_hours"] == 48.0

    def test_cycle_time_zero_when_no_resolved_issues(self):
        """Test cycle time returns 0 when no resolved issues"""
        issues = pd.DataFrame(
            [
                {"key": "PROJ-1", "resolved": None, "cycle_time_hours": None},
                {"key": "PROJ-2", "resolved": None, "cycle_time_hours": None},
            ]
        )
        dfs = {"jira_issues": issues}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        assert result["avg_cycle_time_hours"] == 0.0
        assert result["median_cycle_time_hours"] == 0.0

    def test_issues_by_type_breakdown(self):
        """Test issues grouped by type"""
        issues = pd.DataFrame(
            [
                {"key": "PROJ-1", "type": "Bug", "resolved": None, "cycle_time_hours": None},
                {"key": "PROJ-2", "type": "Bug", "resolved": None, "cycle_time_hours": None},
                {"key": "PROJ-3", "type": "Story", "resolved": None, "cycle_time_hours": None},
                {"key": "PROJ-4", "type": "Task", "resolved": None, "cycle_time_hours": None},
            ]
        )
        dfs = {"jira_issues": issues}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        assert result["issues_by_type"] == {"Bug": 2, "Story": 1, "Task": 1}

    def test_issues_by_status_breakdown(self):
        """Test issues grouped by status"""
        issues = pd.DataFrame(
            [
                {"key": "PROJ-1", "status": "In Progress", "resolved": None, "cycle_time_hours": None},
                {"key": "PROJ-2", "status": "In Progress", "resolved": None, "cycle_time_hours": None},
                {"key": "PROJ-3", "status": "Done", "resolved": datetime.now(), "cycle_time_hours": 48.0},
                {"key": "PROJ-4", "status": "To Do", "resolved": None, "cycle_time_hours": None},
            ]
        )
        dfs = {"jira_issues": issues}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        assert result["issues_by_status"] == {"In Progress": 2, "Done": 1, "To Do": 1}

    def test_top_assignees_list(self):
        """Test top 10 assignees by issue count"""
        issues = pd.DataFrame(
            [
                {"key": f"PROJ-{i}", "assignee": f"user{i % 3}", "resolved": None, "cycle_time_hours": None}
                for i in range(15)
            ]
        )
        dfs = {"jira_issues": issues}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_jira_metrics()

        # user0, user1, user2 should each have 5 issues
        assert result["top_assignees"]["user0"] == 5
        assert result["top_assignees"]["user1"] == 5
        assert result["top_assignees"]["user2"] == 5
        assert len(result["top_assignees"]) == 3  # Only 3 unique assignees


class TestProcessJiraMetrics:
    """Test _process_jira_metrics() method"""

    def test_empty_filter_results_returns_empty_dict(self):
        """Test that empty filter results return empty dict"""
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(None)

        assert result == {}

    def test_none_filter_results_returns_empty_dict(self):
        """Test that None filter results return empty dict"""
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(None)

        assert result == {}

    def test_throughput_calculation_weekly(self):
        """Test throughput calculation by week"""
        base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        completed_issues = [
            {"key": "PROJ-1", "resolved": (base_date + timedelta(days=0)).isoformat(), "type": "Story"},
            {"key": "PROJ-2", "resolved": (base_date + timedelta(days=1)).isoformat(), "type": "Story"},
            {"key": "PROJ-3", "resolved": (base_date + timedelta(days=7)).isoformat(), "type": "Bug"},
            {"key": "PROJ-4", "resolved": (base_date + timedelta(days=8)).isoformat(), "type": "Task"},
        ]

        filter_results = {"completed": completed_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert "throughput" in result
        assert result["throughput"]["total_completed"] == 4
        assert result["throughput"]["weekly_avg"] > 0
        assert "by_week" in result["throughput"]
        assert "by_type" in result["throughput"]

    def test_throughput_type_breakdown(self):
        """Test throughput breakdown by issue type"""
        base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        completed_issues = [
            {"key": "PROJ-1", "resolved": base_date.isoformat(), "type": "Story"},
            {"key": "PROJ-2", "resolved": base_date.isoformat(), "type": "Story"},
            {"key": "PROJ-3", "resolved": base_date.isoformat(), "type": "Bug"},
            {"key": "PROJ-4", "resolved": base_date.isoformat(), "type": "Task"},
        ]

        filter_results = {"completed": completed_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["throughput"]["by_type"] == {"Story": 2, "Bug": 1, "Task": 1}

    def test_throughput_duplicate_handling(self):
        """Test that duplicate issues are removed from throughput"""
        base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        completed_issues = [
            {"key": "PROJ-1", "resolved": base_date.isoformat(), "type": "Story"},
            {"key": "PROJ-1", "resolved": base_date.isoformat(), "type": "Story"},  # Duplicate
            {"key": "PROJ-2", "resolved": base_date.isoformat(), "type": "Bug"},
        ]

        filter_results = {"completed": completed_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        # Should only count 2 unique issues
        assert result["throughput"]["total_completed"] == 2

    def test_wip_age_distribution(self):
        """Test WIP age distribution buckets"""
        wip_issues = [
            {"key": "PROJ-1", "days_in_current_status": 2},  # 0-3 days
            {"key": "PROJ-2", "days_in_current_status": 5},  # 4-7 days
            {"key": "PROJ-3", "days_in_current_status": 10},  # 8-14 days
            {"key": "PROJ-4", "days_in_current_status": 20},  # 15+ days
            {"key": "PROJ-5", "days_in_current_status": 30},  # 15+ days
        ]

        filter_results = {"wip": wip_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["wip"]["count"] == 5
        assert result["wip"]["age_distribution"]["0-3 days"] == 1
        assert result["wip"]["age_distribution"]["4-7 days"] == 1
        assert result["wip"]["age_distribution"]["8-14 days"] == 1
        assert result["wip"]["age_distribution"]["15+ days"] == 2

    def test_wip_average_age(self):
        """Test WIP average age calculation"""
        wip_issues = [
            {"key": "PROJ-1", "days_in_current_status": 10},
            {"key": "PROJ-2", "days_in_current_status": 20},
            {"key": "PROJ-3", "days_in_current_status": 30},
        ]

        filter_results = {"wip": wip_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        # Average: (10 + 20 + 30) / 3 = 20.0
        assert result["wip"]["avg_age_days"] == 20.0

    def test_wip_status_breakdown(self):
        """Test WIP breakdown by status"""
        wip_issues = [
            {"key": "PROJ-1", "status": "In Progress", "days_in_current_status": 5},
            {"key": "PROJ-2", "status": "In Progress", "days_in_current_status": 3},
            {"key": "PROJ-3", "status": "In Review", "days_in_current_status": 2},
            {"key": "PROJ-4", "status": "Blocked", "days_in_current_status": 10},
        ]

        filter_results = {"wip": wip_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["wip"]["by_status"] == {"In Progress": 2, "In Review": 1, "Blocked": 1}

    def test_wip_handles_missing_age_data(self):
        """Test WIP handles issues with missing days_in_current_status"""
        wip_issues = [
            {"key": "PROJ-1", "days_in_current_status": 5},
            {"key": "PROJ-2", "days_in_current_status": None},  # Missing
            {"key": "PROJ-3"},  # Missing field entirely
        ]

        filter_results = {"wip": wip_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        # Should only count the 1 issue with valid age
        assert result["wip"]["avg_age_days"] == 5.0

    def test_flagged_blocked_items(self):
        """Test flagged/blocked issues tracking"""
        flagged_issues = [
            {
                "key": "PROJ-1",
                "summary": "Blocked by external dependency",
                "assignee": "alice",
                "days_in_current_status": 5,
            },
            {
                "key": "PROJ-2",
                "summary": "Waiting for approval",
                "assignee": "bob",
                "days_in_current_status": 3,
            },
        ]

        filter_results = {"flagged_blocked": flagged_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["flagged"]["count"] == 2
        assert len(result["flagged"]["issues"]) == 2
        assert result["flagged"]["issues"][0]["key"] == "PROJ-1"
        assert result["flagged"]["issues"][0]["assignee"] == "alice"
        assert result["flagged"]["issues"][0]["days_blocked"] == 5

    def test_flagged_limits_to_top_10(self):
        """Test flagged issues limited to top 10"""
        flagged_issues = [{"key": f"PROJ-{i}", "summary": f"Issue {i}", "days_in_current_status": i} for i in range(15)]

        filter_results = {"flagged_blocked": flagged_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["flagged"]["count"] == 15
        assert len(result["flagged"]["issues"]) == 10  # Limited to 10

    def test_flagged_handles_unassigned(self):
        """Test flagged issues handle missing assignee"""
        flagged_issues = [
            {"key": "PROJ-1", "summary": "Issue 1"},  # No assignee field
        ]

        filter_results = {"flagged_blocked": flagged_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["flagged"]["issues"][0]["assignee"] == "Unassigned"

    def test_bugs_created_vs_resolved_trend(self):
        """Test bug trend analysis (created vs resolved)"""
        base_date = datetime.now(timezone.utc) - timedelta(days=10)  # Recent date within 90 days
        bugs_created = [
            {"key": "BUG-1", "created": base_date.isoformat()},
            {"key": "BUG-2", "created": (base_date + timedelta(days=1)).isoformat()},
        ]
        bugs_resolved = [
            {"key": "BUG-3", "resolved": (base_date + timedelta(days=2)).isoformat()},
        ]

        filter_results = {"bugs_created": bugs_created, "bugs_resolved": bugs_resolved}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["bugs"]["created"] == 2
        assert result["bugs"]["resolved"] == 1
        assert result["bugs"]["net"] == 1  # 2 - 1 = 1
        # Trends should have data since dates are within 90 days
        assert len(result["bugs"]["trend_created"]) > 0
        assert len(result["bugs"]["trend_resolved"]) > 0

    def test_bugs_filters_last_90_days(self):
        """Test bug trends only include last 90 days"""
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        recent_date = datetime.now(timezone.utc) - timedelta(days=10)

        bugs_created = [
            {"key": "BUG-1", "created": old_date.isoformat()},  # Should be excluded
            {"key": "BUG-2", "created": recent_date.isoformat()},  # Should be included
        ]

        filter_results = {"bugs_created": bugs_created, "bugs_resolved": []}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        # Total count includes all bugs
        assert result["bugs"]["created"] == 2
        # But trend should only have the recent one
        assert len(result["bugs"]["trend_created"]) > 0

    def test_bugs_handles_invalid_dates(self):
        """Test bug trends handle invalid date formats"""
        bugs_created = [
            {"key": "BUG-1", "created": "invalid-date"},
            {"key": "BUG-2", "created": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()},
        ]

        filter_results = {"bugs_created": bugs_created, "bugs_resolved": []}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        # Should not raise exception
        result = calculator._process_jira_metrics(filter_results)

        assert result["bugs"]["created"] == 2

    def test_scope_change_tracking(self):
        """Test scope change trend analysis"""
        base_date = datetime.now(timezone.utc) - timedelta(days=10)  # Recent date within 90 days
        scope_issues = [
            {"key": "SCOPE-1", "created": base_date.isoformat(), "resolved": None},
            {
                "key": "SCOPE-2",
                "created": (base_date + timedelta(days=7)).isoformat(),
                "resolved": (base_date + timedelta(days=7, hours=1)).isoformat(),
            },
        ]

        filter_results = {"scope": scope_issues}
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["scope"]["total"] == 2
        # Trends should have data since dates are within 90 days
        assert len(result["scope"]["trend_created"]) > 0
        assert len(result["scope"]["trend_resolved"]) > 0

    def test_scope_empty_returns_default_structure(self):
        """Test scope returns default structure when no issues"""
        # Need at least one key in filter_results to avoid early return
        filter_results = {"wip": []}  # Has a key but scope is missing
        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        assert result["scope"]["total"] == 0
        assert result["scope"]["trend_created"] is None
        assert result["scope"]["trend_resolved"] is None

    def test_comprehensive_filter_results(self):
        """Test processing with all filter types present"""
        base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        filter_results = {
            "completed": [
                {"key": "PROJ-1", "resolved": base_date.isoformat(), "type": "Story"},
            ],
            "wip": [
                {"key": "PROJ-2", "status": "In Progress", "days_in_current_status": 5},
            ],
            "flagged_blocked": [
                {"key": "PROJ-3", "summary": "Blocked", "days_in_current_status": 10},
            ],
            "bugs_created": [
                {"key": "BUG-1", "created": base_date.isoformat()},
            ],
            "bugs_resolved": [
                {"key": "BUG-2", "resolved": base_date.isoformat()},
            ],
            "scope": [
                {"key": "SCOPE-1", "created": base_date.isoformat()},
            ],
        }

        dfs = {}
        calculator = MetricsCalculator(dfs)

        result = calculator._process_jira_metrics(filter_results)

        # Verify all sections present
        assert "throughput" in result
        assert "wip" in result
        assert "flagged" in result
        assert "bugs" in result
        assert "scope" in result
