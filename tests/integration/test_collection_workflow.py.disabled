"""Integration tests for end-to-end collection workflow

Tests the complete pipeline from data collection through metrics calculation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.models.metrics import MetricsCalculator


class TestCollectionWorkflow:
    """Test complete data collection pipeline"""

    def test_github_to_metrics_workflow(self):
        """Test GitHub data collection through metrics calculation"""
        # Arrange - Mock GitHub GraphQL responses
        mock_pr_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "nodes": [
                            {
                                "number": 1,
                                "title": "Test PR",
                                "author": {"login": "alice"},
                                "createdAt": "2024-01-01T10:00:00Z",
                                "mergedAt": "2024-01-02T10:00:00Z",
                                "closedAt": "2024-01-02T10:00:00Z",
                                "state": "MERGED",
                                "additions": 100,
                                "deletions": 50,
                                "reviews": {
                                    "nodes": [
                                        {
                                            "author": {"login": "bob"},
                                            "createdAt": "2024-01-01T12:00:00Z",
                                            "state": "APPROVED",
                                        }
                                    ]
                                },
                                "commits": {
                                    "nodes": [
                                        {
                                            "commit": {
                                                "oid": "abc123",
                                                "author": {
                                                    "name": "Alice",
                                                    "email": "alice@example.com",
                                                    "date": "2024-01-01T11:00:00Z",
                                                    "user": {"login": "alice"},
                                                },
                                                "additions": 100,
                                                "deletions": 50,
                                            }
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }

        with patch.object(GitHubGraphQLCollector, "_execute_graphql_query", return_value=mock_pr_response):
            # Act - Collect data
            collector = GitHubGraphQLCollector("fake_token", "test-org")
            prs, reviews, commits, releases = collector.collect_repository_metrics(
                "test-org", "test-repo", datetime.now(timezone.utc) - timedelta(days=90), datetime.now(timezone.utc)
            )

            # Create metrics calculator
            dfs = {
                "pull_requests": pd.DataFrame(prs),
                "reviews": pd.DataFrame(reviews),
                "commits": pd.DataFrame(commits),
                "deployments": pd.DataFrame(releases),
            }
            calculator = MetricsCalculator(dfs)

            # Calculate metrics
            pr_metrics = calculator.calculate_pr_metrics()
            review_metrics = calculator.calculate_review_metrics()
            commit_metrics = calculator.calculate_contributor_metrics()

        # Assert - Verify metrics calculated correctly
        assert pr_metrics["total_prs"] == 1
        assert pr_metrics["merged_prs"] == 1
        assert pr_metrics["merge_rate"] == 1.0
        assert review_metrics["total_reviews"] == 1
        assert commit_metrics["total_commits"] == 1
        assert commit_metrics["unique_contributors"] == 1

    def test_jira_to_metrics_workflow(self):
        """Test Jira data collection through metrics calculation"""
        # Arrange - Mock Jira API
        mock_jira = Mock()

        # Mock issue object
        mock_issue = Mock()
        mock_issue.key = "TEST-1"
        mock_issue.fields = Mock()
        mock_issue.fields.created = "2024-01-01T10:00:00.000+0000"
        mock_issue.fields.resolutiondate = "2024-01-05T10:00:00.000+0000"
        mock_issue.fields.status = Mock(name="Done")
        mock_issue.fields.assignee = Mock(displayName="Alice")
        mock_issue.fields.reporter = Mock(displayName="Bob")
        mock_issue.changelog = Mock()
        mock_issue.changelog.histories = []

        mock_jira.search_issues.return_value = [mock_issue]
        mock_jira.issue.return_value = mock_issue

        with patch("src.collectors.jira_collector.JIRA", return_value=mock_jira):
            # Act - Collect Jira data
            collector = JiraCollector(
                server="https://jira.example.com",
                username="test",
                api_token="test_token",
                project_keys=["TEST"],
                days_back=90,
            )

            issues = collector.collect_issue_metrics("TEST")

        # Assert - Verify issue data collected
        assert len(issues) > 0
        assert issues[0]["key"] == "TEST-1"
        assert issues[0]["status"] == "Done"

    def test_full_collection_pipeline(self):
        """Test complete pipeline: GitHub + Jira → Metrics → Cache"""
        # Arrange - Mock both GitHub and Jira
        mock_pr_data = [
            {
                "pr_number": 1,
                "author": "alice",
                "merged": True,
                "state": "merged",
                "additions": 100,
                "deletions": 50,
                "cycle_time_hours": 24.0,
                "time_to_first_review_hours": 2.0,
                "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "merged_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
            }
        ]

        mock_review_data = [
            {
                "reviewer": "bob",
                "pr_number": 1,
                "state": "APPROVED",
                "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            }
        ]

        mock_commit_data = [
            {"sha": "abc123", "author": "alice", "date": "2024-01-01", "additions": 100, "deletions": 50}
        ]

        mock_jira_data = [
            {
                "key": "TEST-1",
                "status": "Done",
                "created": "2024-01-01",
                "resolved": "2024-01-05",
                "assignee": "Alice",
                "reporter": "Bob",
            }
        ]

        # Act - Create calculator with mock data
        dfs = {
            "pull_requests": pd.DataFrame(mock_pr_data),
            "reviews": pd.DataFrame(mock_review_data),
            "commits": pd.DataFrame(mock_commit_data),
            "deployments": pd.DataFrame(),
            "jira_issues": pd.DataFrame(mock_jira_data),
        }
        calculator = MetricsCalculator(dfs)

        # Calculate all metrics
        pr_metrics = calculator.calculate_pr_metrics()
        review_metrics = calculator.calculate_review_metrics()
        commit_metrics = calculator.calculate_contributor_metrics()

        # Assert - Verify complete workflow
        assert pr_metrics["total_prs"] == 1
        assert pr_metrics["merged_prs"] == 1
        assert review_metrics["total_reviews"] == 1
        assert commit_metrics["total_commits"] == 1

        # Verify data integrity
        assert pr_metrics["merge_rate"] == 1.0
        assert pr_metrics["avg_cycle_time_hours"] == 24.0
        assert commit_metrics["unique_contributors"] == 1
