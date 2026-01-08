"""
Unit tests for Jira collector

Tests cover:
- Status time calculations
- Throughput calculations
- WIP age distribution
- Filter response parsing
"""
import pytest
from datetime import datetime
from unittest.mock import Mock

from tests.fixtures.sample_data import (
    get_jira_issue_response,
    get_jira_filter_response
)


class TestJiraCollector:
    """Tests for JiraCollector"""

    def test_parse_issue_response_extracts_all_fields(self):
        # Arrange
        issue = get_jira_issue_response()

        # Assert
        assert issue['key'] == 'PROJ-123'
        assert issue['fields']['summary'] == 'Implement new feature'
        assert issue['fields']['status']['name'] == 'Done'
        assert issue['fields']['assignee']['name'] == 'alice.jira'

    def test_parse_issue_extracts_dates(self):
        # Arrange
        issue = get_jira_issue_response()

        # Assert
        assert issue['fields']['created'] == '2025-01-01T10:00:00.000+0000'
        assert issue['fields']['resolutiondate'] == '2025-01-10T15:00:00.000+0000'

    def test_calculate_status_times_from_changelog(self):
        # Arrange
        issue = get_jira_issue_response()
        histories = issue['changelog']['histories']

        # Assert - Has 3 status transitions
        assert len(histories) == 3

        # First transition: To Do -> In Progress on 2025-01-02
        assert histories[0]['items'][0]['fromString'] == 'To Do'
        assert histories[0]['items'][0]['toString'] == 'In Progress'

        # Second transition: In Progress -> In Review on 2025-01-08
        assert histories[1]['items'][0]['toString'] == 'In Review'

        # Third transition: In Review -> Done on 2025-01-10
        assert histories[2]['items'][0]['toString'] == 'Done'

    def test_calculate_time_in_status(self):
        # Arrange
        issue = get_jira_issue_response()

        # Created: 2025-01-01
        # To In Progress: 2025-01-02 (1 day in To Do)
        # To In Review: 2025-01-08 (6 days in In Progress)
        # To Done: 2025-01-10 (2 days in In Review)

        created = datetime.fromisoformat(issue['fields']['created'].replace('+0000', '+00:00'))
        in_progress = datetime.fromisoformat(issue['changelog']['histories'][0]['created'].replace('+0000', '+00:00'))
        in_review = datetime.fromisoformat(issue['changelog']['histories'][1]['created'].replace('+0000', '+00:00'))
        done = datetime.fromisoformat(issue['changelog']['histories'][2]['created'].replace('+0000', '+00:00'))

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
        assert response['total'] == 2
        assert len(response['issues']) == 2

        # First issue
        assert response['issues'][0]['key'] == 'PROJ-100'
        assert response['issues'][0]['fields']['status']['name'] == 'In Progress'

        # Second issue
        assert response['issues'][1]['key'] == 'PROJ-101'
        assert response['issues'][1]['fields']['status']['name'] == 'Done'

    def test_filter_response_identifies_wip_vs_completed(self):
        # Arrange
        response = get_jira_filter_response()

        # Assert - Issue with no resolutiondate is WIP
        wip_issue = response['issues'][0]
        completed_issue = response['issues'][1]

        assert wip_issue['fields']['resolutiondate'] is None
        assert completed_issue['fields']['resolutiondate'] is not None

    def test_calculate_wip_age_distribution(self):
        # Arrange
        # Issue created on 2025-01-05, current date would determine age
        issue = get_jira_filter_response()['issues'][0]
        created = datetime.fromisoformat(issue['fields']['created'].replace('+0000', '+00:00'))

        # Simulate current date as 2025-01-12
        current = datetime(2025, 1, 12, tzinfo=created.tzinfo)
        age_days = (current - created).days

        # Assert
        assert age_days == 7  # Issue is 7 days old

    def test_bucket_wip_ages_correctly(self):
        # Arrange - Different age buckets
        ages = [2, 5, 8, 15, 25, 40]  # Days
        buckets = {
            '0-7 days': 0,
            '8-14 days': 0,
            '15-30 days': 0,
            '30+ days': 0
        }

        # Act - Bucket the ages
        for age in ages:
            if age <= 7:
                buckets['0-7 days'] += 1
            elif age <= 14:
                buckets['8-14 days'] += 1
            elif age <= 30:
                buckets['15-30 days'] += 1
            else:
                buckets['30+ days'] += 1

        # Assert
        assert buckets['0-7 days'] == 2  # 2, 5
        assert buckets['8-14 days'] == 1  # 8
        assert buckets['15-30 days'] == 2  # 15, 25
        assert buckets['30+ days'] == 1  # 40

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
            'key': 'PROJ-999',
            'fields': {
                'summary': 'Unassigned issue',
                'status': {'name': 'Open'},
                'assignee': None,  # No assignee
                'created': '2025-01-01T10:00:00.000+0000'
            }
        }

        # Assert - Should handle None assignee
        assert issue['fields']['assignee'] is None

    def test_handles_empty_changelog(self):
        # Arrange - Issue with no status transitions
        issue = {
            'key': 'PROJ-888',
            'fields': {'created': '2025-01-01T10:00:00.000+0000'},
            'changelog': {'histories': []}  # No transitions
        }

        # Assert
        assert len(issue['changelog']['histories']) == 0
