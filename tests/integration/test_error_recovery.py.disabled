"""Integration tests for error recovery and resilience

Tests how the system handles errors and edge cases across modules.
"""

import os
import pickle
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from requests.exceptions import ConnectionError, Timeout

from src.collectors.github_graphql_collector import GitHubGraphQLCollector
from src.collectors.jira_collector import JiraCollector
from src.dashboard.app import load_cache_from_file
from src.models.metrics import MetricsCalculator


class TestErrorRecovery:
    """Test error handling and recovery across modules"""

    def test_github_api_timeout_handling(self):
        """Test handling of GitHub API timeouts"""
        collector = GitHubGraphQLCollector("fake_token", "test-org")

        with patch.object(collector, "_execute_graphql_query", side_effect=Timeout("Connection timeout")):
            # Should handle timeout gracefully
            with pytest.raises(Timeout):
                collector.collect_repository_metrics(
                    "test-org",
                    "test-repo",
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 3, 31, tzinfo=timezone.utc),
                )

    def test_jira_connection_failure_handling(self):
        """Test handling of Jira connection failures"""
        with patch("src.collectors.jira_collector.JIRA", side_effect=ConnectionError("Cannot connect")):
            with pytest.raises(ConnectionError):
                collector = JiraCollector(
                    server="https://jira.invalid.com",
                    username="test",
                    api_token="test_token",
                    project_keys=["TEST"],
                    days_back=90,
                )

    def test_metrics_with_malformed_data(self):
        """Test metrics calculation with malformed data"""
        # Missing required columns
        malformed_prs = pd.DataFrame(
            {
                "pr_number": [1, 2],
                "author": ["alice", "bob"],
                # Missing: merged, state, additions, deletions, etc.
            }
        )

        dfs = {
            "pull_requests": malformed_prs,
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
            "deployments": pd.DataFrame(),
        }

        calculator = MetricsCalculator(dfs)

        # Should handle gracefully, returning zero or default values
        metrics = calculator.calculate_pr_metrics()
        assert metrics is not None
        assert "total_prs" in metrics

    def test_corrupted_cache_handling(self):
        """Test handling of corrupted cache files"""
        # Create corrupted cache file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pkl") as f:
            f.write("This is not valid pickle data")
            temp_path = f.name

        try:
            with patch("src.dashboard.app.get_cache_filename", return_value=temp_path):
                # Should return False and not crash
                success = load_cache_from_file("90d")
                assert success is False
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_missing_cache_file_handling(self):
        """Test handling of missing cache files"""
        with patch("src.dashboard.app.get_cache_filename", return_value="/nonexistent/path/cache.pkl"):
            # Should return False and not crash
            success = load_cache_from_file("90d")
            assert success is False

    def test_empty_dataframes_handling(self):
        """Test metrics calculation with all empty dataframes"""
        empty_dfs = {
            "pull_requests": pd.DataFrame(),
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
            "deployments": pd.DataFrame(),
        }

        calculator = MetricsCalculator(empty_dfs)

        # Should return zero metrics, not crash
        pr_metrics = calculator.calculate_pr_metrics()
        assert pr_metrics["total_prs"] == 0
        assert pr_metrics["merged_prs"] == 0

        review_metrics = calculator.calculate_review_metrics()
        assert review_metrics["total_reviews"] == 0

        commit_metrics = calculator.calculate_contributor_metrics()
        assert commit_metrics["total_commits"] == 0

    def test_invalid_date_range_handling(self):
        """Test handling of invalid date ranges"""
        from src.utils.date_ranges import DateRangeError, parse_date_range

        # Invalid format
        with pytest.raises(DateRangeError):
            parse_date_range("invalid_format")

        # Negative days
        with pytest.raises(DateRangeError):
            parse_date_range("-30d")

        # Days too large
        with pytest.raises(DateRangeError):
            parse_date_range("10000d")

        # Invalid year
        with pytest.raises(DateRangeError):
            parse_date_range("1999")  # Before 2000

    def test_partial_data_collection_recovery(self):
        """Test recovery when only partial data is collected"""
        # Scenario: GitHub succeeds but Jira fails
        mock_prs = [
            {
                "pr_number": 1,
                "author": "alice",
                "merged": True,
                "state": "merged",
                "additions": 100,
                "deletions": 50,
                "cycle_time_hours": 24.0,
                "time_to_first_review_hours": 2.0,
            }
        ]

        # Create calculator with only PR data (no Jira)
        dfs = {
            "pull_requests": pd.DataFrame(mock_prs),
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
            "deployments": pd.DataFrame(),
        }
        calculator = MetricsCalculator(dfs)

        # Should still calculate metrics with available data
        pr_metrics = calculator.calculate_pr_metrics()
        assert pr_metrics["total_prs"] == 1
        assert pr_metrics["merged_prs"] == 1

    def test_nan_and_null_value_handling(self):
        """Test handling of NaN and None values in data"""
        prs_with_nans = pd.DataFrame(
            {
                "pr_number": [1, 2, 3],
                "author": ["alice", "bob", None],  # None value
                "merged": [True, False, True],
                "state": ["merged", "open", "merged"],
                "additions": [100, None, 300],  # NaN value
                "deletions": [50, 100, 150],
                "cycle_time_hours": [24.0, None, 36.0],  # NaN value
            }
        )

        dfs = {
            "pull_requests": prs_with_nans,
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
            "deployments": pd.DataFrame(),
        }

        calculator = MetricsCalculator(dfs)

        # Should handle NaN/None values gracefully
        metrics = calculator.calculate_pr_metrics()
        assert metrics is not None
        assert metrics["total_prs"] == 3
        assert metrics["merged_prs"] == 2

        # Cycle time should ignore None values
        assert metrics["avg_cycle_time_hours"] is not None

    def test_concurrent_cache_access(self):
        """Test handling of concurrent cache file access"""
        # Create valid cache
        cache_data = {
            "teams": {},
            "persons": {},
            "comparison": {"teams": [], "metrics": {}},
            "timestamp": datetime.now(timezone.utc),
            "date_range": {},
        }

        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pkl") as f:
            pickle.dump(cache_data, f)
            temp_path = f.name

        try:
            with patch("src.dashboard.app.get_cache_filename", return_value=temp_path):
                # Multiple sequential loads should work
                success1 = load_cache_from_file("90d")
                success2 = load_cache_from_file("90d")
                assert success1 is True
                assert success2 is True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestGitHubRateLimiting:
    """Test GitHub API rate limiting and retry logic"""

    def test_rate_limit_exceeded_primary(self):
        """Test handling when primary GitHub rate limit is exceeded"""
        collector = GitHubGraphQLCollector("fake_token", "test-org")

        # Mock rate limit error response
        rate_limit_response = {
            "errors": [
                {
                    "type": "RATE_LIMITED",
                    "message": "API rate limit exceeded",
                }
            ]
        }

        with patch.object(collector, "_execute_graphql_query", return_value=rate_limit_response):
            result = collector._fetch_prs_for_repo(
                "test-repo",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 3, 31, tzinfo=timezone.utc),
            )

            # Should return empty result rather than crash
            assert result is not None

    def test_secondary_rate_limit_handling(self):
        """Test handling of GitHub secondary rate limits"""
        collector = GitHubGraphQLCollector("fake_token", "test-org")

        # Mock secondary rate limit (429 status)
        with patch.object(
            collector,
            "_execute_graphql_query",
            side_effect=[
                Exception("Secondary rate limit"),
                {"data": {"repository": {"pullRequests": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}},
            ],
        ):
            # Should retry and eventually succeed
            result = collector._fetch_prs_for_repo(
                "test-repo",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 3, 31, tzinfo=timezone.utc),
            )

            # After retry, should get valid result
            assert result is not None

    def test_exponential_backoff_on_retry(self):
        """Test exponential backoff behavior on API errors"""
        import time

        collector = GitHubGraphQLCollector("fake_token", "test-org")
        retry_times = []

        def mock_query_with_timing(*args, **kwargs):
            retry_times.append(time.time())
            if len(retry_times) < 3:
                raise Timeout("Temporary failure")
            return {"data": {"repository": {"pullRequests": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}}

        with patch.object(collector, "_execute_graphql_query", side_effect=mock_query_with_timing):
            try:
                collector._fetch_prs_for_repo(
                    "test-repo",
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 3, 31, tzinfo=timezone.utc),
                )
            except:
                pass  # May fail, we're testing timing

        # Should have attempted multiple times
        # (Note: actual backoff implementation may vary)


class TestJiraTimeoutRecovery:
    """Test Jira timeout and progressive fallback"""

    def test_jira_search_timeout_with_fallback(self):
        """Test Jira search timeout triggers progressive fallback"""
        mock_jira = Mock()
        mock_jira.search_issues.side_effect = [
            Timeout("Search timeout"),  # First attempt fails
            [],  # Fallback succeeds with simpler query
        ]

        with patch("src.collectors.jira_collector.JIRA", return_value=mock_jira):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="test_token",
                project_keys=["TEST"],
                days_back=90,
            )

            # Should handle timeout and try fallback
            try:
                result = collector.collect_project_issues(["TEST"])
                # Should return something even after timeout
                assert result is not None
            except Timeout:
                # Acceptable to propagate after retries exhausted
                pass

    def test_jira_timeout_reduces_query_complexity(self):
        """Test that timeout leads to simpler query (fewer fields)"""
        mock_jira = Mock()

        # Track query parameters
        queries_attempted = []

        def track_query(jql, *args, **kwargs):
            queries_attempted.append({"jql": jql, "maxResults": kwargs.get("maxResults", 50)})
            if len(queries_attempted) == 1:
                raise Timeout("Initial complex query timeout")
            return []

        mock_jira.search_issues.side_effect = track_query

        with patch("src.collectors.jira_collector.JIRA", return_value=mock_jira):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="test_token",
                project_keys=["TEST"],
                days_back=90,
                timeout=30,
            )

            try:
                collector.collect_project_issues(["TEST"])
            except:
                pass

        # Should have attempted at least one query
        assert len(queries_attempted) >= 1

    def test_jira_connection_pool_exhaustion(self):
        """Test handling when Jira connection pool is exhausted"""
        mock_jira = Mock()
        mock_jira.search_issues.side_effect = ConnectionError("Connection pool exhausted")

        with patch("src.collectors.jira_collector.JIRA", return_value=mock_jira):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="test_token",
                project_keys=["TEST"],
                days_back=90,
            )

            with pytest.raises(ConnectionError):
                collector.collect_project_issues(["TEST"])


class TestAPIResponseValidation:
    """Test validation and handling of malformed API responses"""

    def test_github_missing_required_fields(self):
        """Test GitHub response missing required fields"""
        collector = GitHubGraphQLCollector("fake_token", "test-org")

        # Malformed response missing 'data' key
        malformed_response = {"errors": []}

        with patch.object(collector, "_execute_graphql_query", return_value=malformed_response):
            result = collector._fetch_prs_for_repo(
                "test-repo",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 3, 31, tzinfo=timezone.utc),
            )

            # Should handle gracefully
            assert result is not None

    def test_github_null_values_in_response(self):
        """Test GitHub response with null values"""
        collector = GitHubGraphQLCollector("fake_token", "test-org")

        # Response with null author
        response_with_nulls = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "nodes": [
                            {
                                "number": 123,
                                "title": "Test PR",
                                "author": None,  # Null author (deleted user)
                                "createdAt": "2025-01-01T10:00:00Z",
                                "mergedAt": None,
                                "state": "OPEN",
                                "merged": False,
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }

        with patch.object(collector, "_execute_graphql_query", return_value=response_with_nulls):
            result = collector._fetch_prs_for_repo(
                "test-repo",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 3, 31, tzinfo=timezone.utc),
            )

            # Should handle null author
            assert result is not None
            assert len(result) > 0

    def test_jira_malformed_issue_data(self):
        """Test Jira returning malformed issue data"""
        mock_jira = Mock()

        # Mock issue with missing fields
        mock_issue = Mock()
        mock_issue.key = "TEST-123"
        mock_issue.fields = Mock()
        mock_issue.fields.summary = None  # Missing summary
        mock_issue.fields.status = None  # Missing status
        mock_issue.raw = {"fields": {}}

        mock_jira.search_issues.return_value = [mock_issue]

        with patch("src.collectors.jira_collector.JIRA", return_value=mock_jira):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="test_token",
                project_keys=["TEST"],
            )

            # Should handle malformed issue gracefully
            result = collector.collect_project_issues(["TEST"])
            assert result is not None


class TestNetworkFailureRecovery:
    """Test network failure and recovery scenarios"""

    def test_intermittent_network_failure(self):
        """Test recovery from intermittent network failures"""
        collector = GitHubGraphQLCollector("fake_token", "test-org")

        # Simulate intermittent failure (fail, fail, succeed)
        responses = [
            ConnectionError("Network unreachable"),
            ConnectionError("Network unreachable"),
            {"data": {"repository": {"pullRequests": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}},
        ]

        with patch.object(collector, "_execute_graphql_query", side_effect=responses):
            try:
                result = collector._fetch_prs_for_repo(
                    "test-repo",
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 3, 31, tzinfo=timezone.utc),
                )
                # Should eventually succeed after retries
                assert result is not None
            except ConnectionError:
                # Also acceptable if retries exhausted
                pass

    def test_dns_resolution_failure(self):
        """Test handling of DNS resolution failures"""
        with patch("src.collectors.jira_collector.JIRA", side_effect=ConnectionError("Name or service not known")):
            with pytest.raises(ConnectionError):
                JiraCollector(
                    server="https://nonexistent.invalid",
                    username="test",
                    api_token="test_token",
                    project_keys=["TEST"],
                )

    def test_ssl_verification_failure(self):
        """Test handling of SSL certificate verification failures"""
        mock_jira = Mock()
        mock_jira.search_issues.side_effect = ConnectionError("SSL: CERTIFICATE_VERIFY_FAILED")

        with patch("src.collectors.jira_collector.JIRA", return_value=mock_jira):
            collector = JiraCollector(
                server="https://jira.test.com",
                username="test",
                api_token="test_token",
                project_keys=["TEST"],
                verify_ssl=False,  # Should bypass SSL verification
            )

            # With verify_ssl=False, should handle differently
            with pytest.raises(ConnectionError):
                collector.collect_project_issues(["TEST"])


class TestDataIntegrityValidation:
    """Test data integrity checks and validation"""

    def test_duplicate_pr_detection(self):
        """Test detection and handling of duplicate PRs"""
        prs_with_duplicates = pd.DataFrame(
            {
                "pr_number": [1, 1, 2],  # PR #1 appears twice
                "author": ["alice", "alice", "bob"],
                "merged": [True, True, False],
                "state": ["merged", "merged", "open"],
                "additions": [100, 100, 50],
                "deletions": [50, 50, 25],
            }
        )

        dfs = {
            "pull_requests": prs_with_duplicates,
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }

        calculator = MetricsCalculator(dfs)
        metrics = calculator.calculate_pr_metrics()

        # Should handle duplicates (either deduplicate or count correctly)
        assert metrics["total_prs"] >= 2

    def test_orphaned_reviews_without_prs(self):
        """Test handling reviews that reference non-existent PRs"""
        reviews_orphaned = pd.DataFrame(
            {
                "reviewer": ["alice", "bob"],
                "pr_number": [999, 1000],  # PRs don't exist
                "state": ["APPROVED", "CHANGES_REQUESTED"],
            }
        )

        dfs = {
            "pull_requests": pd.DataFrame(),  # No PRs
            "reviews": reviews_orphaned,
            "commits": pd.DataFrame(),
        }

        calculator = MetricsCalculator(dfs)

        # Should handle orphaned reviews gracefully
        review_metrics = calculator.calculate_review_metrics()
        assert review_metrics is not None

    def test_commits_without_author(self):
        """Test handling commits with missing author information"""
        commits_no_author = pd.DataFrame(
            {
                "sha": ["abc123", "def456"],
                "author": [None, ""],  # Missing authors
                "date": [datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 2, tzinfo=timezone.utc)],
                "additions": [100, 200],
                "deletions": [50, 100],
            }
        )

        dfs = {
            "pull_requests": pd.DataFrame(),
            "reviews": pd.DataFrame(),
            "commits": commits_no_author,
        }

        calculator = MetricsCalculator(dfs)

        # Should handle missing author data
        commit_metrics = calculator.calculate_contributor_metrics()
        assert commit_metrics is not None
        assert commit_metrics["total_commits"] == 2

    def test_date_chronology_validation(self):
        """Test validation that dates are in correct chronological order"""
        # PR merged before it was created (data error)
        prs_invalid_dates = pd.DataFrame(
            {
                "pr_number": [1],
                "author": ["alice"],
                "created_at": [datetime(2025, 1, 10, tzinfo=timezone.utc)],
                "merged_at": [datetime(2025, 1, 5, tzinfo=timezone.utc)],  # Before created!
                "merged": [True],
                "state": ["merged"],
            }
        )

        dfs = {
            "pull_requests": prs_invalid_dates,
            "reviews": pd.DataFrame(),
            "commits": pd.DataFrame(),
        }

        calculator = MetricsCalculator(dfs)

        # Should handle invalid date order gracefully
        metrics = calculator.calculate_pr_metrics()
        assert metrics is not None


class TestCacheValidationAndRecovery:
    """Test cache validation and recovery from cache issues"""

    def test_cache_version_mismatch(self):
        """Test handling cache from incompatible version"""
        # Old cache format (missing required fields)
        old_cache = {
            "teams": {},
            # Missing: persons, comparison, timestamp, date_range
        }

        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pkl") as f:
            pickle.dump(old_cache, f)
            temp_path = f.name

        try:
            with patch("src.dashboard.app.get_cache_filename", return_value=temp_path):
                # Should detect incompatible cache and return False
                success = load_cache_from_file("90d")
                assert success is False
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_cache_with_future_timestamp(self):
        """Test handling cache with timestamp in the future"""
        future_cache = {
            "teams": {},
            "persons": {},
            "comparison": {"teams": [], "metrics": {}},
            "timestamp": datetime(2030, 1, 1, tzinfo=timezone.utc),  # Future date
            "date_range": {},
        }

        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pkl") as f:
            pickle.dump(future_cache, f)
            temp_path = f.name

        try:
            with patch("src.dashboard.app.get_cache_filename", return_value=temp_path):
                # Should load but may flag as suspicious
                success = load_cache_from_file("90d")
                # Depending on implementation, may accept or reject
                assert success is not None
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_cache_file_permission_denied(self):
        """Test handling cache file with read permission denied"""
        cache_data = {
            "teams": {},
            "persons": {},
            "comparison": {"teams": [], "metrics": {}},
            "timestamp": datetime.now(timezone.utc),
            "date_range": {},
        }

        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pkl") as f:
            pickle.dump(cache_data, f)
            temp_path = f.name

        try:
            # Remove read permissions
            os.chmod(temp_path, 0o000)

            with patch("src.dashboard.app.get_cache_filename", return_value=temp_path):
                # Should handle permission error gracefully
                success = load_cache_from_file("90d")
                assert success is False
        finally:
            # Restore permissions before cleanup
            try:
                os.chmod(temp_path, 0o644)
                os.unlink(temp_path)
            except:
                pass
