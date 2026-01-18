"""Tests for GitHub GraphQL collector helper methods and batched collection"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.collectors.github_graphql_collector import GitHubGraphQLCollector


class TestHelperMethods:
    """Test the new helper methods added for batched collection"""

    @pytest.fixture
    def collector(self):
        """Create collector instance for testing"""
        return GitHubGraphQLCollector(token="test_token", organization="test-org", teams=["test-team"], days_back=7)

    # Date Range Tests
    def test_is_pr_in_date_range_within_range(self, collector):
        """Test PR within date range returns True"""
        # Arrange
        pr = {"createdAt": datetime.now(timezone.utc).isoformat()}

        # Act
        result = collector._is_pr_in_date_range(pr)

        # Assert
        assert result is True

    def test_is_pr_in_date_range_before_range(self, collector):
        """Test PR before date range returns False"""
        # Arrange
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        pr = {"createdAt": old_date}

        # Act
        result = collector._is_pr_in_date_range(pr)

        # Assert
        assert result is False

    def test_is_pr_in_date_range_missing_created_at(self, collector):
        """Test PR without createdAt returns False"""
        # Arrange
        pr = {}

        # Act
        result = collector._is_pr_in_date_range(pr)

        # Assert
        assert result is False

    def test_is_pr_in_date_range_boundary(self, collector):
        """Test PR exactly at boundary date"""
        # Arrange
        pr = {"createdAt": collector.since_date.isoformat()}

        # Act
        result = collector._is_pr_in_date_range(pr)

        # Assert
        assert result is True

    def test_is_release_in_date_range_uses_published_at(self, collector):
        """Test release uses publishedAt when available"""
        # Arrange
        recent_date = datetime.now(timezone.utc).isoformat()
        release = {"publishedAt": recent_date, "createdAt": "2020-01-01T00:00:00Z"}  # Old date, should be ignored

        # Act
        result = collector._is_release_in_date_range(release)

        # Assert
        assert result is True

    def test_is_release_in_date_range_falls_back_to_created_at(self, collector):
        """Test release falls back to createdAt when publishedAt missing"""
        # Arrange
        recent_date = datetime.now(timezone.utc).isoformat()
        release = {"publishedAt": None, "createdAt": recent_date}

        # Act
        result = collector._is_release_in_date_range(release)

        # Assert
        assert result is True

    def test_is_release_in_date_range_missing_both_dates(self, collector):
        """Test release without dates returns False"""
        # Arrange
        release = {}

        # Act
        result = collector._is_release_in_date_range(release)

        # Assert
        assert result is False

    def test_is_release_in_date_range_before_range(self, collector):
        """Test release before date range returns False"""
        # Arrange
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        release = {"publishedAt": old_date}

        # Act
        result = collector._is_release_in_date_range(release)

        # Assert
        assert result is False

    # Data Extraction Tests
    def test_extract_pr_data_complete(self, collector):
        """Test extracting complete PR data"""
        # Arrange
        pr = {
            "number": 123,
            "title": "Test PR",
            "author": {"login": "testuser"},
            "created_at": "2026-01-10T10:00:00Z",
            "merged_at": "2026-01-11T10:00:00Z",
            "closed_at": None,
            "state": "MERGED",
            "merged": True,
            "additions": 100,
            "deletions": 50,
            "changed_files": 5,
        }

        # Act
        result = collector._extract_pr_data(pr)

        # Assert
        assert result["number"] == 123
        assert result["title"] == "Test PR"
        assert result["author"] == "testuser"
        assert result["merged"] is True
        assert result["additions"] == 100

    def test_extract_pr_data_missing_author(self, collector):
        """Test extracting PR data with missing author"""
        # Arrange
        pr = {"number": 123, "title": "Test PR", "author": None}

        # Act
        result = collector._extract_pr_data(pr)

        # Assert
        assert result["number"] == 123
        assert result["author"] is None

    def test_extract_pr_data_missing_optional_fields(self, collector):
        """Test extracting PR data with missing optional fields"""
        # Arrange
        pr = {"number": 123}

        # Act
        result = collector._extract_pr_data(pr)

        # Assert
        assert result["number"] == 123
        assert result["additions"] == 0  # Default value
        assert result["deletions"] == 0
        assert result["changed_files"] == 0

    def test_extract_review_data_multiple_reviews(self, collector):
        """Test extracting multiple reviews"""
        # Arrange
        pr = {
            "number": 123,
            "author": {"login": "pr_author"},
            "reviews": {
                "nodes": [
                    {"author": {"login": "reviewer1"}, "submittedAt": "2026-01-10T15:00:00Z", "state": "APPROVED"},
                    {
                        "author": {"login": "reviewer2"},
                        "submittedAt": "2026-01-10T16:00:00Z",
                        "state": "CHANGES_REQUESTED",
                    },
                ]
            },
        }

        # Act
        result = collector._extract_review_data(pr)

        # Assert
        assert len(result) == 2
        assert result[0]["reviewer"] == "reviewer1"  # BUG FIX: Check 'reviewer' field
        assert result[0]["state"] == "APPROVED"
        assert result[1]["reviewer"] == "reviewer2"

    def test_extract_review_data_no_reviews(self, collector):
        """Test extracting data with no reviews"""
        # Arrange
        pr = {"number": 123, "reviews": {"nodes": []}}

        # Act
        result = collector._extract_review_data(pr)

        # Assert
        assert result == []

    def test_extract_review_data_missing_author(self, collector):
        """Test extracting reviews with missing author"""
        # Arrange
        pr = {
            "number": 123,
            "reviews": {"nodes": [{"author": None, "submittedAt": "2026-01-10T15:00:00Z", "state": "APPROVED"}]},
        }

        # Act
        result = collector._extract_review_data(pr)

        # Assert
        assert result == []  # Should skip reviews without author

    def test_extract_review_data_includes_reviewer_field(self, collector):
        """Test that extracted review data includes 'reviewer' field (bug fix test)"""
        # Arrange
        pr = {
            "number": 123,
            "author": {"login": "pr_author"},
            "reviews": {
                "nodes": [
                    {"author": {"login": "test_reviewer"}, "submittedAt": "2026-01-10T15:00:00Z", "state": "APPROVED"}
                ]
            },
        }

        # Act
        result = collector._extract_review_data(pr)

        # Assert
        assert "reviewer" in result[0]  # Critical: must have 'reviewer' not 'author'
        assert result[0]["reviewer"] == "test_reviewer"
        assert "pr_author" in result[0]
        assert result[0]["pr_author"] == "pr_author"

    def test_extract_commit_data_multiple_commits(self, collector):
        """Test extracting multiple commits"""
        # Arrange
        pr = {
            "number": 123,
            "commits": {
                "nodes": [
                    {
                        "commit": {
                            "oid": "abc123",
                            "author": {"user": {"login": "testuser"}, "name": "Test User", "email": "test@example.com"},
                            "committedDate": "2026-01-10T09:00:00Z",
                            "additions": 50,
                            "deletions": 25,
                        }
                    },
                    {
                        "commit": {
                            "oid": "def456",
                            "author": {
                                "user": {"login": "otheruser"},
                                "name": "Other User",
                                "email": "other@example.com",
                            },
                            "committedDate": "2026-01-10T10:00:00Z",
                            "additions": 30,
                            "deletions": 15,
                        }
                    },
                ]
            },
        }

        # Act
        result = collector._extract_commit_data(pr)

        # Assert
        assert len(result) == 2
        assert result[0]["sha"] == "abc123"
        assert result[0]["author"] == "testuser"
        assert result[1]["sha"] == "def456"

    def test_extract_commit_data_no_commits(self, collector):
        """Test extracting data with no commits"""
        # Arrange
        pr = {"number": 123, "commits": {"nodes": []}}

        # Act
        result = collector._extract_commit_data(pr)

        # Assert
        assert result == []

    def test_extract_commit_data_missing_user_uses_email(self, collector):
        """Test commit author fallback to email when user missing"""
        # Arrange
        pr = {
            "number": 123,
            "commits": {
                "nodes": [
                    {
                        "commit": {
                            "oid": "abc123",
                            "author": {"user": None, "email": "test@example.com"},
                            "committedDate": "2026-01-10T09:00:00Z",
                        }
                    }
                ]
            },
        }

        # Act
        result = collector._extract_commit_data(pr)

        # Assert
        assert result[0]["author"] == "test@example.com"

    def test_extract_commit_data_missing_fields(self, collector):
        """Test extracting commits with missing optional fields"""
        # Arrange
        pr = {
            "number": 123,
            "commits": {
                "nodes": [
                    {
                        "commit": {
                            "oid": "abc123",
                            "author": {"email": "test@example.com"},
                            "committedDate": "2026-01-10T09:00:00Z",
                        }
                    }
                ]
            },
        }

        # Act
        result = collector._extract_commit_data(pr)

        # Assert
        assert result[0]["additions"] == 0
        assert result[0]["deletions"] == 0

    def test_classify_release_environment_production_patterns(self, collector):
        """Test production release pattern recognition"""
        # Act & Assert - GitHub uses semantic version tags
        assert collector._classify_release_environment("v1.0.0", False) == "production"
        assert collector._classify_release_environment("v2.3.1", False) == "production"
        assert collector._classify_release_environment("1.0.0", False) == "production"
        assert collector._classify_release_environment("v10.5.23", False) == "production"

    def test_classify_release_environment_staging_patterns(self, collector):
        """Test staging release pattern recognition"""
        # Act & Assert - GitHub uses semantic version tags with suffixes
        assert collector._classify_release_environment("v1.0.0-beta", False) == "staging"
        assert collector._classify_release_environment("v2.0.0-preview", False) == "staging"
        assert collector._classify_release_environment("v1.0.0-rc1", False) == "staging"
        assert collector._classify_release_environment("v1.5.0-alpha", False) == "staging"
        assert collector._classify_release_environment("v3.0.0-dev", False) == "staging"

    def test_classify_release_environment_prerelease_flag(self, collector):
        """Test that prerelease flag overrides to staging"""
        # Act - Even production tag format becomes staging if prerelease=True
        result = collector._classify_release_environment("v1.0.0", True)

        # Assert
        assert result == "staging"  # Prerelease flag forces staging
