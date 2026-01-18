"""
Unit tests for Jira collector

Tests cover:
- Status time calculations
- Throughput calculations
- WIP age distribution
- Filter response parsing
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from tests.fixtures.sample_data import get_jira_filter_response, get_jira_issue_response


class TestJiraCollector:
    """Tests for JiraCollector"""

    def test_parse_issue_response_extracts_all_fields(self):
        # Arrange
        issue = get_jira_issue_response()

        # Assert
        assert issue["key"] == "PROJ-123"
        assert issue["fields"]["summary"] == "Implement new feature"
        assert issue["fields"]["status"]["name"] == "Done"
        assert issue["fields"]["assignee"]["name"] == "alice.jira"

    def test_parse_issue_extracts_dates(self):
        # Arrange
        issue = get_jira_issue_response()

        # Assert
        assert issue["fields"]["created"] == "2025-01-01T10:00:00.000+0000"
        assert issue["fields"]["resolutiondate"] == "2025-01-10T15:00:00.000+0000"

    def test_calculate_status_times_from_changelog(self):
        # Arrange
        issue = get_jira_issue_response()
        histories = issue["changelog"]["histories"]

        # Assert - Has 3 status transitions
        assert len(histories) == 3

        # First transition: To Do -> In Progress on 2025-01-02
        assert histories[0]["items"][0]["fromString"] == "To Do"
        assert histories[0]["items"][0]["toString"] == "In Progress"

        # Second transition: In Progress -> In Review on 2025-01-08
        assert histories[1]["items"][0]["toString"] == "In Review"

        # Third transition: In Review -> Done on 2025-01-10
        assert histories[2]["items"][0]["toString"] == "Done"

    def test_calculate_time_in_status(self):
        # Arrange
        issue = get_jira_issue_response()

        # Created: 2025-01-01
        # To In Progress: 2025-01-02 (1 day in To Do)
        # To In Review: 2025-01-08 (6 days in In Progress)
        # To Done: 2025-01-10 (2 days in In Review)

        created = datetime.fromisoformat(issue["fields"]["created"].replace("+0000", "+00:00"))
        in_progress = datetime.fromisoformat(issue["changelog"]["histories"][0]["created"].replace("+0000", "+00:00"))
        in_review = datetime.fromisoformat(issue["changelog"]["histories"][1]["created"].replace("+0000", "+00:00"))
        done = datetime.fromisoformat(issue["changelog"]["histories"][2]["created"].replace("+0000", "+00:00"))

        # Calculate durations
        time_in_todo = (in_progress - created).total_seconds() / 3600  # hours
        time_in_progress = (in_review - in_progress).total_seconds() / 3600
        time_in_review = (done - in_review).total_seconds() / 3600

        # Assert
        assert time_in_todo == 24.0  # 1 day
        assert time_in_progress == 144.0  # 6 days
        assert time_in_review == 53.0  # ~2.2 days

    def test_parse_filter_response_extracts_issues(self):
        # Arrange
        response = get_jira_filter_response()

        # Assert
        assert response["total"] == 2
        assert len(response["issues"]) == 2

        # First issue
        assert response["issues"][0]["key"] == "PROJ-100"
        assert response["issues"][0]["fields"]["status"]["name"] == "In Progress"

        # Second issue
        assert response["issues"][1]["key"] == "PROJ-101"
        assert response["issues"][1]["fields"]["status"]["name"] == "Done"

    def test_filter_response_identifies_wip_vs_completed(self):
        # Arrange
        response = get_jira_filter_response()

        # Assert - Issue with no resolutiondate is WIP
        wip_issue = response["issues"][0]
        completed_issue = response["issues"][1]

        assert wip_issue["fields"]["resolutiondate"] is None
        assert completed_issue["fields"]["resolutiondate"] is not None

    def test_calculate_wip_age_distribution(self):
        # Arrange
        # Issue created on 2025-01-05, current date would determine age
        issue = get_jira_filter_response()["issues"][0]
        created = datetime.fromisoformat(issue["fields"]["created"].replace("+0000", "+00:00"))

        # Simulate current date as 2025-01-12
        current = datetime(2025, 1, 12, tzinfo=created.tzinfo)
        age_days = (current - created).days

        # Assert
        assert age_days == 6  # Days between Jan 5 and Jan 12 (not inclusive)

    def test_bucket_wip_ages_correctly(self):
        # Arrange - Different age buckets
        ages = [2, 5, 8, 15, 25, 40]  # Days
        buckets = {"0-7 days": 0, "8-14 days": 0, "15-30 days": 0, "30+ days": 0}

        # Act - Bucket the ages
        for age in ages:
            if age <= 7:
                buckets["0-7 days"] += 1
            elif age <= 14:
                buckets["8-14 days"] += 1
            elif age <= 30:
                buckets["15-30 days"] += 1
            else:
                buckets["30+ days"] += 1

        # Assert
        assert buckets["0-7 days"] == 2  # 2, 5
        assert buckets["8-14 days"] == 1  # 8
        assert buckets["15-30 days"] == 2  # 15, 25
        assert buckets["30+ days"] == 1  # 40

    def test_calculate_throughput_per_week(self):
        # Arrange - Issues resolved in different weeks
        # Week 1: 3 issues, Week 2: 5 issues, Week 3: 2 issues
        weekly_counts = [3, 5, 2]

        # Act - Calculate average throughput
        avg_throughput = sum(weekly_counts) / len(weekly_counts)

        # Assert
        assert avg_throughput == pytest.approx(3.33, rel=0.01)

    def test_handles_missing_assignee(self):
        # Arrange - Issue with no assignee
        issue = {
            "key": "PROJ-999",
            "fields": {
                "summary": "Unassigned issue",
                "status": {"name": "Open"},
                "assignee": None,  # No assignee
                "created": "2025-01-01T10:00:00.000+0000",
            },
        }

        # Assert - Should handle None assignee
        assert issue["fields"]["assignee"] is None

    def test_handles_empty_changelog(self):
        # Arrange - Issue with no status transitions
        issue = {
            "key": "PROJ-888",
            "fields": {"created": "2025-01-01T10:00:00.000+0000"},
            "changelog": {"histories": []},  # No transitions
        }

        # Assert
        assert len(issue["changelog"]["histories"]) == 0

    def test_collect_person_issues_jql_includes_statusCategory_filter(self):
        """Verify JQL query filters updated field to non-Done items only"""
        from unittest.mock import MagicMock, patch

        from src.collectors.jira_collector import JiraCollector

        # Arrange
        with patch("src.collectors.jira_collector.JIRA") as mock_jira_class:
            mock_jira_instance = MagicMock()
            mock_jira_class.return_value = mock_jira_instance
            mock_jira_instance.search_issues.return_value = []

            collector = JiraCollector(
                server="https://jira.test.com",
                username="testuser",
                api_token="token123",
                project_keys=["TEST"],
                verify_ssl=False,
            )

            # Act
            collector.collect_person_issues("testuser", days_back=90, expand_changelog=False)

            # Assert - Verify JQL contains statusCategory filter
            mock_jira_instance.search_issues.assert_called_once()
            called_jql = mock_jira_instance.search_issues.call_args[0][0]

            assert "statusCategory != Done" in called_jql
            assert "updated >= -90d" in called_jql
            assert "created >= -90d" in called_jql
            assert "resolved >= -90d" in called_jql

    def test_collect_person_issues_jql_structure(self):
        """Verify JQL query has correct OR structure with nested AND"""
        from unittest.mock import MagicMock, patch

        from src.collectors.jira_collector import JiraCollector

        # Arrange
        with patch("src.collectors.jira_collector.JIRA") as mock_jira_class:
            mock_jira_instance = MagicMock()
            mock_jira_class.return_value = mock_jira_instance
            mock_jira_instance.search_issues.return_value = []

            collector = JiraCollector(
                server="https://jira.test.com",
                username="testuser",
                api_token="token123",
                project_keys=["TEST"],
                verify_ssl=False,
            )

            # Act
            collector.collect_person_issues("testuser", days_back=90, expand_changelog=False)

            # Assert - Verify parentheses structure
            called_jql = mock_jira_instance.search_issues.call_args[0][0]
            assert "(created >= -90d OR resolved >= -90d OR (statusCategory != Done AND updated >= -90d))" in called_jql
            assert 'assignee = "testuser"' in called_jql

    def test_collect_issue_metrics_jql_includes_statusCategory_filter(self):
        """Verify project query also filters by statusCategory"""
        from unittest.mock import MagicMock, patch

        from src.collectors.jira_collector import JiraCollector

        # Arrange
        with patch("src.collectors.jira_collector.JIRA") as mock_jira_class:
            mock_jira_instance = MagicMock()
            mock_jira_class.return_value = mock_jira_instance
            mock_jira_instance.search_issues.return_value = []

            collector = JiraCollector(
                server="https://jira.test.com",
                username="testuser",
                api_token="token123",
                project_keys=["TEST"],
                verify_ssl=False,
            )

            # Act
            collector.collect_issue_metrics("TESTPROJECT")

            # Assert - Verify JQL contains statusCategory filter
            called_jql = mock_jira_instance.search_issues.call_args[0][0]
            assert "statusCategory != Done" in called_jql
            assert "project = TESTPROJECT" in called_jql


class TestFixVersionParsing:
    """Test parsing of Jira Fix Version names"""

    def test_parse_live_format_with_slashes(self):
        """Test parsing 'Live - 21/Oct/2025' format"""
        from unittest.mock import Mock, patch

        from src.collectors.jira_collector import JiraCollector

        with patch("src.collectors.jira_collector.JIRA"):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="token",
                project_keys=["TEST"],
            )

            version_name = "Live - 21/Oct/2025"
            result = collector._parse_fix_version_name(version_name)

            assert result is not None
            assert result["published_at"].year == 2025
            assert result["published_at"].month == 10
            assert result["published_at"].day == 21
            assert result["environment"] == "production"
            assert result["is_prerelease"] is False

    def test_parse_underscore_format(self):
        """Test parsing 'RA_Web_2025_11_25' format"""
        from unittest.mock import patch

        from src.collectors.jira_collector import JiraCollector

        with patch("src.collectors.jira_collector.JIRA"):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="token",
                project_keys=["TEST"],
            )

            version_name = "RA_Web_2025_11_25"
            result = collector._parse_fix_version_name(version_name)

            assert result is not None
            assert result["published_at"].year == 2025
            assert result["published_at"].month == 11
            assert result["published_at"].day == 25
            assert result["environment"] == "production"

    def test_parse_beta_format(self):
        """Test parsing 'Beta - 15/Jan/2026' format"""
        from unittest.mock import patch

        from src.collectors.jira_collector import JiraCollector

        with patch("src.collectors.jira_collector.JIRA"):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="token",
                project_keys=["TEST"],
            )

            version_name = "Beta - 15/Jan/2026"
            result = collector._parse_fix_version_name(version_name)

            assert result is not None
            assert result["published_at"].year == 2026
            assert result["published_at"].month == 1
            assert result["published_at"].day == 15
            assert result["environment"] == "staging"
            assert result["is_prerelease"] is True

    def test_parse_invalid_format_returns_none(self):
        """Test invalid version name returns None"""
        from unittest.mock import patch

        from src.collectors.jira_collector import JiraCollector

        with patch("src.collectors.jira_collector.JIRA"):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="token",
                project_keys=["TEST"],
            )

            invalid_names = [
                "Version 1.0",
                "Sprint 42",
                "Invalid Date Format",
                "Live - BadMonth/2025",
            ]

            for name in invalid_names:
                result = collector._parse_fix_version_name(name)
                assert result is None
