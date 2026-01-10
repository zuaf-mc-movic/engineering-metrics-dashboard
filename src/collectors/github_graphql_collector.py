"""
GitHub GraphQL Collector - More efficient than REST API

Uses GitHub's GraphQL API v4 to collect metrics with fewer API calls.
GraphQL has a separate rate limit (5000 points/hour) from REST API.
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import pandas as pd


class GitHubGraphQLCollector:
    def __init__(self, token: str, organization: str = None, teams: List[str] = None,
                 team_members: List[str] = None, days_back: int = 90,
                 max_pages_per_repo: int = 5):
        """Initialize GitHub GraphQL collector

        Args:
            token: GitHub personal access token
            organization: GitHub organization name
            teams: List of team slugs to collect from
            team_members: List of GitHub usernames to filter by
            days_back: Number of days to look back (default: 90)
            max_pages_per_repo: Max pages to fetch per repo (default: 5, 50 PRs per page)
        """
        self.token = token
        self.organization = organization
        self.teams = teams or []
        self.team_members = team_members or []
        self.days_back = days_back
        self.max_pages_per_repo = max_pages_per_repo
        self.since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        self.api_url = "https://api.github.com/graphql"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def _execute_query(self, query: str, variables: Dict = None) -> Dict:
        """Execute a GraphQL query"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(self.api_url, json=payload, headers=self.headers)

        if response.status_code != 200:
            raise Exception(f"GraphQL query failed: {response.status_code} - {response.text}")

        result = response.json()

        if "errors" in result:
            raise Exception(f"GraphQL errors: {result['errors']}")

        return result["data"]

    def _get_team_repositories(self) -> List[str]:
        """Get repository names for team using GraphQL"""
        if not self.organization or not self.teams:
            return []

        repo_names = set()

        for team_slug in self.teams:
            print(f"  Fetching repos for team: {team_slug}")

            query = """
            query($org: String!, $team: String!, $cursor: String) {
              organization(login: $org) {
                team(slug: $team) {
                  repositories(first: 100, after: $cursor) {
                    nodes {
                      nameWithOwner
                    }
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                  }
                }
              }
            }
            """

            cursor = None
            while True:
                try:
                    data = self._execute_query(query, {
                        "org": self.organization,
                        "team": team_slug,
                        "cursor": cursor
                    })

                    if not data.get("organization") or not data["organization"].get("team"):
                        print(f"    Team not found or no access: {team_slug}")
                        break

                    team_data = data["organization"]["team"]
                    repos = team_data["repositories"]["nodes"]

                    for repo in repos:
                        repo_names.add(repo["nameWithOwner"])

                    if not team_data["repositories"]["pageInfo"]["hasNextPage"]:
                        break

                    cursor = team_data["repositories"]["pageInfo"]["endCursor"]

                except Exception as e:
                    print(f"    Error fetching repos for team {team_slug}: {e}")
                    break

            print(f"    Found {len(repo_names)} repositories")

        return list(repo_names)

    def collect_all_metrics(self):
        """Collect all metrics using GraphQL"""
        all_data = {
            'pull_requests': [],
            'reviews': [],
            'commits': [],
            'deployments': []
        }

        # Get repositories
        if self.teams and self.organization:
            repo_names = self._get_team_repositories()
            print(f"Total repositories to collect: {len(repo_names)}")
        else:
            print("⚠️  No teams configured for GraphQL collection")
            return all_data

        # Collect metrics for each repository
        for repo_name in repo_names:
            print(f"Collecting metrics for {repo_name}...")

            try:
                owner, name = repo_name.split("/")

                # Collect PRs, reviews, and commits in one query
                pr_data = self._collect_repository_metrics(owner, name)

                all_data['pull_requests'].extend(pr_data['pull_requests'])
                all_data['reviews'].extend(pr_data['reviews'])
                all_data['commits'].extend(pr_data['commits'])

            except Exception as e:
                print(f"  Error collecting metrics for {repo_name}: {e}")
                continue

        # Filter by team members if specified
        if self.team_members:
            all_data = self._filter_by_team_members(all_data)

        return all_data

    def _filter_by_team_members(self, data):
        """Filter data to only include specified team members"""
        filtered_data = {
            'pull_requests': [pr for pr in data['pull_requests']
                            if pr['author'] in self.team_members],
            'reviews': [r for r in data['reviews']
                       if r['reviewer'] in self.team_members or r.get('pr_author') in self.team_members],
            'commits': [c for c in data['commits']
                       if c['author'] in self.team_members],
            'deployments': data['deployments']
        }

        print(f"  Filtered to team members: {len(filtered_data['pull_requests'])} PRs, "
              f"{len(filtered_data['reviews'])} reviews, {len(filtered_data['commits'])} commits")

        return filtered_data

    def _collect_repository_metrics(self, owner: str, repo_name: str) -> Dict:
        """Collect PRs, reviews, and commits for a repository using a single GraphQL query"""
        since_iso = self.since_date.isoformat()

        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            pullRequests(first: 50, orderBy: {field: CREATED_AT, direction: DESC}, after: $cursor) {
              nodes {
                number
                title
                author {
                  login
                }
                createdAt
                mergedAt
                closedAt
                state
                merged
                additions
                deletions
                changedFiles
                comments {
                  totalCount
                }
                reviews(first: 100) {
                  nodes {
                    author {
                      login
                    }
                    submittedAt
                    state
                  }
                }
                reviewRequests(first: 10) {
                  totalCount
                }
                commits(first: 250) {
                  totalCount
                  nodes {
                    commit {
                      oid
                      author {
                        user {
                          login
                        }
                        name
                        email
                        date
                      }
                      committedDate
                      additions
                      deletions
                    }
                  }
                }
              }
              pageInfo {
                hasNextPage
                endCursor
              }
            }
          }
        }
        """

        pull_requests = []
        reviews = []
        commits_data = []

        # Stats tracking
        total_prs_fetched = 0
        total_prs_filtered_out = 0
        hit_page_limit = False

        cursor = None
        page_count = 0
        max_pages = self.max_pages_per_repo

        while page_count < max_pages:
            try:
                data = self._execute_query(query, {
                    "owner": owner,
                    "name": repo_name,
                    "cursor": cursor
                })

                if not data.get("repository"):
                    break

                pr_data = data["repository"]["pullRequests"]
                prs = pr_data["nodes"]

                prs_in_date_range_on_this_page = 0

                for pr in prs:
                    total_prs_fetched += 1

                    # Skip PRs created before our since_date
                    pr_created = datetime.fromisoformat(pr["createdAt"].replace('Z', '+00:00'))
                    if pr_created < self.since_date:
                        total_prs_filtered_out += 1
                        continue

                    prs_in_date_range_on_this_page += 1

                    pr_author = pr["author"]["login"] if pr["author"] else "unknown"

                    # Calculate cycle time
                    cycle_time_hours = None
                    if pr["mergedAt"]:
                        merged_at = datetime.fromisoformat(pr["mergedAt"].replace('Z', '+00:00'))
                        cycle_time_hours = (merged_at - pr_created).total_seconds() / 3600
                    elif pr["closedAt"]:
                        closed_at = datetime.fromisoformat(pr["closedAt"].replace('Z', '+00:00'))
                        cycle_time_hours = (closed_at - pr_created).total_seconds() / 3600

                    # Calculate time to first review
                    time_to_first_review_hours = None
                    if pr["reviews"]["nodes"]:
                        review_times = [
                            datetime.fromisoformat(r["submittedAt"].replace('Z', '+00:00'))
                            for r in pr["reviews"]["nodes"]
                            if r["submittedAt"]
                        ]
                        if review_times:
                            first_review = min(review_times)
                            time_to_first_review_hours = (first_review - pr_created).total_seconds() / 3600

                    pr_entry = {
                        'repo': f"{owner}/{repo_name}",
                        'pr_number': pr["number"],
                        'title': pr["title"],
                        'author': pr_author,
                        'created_at': pr_created,
                        'merged_at': datetime.fromisoformat(pr["mergedAt"].replace('Z', '+00:00')) if pr["mergedAt"] else None,
                        'closed_at': datetime.fromisoformat(pr["closedAt"].replace('Z', '+00:00')) if pr["closedAt"] else None,
                        'state': pr["state"].lower(),
                        'merged': pr["merged"],
                        'additions': pr["additions"],
                        'deletions': pr["deletions"],
                        'changed_files': pr["changedFiles"],
                        'comments': pr["comments"]["totalCount"],
                        'review_comments': len(pr["reviews"]["nodes"]),
                        'commits': pr["commits"]["totalCount"],
                        'cycle_time_hours': cycle_time_hours,
                        'time_to_first_review_hours': time_to_first_review_hours
                    }

                    pull_requests.append(pr_entry)

                    # Extract reviews
                    for review in pr["reviews"]["nodes"]:
                        if review["author"]:
                            reviews.append({
                                'repo': f"{owner}/{repo_name}",
                                'pr_number': pr["number"],
                                'reviewer': review["author"]["login"],
                                'submitted_at': datetime.fromisoformat(review["submittedAt"].replace('Z', '+00:00')) if review["submittedAt"] else None,
                                'state': review["state"],
                                'pr_author': pr_author
                            })

                    # Extract commits from PR (use PR commits instead of default branch)
                    for commit_node in pr["commits"]["nodes"]:
                        commit = commit_node["commit"]
                        if commit["author"]:
                            # Prefer GitHub username, fallback to Git name
                            author = "unknown"
                            if commit["author"].get("user") and commit["author"]["user"]:
                                author = commit["author"]["user"]["login"]
                            elif commit["author"].get("name"):
                                author = commit["author"]["name"]

                            commits_data.append({
                                'repo': f"{owner}/{repo_name}",
                                'sha': commit["oid"],
                                'author': author,
                                'email': commit["author"]["email"],
                                'date': datetime.fromisoformat(commit["author"]["date"].replace('Z', '+00:00')) if commit["author"]["date"] else None,
                                'committed_date': datetime.fromisoformat(commit["committedDate"].replace('Z', '+00:00')) if commit["committedDate"] else None,
                                'additions': commit["additions"],
                                'deletions': commit["deletions"],
                                'pr_number': pr["number"],
                                'pr_created_at': pr_created
                            })

                # Early termination: if no PRs in date range on this page, stop paginating
                if prs_in_date_range_on_this_page == 0:
                    print(f"  No more PRs in date range, stopping pagination at page {page_count + 1}")
                    break

                if not pr_data["pageInfo"]["hasNextPage"]:
                    break

                cursor = pr_data["pageInfo"]["endCursor"]
                page_count += 1

            except Exception as e:
                print(f"  Error in pagination: {e}")
                break

        # Check if we hit the page limit
        if page_count >= max_pages and pr_data.get("pageInfo", {}).get("hasNextPage"):
            hit_page_limit = True

        # Log stats
        print(f"  Fetched {total_prs_fetched} PRs, filtered out {total_prs_filtered_out} (outside date range)")
        if hit_page_limit:
            print(f"  ⚠️  WARNING: Hit {max_pages}-page limit. Some PRs may be missing!")

        # Deduplicate commits (same commit can be in multiple PRs)
        seen_shas = set()
        unique_commits = []
        for commit in commits_data:
            if commit['sha'] not in seen_shas:
                seen_shas.add(commit['sha'])
                unique_commits.append(commit)

        # NOTE: We now collect commits from PRs instead of default branch
        # This ensures PRs and commits use consistent date filtering (PR creation date)
        # Old method: self._collect_commits_graphql(owner, repo_name) - used default branch

        return {
            'pull_requests': pull_requests,
            'reviews': reviews,
            'commits': unique_commits
        }


    def collect_team_metrics(self, team_name: str, team_members: List[str],
                           start_date: datetime = None, end_date: datetime = None):
        """Collect metrics for a specific team"""
        original_members = self.team_members
        original_since = self.since_date

        self.team_members = team_members

        if start_date:
            # Ensure timezone-aware datetime
            if start_date.tzinfo is None:
                self.since_date = start_date.replace(tzinfo=timezone.utc)
            else:
                self.since_date = start_date
        if end_date:
            # Ensure timezone-aware datetime
            if end_date.tzinfo is None:
                self.end_date = end_date.replace(tzinfo=timezone.utc)
            else:
                self.end_date = end_date
        else:
            self.end_date = datetime.now(timezone.utc)

        data = self.collect_all_metrics()

        # Add team label
        for pr in data['pull_requests']:
            pr['team'] = team_name
        for review in data['reviews']:
            review['team'] = team_name
        for commit in data['commits']:
            commit['team'] = team_name

        # Restore original settings
        self.team_members = original_members
        self.since_date = original_since
        if hasattr(self, 'end_date'):
            delattr(self, 'end_date')

        return data

    def collect_person_metrics(self, username: str, start_date: datetime, end_date: datetime):
        """Collect metrics for a specific person"""
        original_members = self.team_members
        original_since = self.since_date

        self.team_members = [username]
        # Ensure timezone-aware datetime
        if start_date.tzinfo is None:
            self.since_date = start_date.replace(tzinfo=timezone.utc)
        else:
            self.since_date = start_date
        # Ensure end_date is also timezone-aware
        if end_date.tzinfo is None:
            self.end_date = end_date.replace(tzinfo=timezone.utc)
        else:
            self.end_date = end_date

        data = self.collect_all_metrics()

        # Filter by date range
        if hasattr(self, 'end_date'):
            data['pull_requests'] = [
                pr for pr in data['pull_requests']
                if pr['created_at'] <= self.end_date
            ]
            data['reviews'] = [
                r for r in data['reviews']
                if r['submitted_at'] and r['submitted_at'] <= self.end_date
            ]
            data['commits'] = [
                c for c in data['commits']
                if c['date'] <= self.end_date
            ]

        # Restore
        self.team_members = original_members
        self.since_date = original_since
        if hasattr(self, 'end_date'):
            delattr(self, 'end_date')

        return data

    def get_dataframes(self):
        """Return all metrics as pandas DataFrames"""
        data = self.collect_all_metrics()

        return {
            'pull_requests': pd.DataFrame(data['pull_requests']),
            'reviews': pd.DataFrame(data['reviews']),
            'commits': pd.DataFrame(data['commits']),
            'deployments': pd.DataFrame(data['deployments']),
        }
