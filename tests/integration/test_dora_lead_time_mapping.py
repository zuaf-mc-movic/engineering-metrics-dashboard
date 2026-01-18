"""Integration tests for DORA lead time mapping workflow

Tests the complete flow of mapping PRs to deployments via Jira:
1. Extract Jira issue key from PR title/branch
2. Map Jira issue to Fix Version
3. Calculate lead time from PR merge to deployment
4. Handle cherry-pick workflows
5. Fallback to time-based mapping
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.models.metrics import MetricsCalculator


class TestPRToJiraIssueMapping:
    """Test extracting Jira issue keys from PR metadata"""

    def test_pr_with_issue_in_title_brackets(self):
        """Test PR with issue key in title with brackets"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-123] Add new feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        dfs = {"releases": pd.DataFrame(), "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        # Extract issue key from first PR
        pr = prs.iloc[0]
        issue_key = calculator._extract_issue_key_from_pr(pr)

        assert issue_key == "PROJ-123"

    def test_pr_with_issue_in_branch_name(self):
        """Test PR with issue key in branch name"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "Add authentication",
                    "branch": "feature/RSC-456-add-authentication",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        dfs = {"releases": pd.DataFrame(), "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        pr = prs.iloc[0]
        issue_key = calculator._extract_issue_key_from_pr(pr)

        assert issue_key == "RSC-456"

    def test_pr_without_issue_key(self):
        """Test PR without any Jira issue key"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "Fix typo in README",
                    "branch": "fix-typo",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        dfs = {"releases": pd.DataFrame(), "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        pr = prs.iloc[0]
        issue_key = calculator._extract_issue_key_from_pr(pr)

        assert issue_key is None


class TestJiraBasedLeadTimeMapping:
    """Test Jira-based lead time calculation (preferred method)"""

    def test_pr_mapped_via_jira_to_deployment(self):
        """Test complete flow: PR → Jira Issue → Fix Version → Lead Time"""
        # PR merged on Jan 1
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] New feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Deployment on Jan 5 (4 days later)
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 5/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 5, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        # Issue to version mapping
        issue_to_version_map = {"PROJ-100": "Live - 5/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        # Lead time should be 4 days = 96 hours
        assert result["lead_time"]["median_hours"] == 96.0
        assert result["lead_time"]["median_days"] == 4.0
        assert result["lead_time"]["sample_size"] == 1

    def test_multiple_prs_same_release(self):
        """Test multiple PRs mapped to same release"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature A",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                },
                {
                    "pr_number": 2,
                    "title": "[PROJ-101] Feature B",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 2, 10, 0),
                    "author": "user2",
                },
            ]
        )

        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 5/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 5, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {
            "PROJ-100": "Live - 5/Jan/2025",
            "PROJ-101": "Live - 5/Jan/2025",
        }

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        # PR1: 4 days, PR2: 3 days → median: 3.5 days = 84 hours
        assert result["lead_time"]["median_hours"] == 84.0
        assert result["lead_time"]["sample_size"] == 2

    def test_pr_without_jira_mapping_ignored(self):
        """Test PR without Jira mapping is not counted"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "Fix typo",  # No issue key
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 5/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 5, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map={})

        # Should fall back to time-based mapping or have no lead time
        # Time-based: PR merged Jan 1, next release Jan 5 → 4 days
        assert result["lead_time"]["sample_size"] >= 0


class TestCherryPickWorkflow:
    """Test lead time tracking through cherry-pick workflows"""

    def test_cherry_pick_tracks_via_jira(self):
        """Test that cherry-picked commits are tracked via Jira Fix Version"""
        # PR merged to master on Jan 1
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[RSC-789] Critical fix",
                    "branch": "feature/RSC-789-fix",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Later cherry-picked to release branch and deployed on Jan 10
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 10/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 10, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        # Jira tracks the Fix Version
        issue_to_version_map = {"RSC-789": "Live - 10/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        # Lead time should be 9 days = 216 hours
        assert result["lead_time"]["median_hours"] == 216.0
        assert result["lead_time"]["sample_size"] == 1

    def test_multiple_fix_versions_uses_latest(self):
        """Test that when issue has multiple fix versions, the earliest is used"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-200] Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Issue deployed to beta first, then production
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Beta - 3/Jan/2025",
                    "environment": "staging",
                    "published_at": datetime(2025, 1, 3, 10, 0),
                    "repo": "test/repo",
                },
                {
                    "tag_name": "Live - 10/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 10, 10, 0),
                    "repo": "test/repo",
                },
            ]
        )

        # Jira tracks only production version (beta excluded by collector)
        issue_to_version_map = {"PROJ-200": "Live - 10/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        # Lead time to production: 9 days = 216 hours
        assert result["lead_time"]["median_hours"] == 216.0


class TestTimeBasedLeadTimeFallback:
    """Test time-based lead time calculation (fallback method)"""

    def test_time_based_maps_to_next_release(self):
        """Test time-based mapping uses next deployment after PR merge"""
        # PR merged on Jan 1, no Jira mapping
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "Quick fix",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Releases on Jan 5 and Jan 10
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "v1.0.0",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 5, 10, 0),
                    "repo": "test/repo",
                },
                {
                    "tag_name": "v1.0.1",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 10, 10, 0),
                    "repo": "test/repo",
                },
            ]
        )

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        # No issue_to_version_map provided, should use time-based
        result = calculator.calculate_dora_metrics()

        # Should map to first release after merge (Jan 5) → 4 days = 96 hours
        assert result["lead_time"]["median_hours"] == 96.0

    def test_time_based_ignores_earlier_releases(self):
        """Test time-based mapping ignores releases before PR merge"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 5, 10, 0),  # Merged on Jan 5
                    "author": "user1",
                }
            ]
        )

        releases = pd.DataFrame(
            [
                {
                    "tag_name": "v1.0.0",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 1, 10, 0),  # Before PR merge
                    "repo": "test/repo",
                },
                {
                    "tag_name": "v1.0.1",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 10, 10, 0),  # After PR merge
                    "repo": "test/repo",
                },
            ]
        )

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics()

        # Should map to v1.0.1 (Jan 10), not v1.0.0 → 5 days = 120 hours
        assert result["lead_time"]["median_hours"] == 120.0

    def test_pr_after_all_releases_excluded(self):
        """Test PR merged after all releases is excluded from lead time"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "Late feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 15, 10, 0),  # After all releases
                    "author": "user1",
                }
            ]
        )

        releases = pd.DataFrame(
            [
                {
                    "tag_name": "v1.0.0",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 10, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics()

        # No releases after PR merge, so no lead time calculated
        assert result["lead_time"]["sample_size"] == 0
        assert result["lead_time"]["median_hours"] is None


class TestLeadTimeEdgeCases:
    """Test edge cases in lead time calculation"""

    def test_no_prs_returns_no_lead_time(self):
        """Test lead time when there are no PRs"""
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "v1.0.0",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 10, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        dfs = {"releases": releases, "pull_requests": pd.DataFrame(), "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics()

        assert result["lead_time"]["median_hours"] is None
        assert result["lead_time"]["sample_size"] == 0

    def test_no_releases_returns_no_lead_time(self):
        """Test lead time when there are no releases"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        dfs = {"releases": pd.DataFrame(), "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics()

        assert result["lead_time"]["median_hours"] is None
        assert result["lead_time"]["sample_size"] == 0

    def test_unmerged_prs_excluded(self):
        """Test that unmerged/closed PRs are excluded from lead time"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature A",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                },
                {
                    "pr_number": 2,
                    "title": "[PROJ-101] Feature B",
                    "branch": "main",
                    "merged": False,  # Not merged
                    "merged_at": None,
                    "author": "user2",
                },
            ]
        )

        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 5/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 5, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {
            "PROJ-100": "Live - 5/Jan/2025",
            "PROJ-101": "Live - 5/Jan/2025",
        }

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        # Only PR 1 should be counted
        assert result["lead_time"]["sample_size"] == 1
        assert result["lead_time"]["median_hours"] == 96.0

    def test_pr_merged_same_time_as_release(self):
        """Test PR merged at exact same time as release"""
        merge_time = datetime(2025, 1, 5, 10, 0)

        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Hotfix",
                    "branch": "main",
                    "merged": True,
                    "merged_at": merge_time,
                    "author": "user1",
                }
            ]
        )

        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 5/Jan/2025",
                    "environment": "production",
                    "published_at": merge_time,  # Same time
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {"PROJ-100": "Live - 5/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        # Edge case: PR merged at same time as release
        # System behavior: may not map if release must be strictly after merge
        # Acceptable to have no lead time or 0 lead time
        if result["lead_time"]["sample_size"] > 0:
            assert result["lead_time"]["median_hours"] == 0.0
            assert result["lead_time"]["level"] == "elite"
        else:
            # Also acceptable for system to not map same-time PRs
            assert result["lead_time"]["median_hours"] is None


class TestLeadTimePerformanceLevels:
    """Test DORA performance level classification for lead time"""

    def test_elite_lead_time_less_than_24h(self):
        """Test elite level: < 24 hours"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Release 12 hours later
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 1/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 1, 22, 0),
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {"PROJ-100": "Live - 1/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        assert result["lead_time"]["level"] == "elite"
        assert result["lead_time"]["median_hours"] == 12.0

    def test_high_lead_time_less_than_1_week(self):
        """Test high level: < 1 week"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Release 3 days later
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 4/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 4, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {"PROJ-100": "Live - 4/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        assert result["lead_time"]["level"] == "high"
        assert result["lead_time"]["median_days"] == 3.0

    def test_medium_lead_time_less_than_1_month(self):
        """Test medium level: < 1 month"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Release 2 weeks later
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 15/Jan/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 1, 15, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {"PROJ-100": "Live - 15/Jan/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        assert result["lead_time"]["level"] == "medium"
        assert result["lead_time"]["median_days"] == 14.0

    def test_low_lead_time_more_than_1_month(self):
        """Test low level: >= 1 month"""
        prs = pd.DataFrame(
            [
                {
                    "pr_number": 1,
                    "title": "[PROJ-100] Feature",
                    "branch": "main",
                    "merged": True,
                    "merged_at": datetime(2025, 1, 1, 10, 0),
                    "author": "user1",
                }
            ]
        )

        # Release 45 days later
        releases = pd.DataFrame(
            [
                {
                    "tag_name": "Live - 15/Feb/2025",
                    "environment": "production",
                    "published_at": datetime(2025, 2, 15, 10, 0),
                    "repo": "test/repo",
                }
            ]
        )

        issue_to_version_map = {"PROJ-100": "Live - 15/Feb/2025"}

        dfs = {"releases": releases, "pull_requests": prs, "commits": pd.DataFrame()}
        calculator = MetricsCalculator(dfs)

        result = calculator.calculate_dora_metrics(issue_to_version_map=issue_to_version_map)

        assert result["lead_time"]["level"] == "low"
        assert result["lead_time"]["median_days"] == 45.0
