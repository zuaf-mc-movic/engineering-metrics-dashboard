"""
Shared pytest fixtures for Team Metrics Dashboard tests
"""
import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta


@pytest.fixture
def sample_pr_dataframe():
    """Sample PR DataFrame for testing metrics calculations"""
    return pd.DataFrame({
        'pr_number': [1, 2, 3, 4],
        'author': ['alice', 'bob', 'alice', 'charlie'],
        'merged': [True, True, False, True],
        'state': ['merged', 'merged', 'open', 'merged'],
        'additions': [100, 200, 50, 300],
        'deletions': [50, 100, 25, 150],
        'cycle_time_hours': [24.0, 48.0, None, 36.0],
        'time_to_first_review_hours': [2.0, 4.0, None, 3.0],
        'created': [
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
            datetime(2025, 1, 4, tzinfo=timezone.utc)
        ]
    })


@pytest.fixture
def sample_reviews_dataframe():
    """Sample reviews DataFrame for testing"""
    return pd.DataFrame({
        'reviewer': ['alice', 'bob', 'alice', 'charlie'],
        'pr_number': [1, 1, 2, 3],
        'state': ['APPROVED', 'APPROVED', 'CHANGES_REQUESTED', 'APPROVED'],
        'submitted_at': [
            datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 3, 9, 0, tzinfo=timezone.utc)
        ]
    })


@pytest.fixture
def sample_commits_dataframe():
    """Sample commits DataFrame for testing"""
    return pd.DataFrame({
        'sha': ['abc123', 'def456', 'ghi789', 'jkl012'],
        'author': ['alice', 'bob', 'alice', 'charlie'],
        'date': [
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
            datetime(2025, 1, 4, tzinfo=timezone.utc)
        ],
        'additions': [100, 200, 50, 300],
        'deletions': [50, 100, 25, 150]
    })


@pytest.fixture
def empty_dataframes():
    """Empty DataFrames for edge case testing"""
    return {
        'pull_requests': pd.DataFrame(),
        'reviews': pd.DataFrame(),
        'commits': pd.DataFrame(),
        'deployments': pd.DataFrame()
    }


@pytest.fixture
def sample_team_config():
    """Sample team configuration for testing"""
    return {
        'name': 'TestTeam',
        'display_name': 'Test Team',
        'github': {
            'team_slug': 'test-team',
            'members': ['alice', 'bob', 'charlie']
        },
        'jira': {
            'members': ['alice.jira', 'bob.jira', 'charlie.jira'],
            'filters': {
                'wip': 12345,
                'completed_12weeks': 12346,
                'bugs': 12347
            }
        }
    }


@pytest.fixture
def sample_jira_issues():
    """Sample Jira issues for testing"""
    return [
        {
            'key': 'TEST-1',
            'summary': 'Test issue 1',
            'status': 'Done',
            'assignee': 'alice.jira',
            'created': '2025-01-01T10:00:00.000+0000',
            'resolved': '2025-01-05T10:00:00.000+0000',
            'issue_type': 'Story'
        },
        {
            'key': 'TEST-2',
            'summary': 'Test issue 2',
            'status': 'In Progress',
            'assignee': 'bob.jira',
            'created': '2025-01-02T10:00:00.000+0000',
            'resolved': None,
            'issue_type': 'Bug'
        },
        {
            'key': 'TEST-3',
            'summary': 'Test issue 3',
            'status': 'Done',
            'assignee': 'charlie.jira',
            'created': '2025-01-03T10:00:00.000+0000',
            'resolved': '2025-01-10T10:00:00.000+0000',
            'issue_type': 'Task'
        }
    ]


@pytest.fixture
def sample_github_graphql_response():
    """Sample GitHub GraphQL API response for testing"""
    return {
        'data': {
            'organization': {
                'team': {
                    'repositories': {
                        'nodes': [
                            {
                                'name': 'test-repo',
                                'pullRequests': {
                                    'nodes': [
                                        {
                                            'number': 1,
                                            'author': {'login': 'alice'},
                                            'createdAt': '2025-01-01T10:00:00Z',
                                            'mergedAt': '2025-01-02T10:00:00Z',
                                            'additions': 100,
                                            'deletions': 50,
                                            'reviews': {
                                                'nodes': [
                                                    {
                                                        'author': {'login': 'bob'},
                                                        'state': 'APPROVED',
                                                        'submittedAt': '2025-01-01T12:00:00Z'
                                                    }
                                                ]
                                            }
                                        }
                                    ],
                                    'pageInfo': {
                                        'hasNextPage': False,
                                        'endCursor': None
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
    }
