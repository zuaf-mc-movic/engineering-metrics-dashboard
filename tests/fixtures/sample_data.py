"""
Sample data generators for testing

Provides reusable test data for various test scenarios
"""
import pandas as pd
from datetime import datetime, timezone, timedelta


def generate_sample_github_prs(count=5):
    """Generate sample PR data for testing"""
    base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    return pd.DataFrame({
        'pr_number': list(range(1, count + 1)),
        'author': ['alice', 'bob', 'alice', 'charlie', 'bob'][:count],
        'merged': [True, True, False, True, True][:count],
        'state': ['merged', 'merged', 'open', 'merged', 'merged'][:count],
        'additions': [100, 200, 50, 300, 150][:count],
        'deletions': [50, 100, 25, 150, 75][:count],
        'cycle_time_hours': [24.0, 48.0, None, 36.0, 30.0][:count],
        'time_to_first_review_hours': [2.0, 4.0, None, 3.0, 2.5][:count],
        'created': [base_date + timedelta(days=i) for i in range(count)]
    })


def generate_sample_reviews(count=10):
    """Generate sample review data for testing"""
    base_date = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    return pd.DataFrame({
        'reviewer': ['alice', 'bob', 'alice', 'charlie', 'bob',
                     'alice', 'charlie', 'bob', 'alice', 'charlie'][:count],
        'pr_number': [1, 1, 2, 2, 3, 3, 4, 4, 5, 5][:count],
        'state': ['APPROVED', 'APPROVED', 'CHANGES_REQUESTED', 'APPROVED',
                  'APPROVED', 'APPROVED', 'APPROVED', 'CHANGES_REQUESTED',
                  'APPROVED', 'APPROVED'][:count],
        'submitted_at': [base_date + timedelta(hours=i*2) for i in range(count)]
    })


def generate_sample_commits(count=10):
    """Generate sample commit data for testing"""
    base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    return pd.DataFrame({
        'sha': [f'commit{i:03d}' for i in range(count)],
        'author': ['alice', 'bob', 'alice', 'charlie', 'bob',
                   'alice', 'charlie', 'bob', 'alice', 'charlie'][:count],
        'date': [base_date + timedelta(hours=i*6) for i in range(count)],
        'additions': [100, 200, 50, 300, 150, 80, 120, 90, 110, 200][:count],
        'deletions': [50, 100, 25, 150, 75, 40, 60, 45, 55, 100][:count]
    })


def get_github_graphql_pr_response():
    """Sample GitHub GraphQL API response for PRs"""
    return {
        'data': {
            'repository': {
                'pullRequests': {
                    'nodes': [
                        {
                            'number': 123,
                            'title': 'Add new feature',
                            'author': {'login': 'alice'},
                            'createdAt': '2025-01-01T10:00:00Z',
                            'mergedAt': '2025-01-02T10:00:00Z',
                            'closedAt': '2025-01-02T10:00:00Z',
                            'state': 'MERGED',
                            'merged': True,
                            'additions': 150,
                            'deletions': 50,
                            'reviews': {
                                'nodes': [
                                    {
                                        'author': {'login': 'bob'},
                                        'state': 'APPROVED',
                                        'submittedAt': '2025-01-01T14:00:00Z'
                                    }
                                ]
                            },
                            'commits': {
                                'nodes': [
                                    {
                                        'commit': {
                                            'oid': 'abc123',
                                            'author': {
                                                'user': {'login': 'alice'},
                                                'name': 'Alice Developer',
                                                'email': 'alice@example.com',
                                                'date': '2025-01-01T09:00:00Z'
                                            },
                                            'committedDate': '2025-01-01T09:00:00Z',
                                            'additions': 150,
                                            'deletions': 50
                                        }
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
        }
    }


def get_github_graphql_error_response():
    """Sample GitHub GraphQL error response"""
    return {
        'errors': [
            {
                'message': 'API rate limit exceeded',
                'type': 'RATE_LIMITED'
            }
        ]
    }


def get_jira_issue_response():
    """Sample Jira API issue response"""
    return {
        'key': 'PROJ-123',
        'fields': {
            'summary': 'Implement new feature',
            'status': {'name': 'Done'},
            'assignee': {
                'displayName': 'Alice Developer',
                'name': 'alice.jira'
            },
            'created': '2025-01-01T10:00:00.000+0000',
            'resolutiondate': '2025-01-10T15:00:00.000+0000',
            'issuetype': {'name': 'Story'},
            'priority': {'name': 'High'}
        },
        'changelog': {
            'histories': [
                {
                    'created': '2025-01-02T10:00:00.000+0000',
                    'items': [
                        {
                            'field': 'status',
                            'fromString': 'To Do',
                            'toString': 'In Progress'
                        }
                    ]
                },
                {
                    'created': '2025-01-08T10:00:00.000+0000',
                    'items': [
                        {
                            'field': 'status',
                            'fromString': 'In Progress',
                            'toString': 'In Review'
                        }
                    ]
                },
                {
                    'created': '2025-01-10T15:00:00.000+0000',
                    'items': [
                        {
                            'field': 'status',
                            'fromString': 'In Review',
                            'toString': 'Done'
                        }
                    ]
                }
            ]
        }
    }


def get_jira_filter_response():
    """Sample Jira filter search response"""
    return {
        'total': 2,
        'issues': [
            {
                'key': 'PROJ-100',
                'fields': {
                    'summary': 'Bug fix',
                    'status': {'name': 'In Progress'},
                    'assignee': {'name': 'bob.jira'},
                    'created': '2025-01-05T10:00:00.000+0000',
                    'resolutiondate': None,
                    'issuetype': {'name': 'Bug'}
                }
            },
            {
                'key': 'PROJ-101',
                'fields': {
                    'summary': 'Feature request',
                    'status': {'name': 'Done'},
                    'assignee': {'name': 'alice.jira'},
                    'created': '2025-01-03T10:00:00.000+0000',
                    'resolutiondate': '2025-01-12T10:00:00.000+0000',
                    'issuetype': {'name': 'Story'}
                }
            }
        ]
    }
