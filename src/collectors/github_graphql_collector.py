"""
GitHub GraphQL Collector - More efficient than REST API

Uses GitHub's GraphQL API v4 to collect metrics with fewer API calls.
GraphQL has a separate rate limit (5000 points/hour) from REST API.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

import pandas as pd
import requests

from src.utils.logging import get_logger
from src.utils.repo_cache import get_cached_repositories, save_cached_repositories


class GitHubGraphQLCollector:
    def __init__(
        self,
        token: str,
        organization: Optional[str] = None,
        teams: Optional[List[str]] = None,
        team_members: Optional[List[str]] = None,
        days_back: int = 90,
        max_pages_per_repo: int = 10,
        repo_workers: int = 5,
    ):
        """Initialize GitHub GraphQL collector

        Args:
            token: GitHub personal access token
            organization: GitHub organization name
            teams: List of team slugs to collect from
            team_members: List of GitHub usernames to filter by
            days_back: Number of days to look back (default: 90)
            max_pages_per_repo: Max pages to fetch per repo (default: 5, 50 PRs per page)
            repo_workers: Number of repos to collect in parallel (default: 5)
        """
        self.token = token
        self.organization = organization
        self.teams = teams or []
        self.team_members = team_members or []
        self.days_back = days_back
        self.max_pages_per_repo = max_pages_per_repo
        self.repo_workers = repo_workers
        self.since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        self.api_url = "https://api.github.com/graphql"
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Initialize logger
        self.out = get_logger("team_metrics.collectors.github")

        # Track collection status
        self.collection_status: Dict[str, Any] = {
            "successful_repos": [],
            "failed_repos": [],
            "partial_repos": [],
            "total_errors": 0,
            "start_time": None,
            "end_time": None,
        }

        # Create session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Configure connection pool for parallel workers
        # Default pool size is 10, increase for parallel operations
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,  # Number of connection pools
            pool_maxsize=20,  # Max connections per pool
            max_retries=0,  # We handle retries manually
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _execute_query(self, query: str, variables: Optional[Dict] = None, max_retries: int = 3) -> Dict:
        """Execute a GraphQL query with retry logic for transient errors"""
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(max_retries):
            try:
                response = self.session.post(self.api_url, json=payload)

                # Transient errors - retry with exponential backoff
                if response.status_code in [502, 504, 503, 429]:
                    if attempt < max_retries - 1:
                        sleep_time = 2**attempt  # 1s, 2s, 4s
                        self.out.warning(
                            f"{response.status_code} error, retrying in {sleep_time}s... (attempt {attempt+1}/{max_retries})",
                            indent=4,
                        )
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise Exception(f"Max retries ({max_retries}) exceeded: {response.status_code}")

                # Permanent errors - don't retry
                if response.status_code in [401, 403, 404, 400]:
                    raise Exception(f"GraphQL query failed: {response.status_code} - {response.text}")

                # Other errors - could be transient, retry once
                if response.status_code != 200:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    raise Exception(f"GraphQL query failed: {response.status_code}")

                # Success - validate response
                if response.status_code == 200:
                    result = response.json()

                    if "errors" in result:
                        raise Exception(f"GraphQL errors: {result['errors']}")

                    return cast(Dict[Any, Any], result["data"])

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    self.out.warning(f"Timeout, retrying... (attempt {attempt+1}/{max_retries})", indent=4)
                    time.sleep(2**attempt)
                    continue
                raise Exception("Request timeout after max retries")

            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    self.out.warning(f"Connection error, retrying... (attempt {attempt+1}/{max_retries})", indent=4)
                    time.sleep(2**attempt)
                    continue
                raise Exception("Connection error after max retries")

        raise Exception("Query failed after max retries")

    def _get_team_repositories(self) -> List[str]:
        """Get repository names for team using GraphQL (with caching)"""
        if not self.organization or not self.teams:
            return []

        # Try to get from cache first
        cached_repos = get_cached_repositories(self.organization, self.teams)
        if cached_repos is not None:
            self.out.success(f"Using cached repositories ({len(cached_repos)} repos)", indent=2)
            return cached_repos

        # Cache miss - fetch from GitHub
        self.out.info("Fetching repositories from GitHub...", emoji="📡", indent=2)
        repo_names = set()

        for team_slug in self.teams:
            self.out.info(f"Team: {team_slug}", indent=4)

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
                    data = self._execute_query(query, {"org": self.organization, "team": team_slug, "cursor": cursor})

                    if not data.get("organization") or not data["organization"].get("team"):
                        self.out.warning(f"Team not found or no access: {team_slug}", indent=6)
                        break

                    team_data = data["organization"]["team"]
                    repos = team_data["repositories"]["nodes"]

                    for repo in repos:
                        repo_names.add(repo["nameWithOwner"])

                    if not team_data["repositories"]["pageInfo"]["hasNextPage"]:
                        break

                    cursor = team_data["repositories"]["pageInfo"]["endCursor"]

                except Exception as e:
                    self.out.error(f"Error fetching repos for team {team_slug}: {e}", indent=6)
                    break

            self.out.info(f"Found {len(repo_names)} repositories", indent=6)

        repo_list = list(repo_names)

        # Save to cache for next time
        save_cached_repositories(self.organization, self.teams, repo_list)

        return repo_list

    def _collect_single_repository(self, repo_name: str) -> Dict[str, Any]:
        """Collect metrics for a single repository (for parallel execution)

        Args:
            repo_name: Repository name in format "owner/name"

        Returns:
            Dictionary with keys: pull_requests, reviews, commits, releases,
            success (bool), error (str or None), repo (str)
        """
        result = {
            "pull_requests": [],
            "reviews": [],
            "commits": [],
            "releases": [],
            "success": False,
            "error": None,
            "repo": repo_name,
        }

        try:
            owner, name = repo_name.split("/")

            # Collect PRs, reviews, commits, AND releases in batched queries
            batch_data = self._collect_repository_metrics_batched(owner, name)

            # Check if data was collected
            has_data = batch_data["pull_requests"] or batch_data["reviews"] or batch_data["commits"]

            result["pull_requests"] = batch_data["pull_requests"]
            result["reviews"] = batch_data["reviews"]
            result["commits"] = batch_data["commits"]
            result["releases"] = batch_data["releases"]
            result["success"] = has_data

            if not has_data:
                result["error"] = "No data returned (empty repo or early termination)"

        except Exception as e:
            result["error"] = str(e)
            result["success"] = False

        return result

    def collect_all_metrics(self):
        """Collect all metrics using GraphQL"""
        all_data: Dict[str, List[Any]] = {
            "pull_requests": [],
            "reviews": [],
            "commits": [],
            "deployments": [],
            "releases": [],
        }

        # Get repositories
        if self.teams and self.organization:
            repo_names = self._get_team_repositories()
            self.out.info(f"Total repositories to collect: {len(repo_names)}")
        else:
            self.out.warning("No teams configured for GraphQL collection")
            return all_data

        # Track collection timing
        self.collection_status["start_time"] = datetime.now()

        # Determine if parallel collection is enabled
        use_parallel = self.repo_workers > 1 and len(repo_names) > 1

        if use_parallel:
            self.out.info(f"Using parallel repository collection ({self.repo_workers} workers)", emoji="⚡")
            self.out.info("")

            # Parallel repository collection
            with ThreadPoolExecutor(max_workers=self.repo_workers) as executor:
                # Submit all repository collection jobs
                futures = {
                    executor.submit(self._collect_single_repository, repo_name): repo_name for repo_name in repo_names
                }

                # Collect results as they complete
                completed = 0
                total = len(repo_names)

                for future in as_completed(futures):
                    repo_name = futures[future]
                    completed += 1

                    try:
                        result = future.result()

                        # Track collection status
                        if result["success"]:
                            self.collection_status["successful_repos"].append(result["repo"])
                            status = "✓"
                        elif result["error"]:
                            if "No data returned" in result["error"]:
                                # Partial - empty repo
                                self.collection_status["partial_repos"].append(
                                    {"repo": result["repo"], "reason": result["error"]}
                                )
                                status = "⚠️"
                            else:
                                # Failed
                                self.collection_status["failed_repos"].append(
                                    {
                                        "repo": result["repo"],
                                        "error": result["error"],
                                        "error_type": "Unknown",
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                )
                                self.collection_status["total_errors"] += 1
                                status = "❌"
                        else:
                            status = "⚠️"

                        # Aggregate data
                        all_data["pull_requests"].extend(result["pull_requests"])
                        all_data["reviews"].extend(result["reviews"])
                        all_data["commits"].extend(result["commits"])
                        all_data["releases"].extend(result["releases"])

                        # Print progress
                        self.out.progress(completed, total, repo_name, status_emoji=status)

                    except Exception as e:
                        self.collection_status["failed_repos"].append(
                            {
                                "repo": repo_name,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                        self.collection_status["total_errors"] += 1
                        self.out.progress(completed, total, f"{repo_name}: {e}", status_emoji="❌")

        else:
            # Sequential collection (fallback or single repo)
            self.out.info("Using sequential repository collection", emoji="ℹ️")
            self.out.info("")

            for repo_name in repo_names:
                self.out.info(f"Collecting metrics for {repo_name}...")

                try:
                    owner, name = repo_name.split("/")

                    # Collect PRs, reviews, and commits in one query
                    pr_data = self._collect_repository_metrics(owner, name)

                    # Check if data was collected
                    has_data = pr_data["pull_requests"] or pr_data["reviews"] or pr_data["commits"]

                    if has_data:
                        self.collection_status["successful_repos"].append(repo_name)
                    else:
                        # Empty but no error - might be genuinely empty or partial
                        self.collection_status["partial_repos"].append(
                            {"repo": repo_name, "reason": "No data returned (empty repo or early termination)"}
                        )

                    all_data["pull_requests"].extend(pr_data["pull_requests"])
                    all_data["reviews"].extend(pr_data["reviews"])
                    all_data["commits"].extend(pr_data["commits"])
                    all_data["releases"].extend(pr_data.get("releases", []))

                except Exception as e:
                    # Track failed repo
                    self.collection_status["failed_repos"].append(
                        {
                            "repo": repo_name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    self.collection_status["total_errors"] += 1

                    self.out.error(f"Failed after retries: {e}", indent=2)
                    continue

        self.collection_status["end_time"] = datetime.now()

        # Print summary
        self.out.info("")
        self.out.info("Collection Summary:", emoji="📊")
        self.out.success(f"Successful: {len(self.collection_status['successful_repos'])} repos", indent=2)
        if self.collection_status["partial_repos"]:
            self.out.warning(f"Partial: {len(self.collection_status['partial_repos'])} repos", indent=2)
        if self.collection_status["failed_repos"]:
            self.out.error(f"Failed: {len(self.collection_status['failed_repos'])} repos", indent=2)
            for failed in self.collection_status["failed_repos"]:
                self.out.info(f"- {failed['repo']}: {failed['error'][:80]}", indent=5)

        # Filter by team members if specified
        if self.team_members:
            all_data = self._filter_by_team_members(all_data)

        return all_data

    def _filter_by_team_members(self, data):
        """Filter data to only include specified team members"""
        filtered_data = {
            "pull_requests": [pr for pr in data["pull_requests"] if pr["author"] in self.team_members],
            "reviews": [
                r
                for r in data["reviews"]
                if r["reviewer"] in self.team_members or r.get("pr_author") in self.team_members
            ],
            "commits": [c for c in data["commits"] if c["author"] in self.team_members],
            "deployments": data["deployments"],
            "releases": data.get("releases", []),  # Don't filter releases by person
        }

        self.out.info(
            f"Filtered to team members: {len(filtered_data['pull_requests'])} PRs, "
            f"{len(filtered_data['reviews'])} reviews, {len(filtered_data['commits'])} commits",
            indent=2,
        )

        if filtered_data["releases"]:
            self.out.info(f"- Releases: {len(filtered_data['releases'])} (team-level)", indent=3)

        return filtered_data

    def _is_pr_in_date_range(self, pr: Dict) -> bool:
        """Check if PR is within the collection date range"""
        created_at = pr.get("createdAt")
        if not created_at:
            return False

        created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return created_date >= self.since_date

    def _is_release_in_date_range(self, release: Dict) -> bool:
        """Check if release is within the collection date range"""
        published = release.get("publishedAt")
        created = release.get("createdAt")
        release_date_str = published if published else created

        if not release_date_str:
            return False

        release_date = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
        return release_date >= self.since_date

    def _extract_pr_data(self, pr: Dict) -> Dict:
        """Extract PR data from GraphQL response"""
        return {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "author": pr.get("author", {}).get("login") if pr.get("author") else None,
            "created_at": pr.get("createdAt"),
            "merged_at": pr.get("mergedAt"),
            "closed_at": pr.get("closedAt"),
            "state": pr.get("state"),
            "merged": pr.get("merged", False),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changedFiles", 0),
        }

    def _extract_review_data(self, pr: Dict) -> List[Dict]:
        """Extract review data from PR"""
        reviews = []
        pr_author = pr.get("author", {}).get("login") if pr.get("author") else None

        for review in pr.get("reviews", {}).get("nodes", []):
            if review.get("author"):
                reviews.append(
                    {
                        "pr_number": pr.get("number"),
                        "reviewer": review.get("author", {}).get("login"),
                        "submitted_at": review.get("submittedAt"),
                        "state": review.get("state"),
                        "pr_author": pr_author,
                    }
                )
        return reviews

    def _extract_commit_data(self, pr: Dict) -> List[Dict]:
        """Extract commit data from PR"""
        commits = []
        for commit_node in pr.get("commits", {}).get("nodes", []):
            commit = commit_node.get("commit", {})
            author = commit.get("author", {})

            commits.append(
                {
                    "pr_number": pr.get("number"),
                    "sha": commit.get("oid"),
                    "author": author.get("user", {}).get("login") if author.get("user") else author.get("email"),
                    "author_name": author.get("name"),
                    "author_email": author.get("email"),
                    "date": commit.get("committedDate"),
                    "additions": commit.get("additions", 0),
                    "deletions": commit.get("deletions", 0),
                }
            )
        return commits

    def _collect_releases_graphql(self, owner: str, repo_name: str) -> List[Dict]:
        """Collect releases from GitHub GraphQL API

        Collects all releases in the date range and classifies them by environment
        (production vs staging) based on tag naming patterns.

        Args:
            owner: Repository owner
            repo_name: Repository name

        Returns:
            List of release dictionaries with environment classification
        """
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            releases(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                name
                tagName
                createdAt
                publishedAt
                isPrerelease
                isDraft
                author {
                  login
                }
                tagCommit {
                  oid
                  committedDate
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

        releases = []
        cursor = None

        while True:
            try:
                data = self._execute_query(query, {"owner": owner, "name": repo_name, "cursor": cursor})

                if not data.get("repository"):
                    break

                release_data = data["repository"]["releases"]
                nodes = release_data["nodes"]

                releases_in_date_range_on_this_page = 0

                for release in nodes:
                    # Skip draft releases
                    if release.get("isDraft", False):
                        continue

                    # Parse dates
                    published_at = None
                    if release.get("publishedAt"):
                        published_at = datetime.fromisoformat(release["publishedAt"].replace("Z", "+00:00"))

                    created_at = None
                    if release.get("createdAt"):
                        created_at = datetime.fromisoformat(release["createdAt"].replace("Z", "+00:00"))

                    # Use publishedAt for date filtering (when release went public)
                    release_date = published_at or created_at
                    if not release_date or release_date < self.since_date:
                        continue

                    releases_in_date_range_on_this_page += 1

                    # Determine environment based on tag pattern
                    tag_name = release.get("tagName", "")
                    environment = self._classify_release_environment(tag_name, release.get("isPrerelease", False))

                    # Extract commit info
                    commit_sha = None
                    committed_date = None
                    if release.get("tagCommit"):
                        commit_sha = release["tagCommit"].get("oid")
                        if release["tagCommit"].get("committedDate"):
                            committed_date = datetime.fromisoformat(
                                release["tagCommit"]["committedDate"].replace("Z", "+00:00")
                            )

                    # Build release entry
                    release_entry = {
                        "repo": f"{owner}/{repo_name}",
                        "tag_name": tag_name,
                        "release_name": release.get("name", tag_name),
                        "published_at": published_at,
                        "created_at": created_at,
                        "environment": environment,
                        "author": release["author"]["login"] if release.get("author") else "unknown",
                        "commit_sha": commit_sha,
                        "committed_date": committed_date,
                        "is_prerelease": release.get("isPrerelease", False),
                    }

                    releases.append(release_entry)

                # Early termination: if no releases in date range on this page, stop
                if releases_in_date_range_on_this_page == 0:
                    break

                if not release_data["pageInfo"]["hasNextPage"]:
                    break

                cursor = release_data["pageInfo"]["endCursor"]

            except Exception as e:
                self.out.warning(f"Error collecting releases for {owner}/{repo_name}: {e}", indent=2)
                break

        return releases

    def _classify_release_environment(self, tag_name: str, is_prerelease: bool) -> str:
        """Classify release as production or staging based on tag pattern

        Args:
            tag_name: Git tag name (e.g., "v1.2.3", "v1.2.3-rc1")
            is_prerelease: GitHub's prerelease flag

        Returns:
            'production' or 'staging'
        """
        import re

        # If explicitly marked as prerelease, it's staging
        if is_prerelease:
            return "staging"

        # Production pattern: vX.Y.Z (semantic version with no suffix)
        # Examples: v1.2.3, v10.0.0, 1.2.3
        production_pattern = r"^v?\d+\.\d+\.\d+$"

        # Staging patterns: any suffix like -rc, -beta, -alpha, -test
        # Examples: v1.2.3-rc1, v1.2.3-beta, v1.2.3-alpha.1
        staging_patterns = [
            r"-rc\d*",  # Release candidates
            r"-beta",  # Beta releases
            r"-alpha",  # Alpha releases
            r"-test",  # Test releases
            r"-dev",  # Development releases
            r"-preview",  # Preview releases
            r"-snapshot",  # Snapshot releases
        ]

        # Check if it's a clean production release
        if re.match(production_pattern, tag_name):
            return "production"

        # Check if it matches any staging pattern
        for pattern in staging_patterns:
            if re.search(pattern, tag_name, re.IGNORECASE):
                return "staging"

        # Default to staging for non-standard tags
        return "staging"

    def _collect_repository_metrics_batched(self, owner: str, repo_name: str) -> Dict[str, List]:
        """Collect PRs, reviews, commits, AND releases in batched queries

        This combines what was previously 2 separate queries into 1 batched query,
        reducing API calls by 50%.

        Args:
            owner: Repository owner
            repo_name: Repository name

        Returns:
            Dict with 'pull_requests', 'reviews', 'commits', 'releases' lists
        """
        pull_requests = []
        reviews = []
        commits = []
        releases = []

        pr_cursor = None
        release_cursor = None
        pr_done = False
        release_done = False
        page_count = 0
        max_pages = 20  # Safety limit

        while (not pr_done or not release_done) and page_count < max_pages:
            page_count += 1

            # Build batched query
            query = """
            query($owner: String!, $name: String!, $prCursor: String, $releaseCursor: String) {
              repository(owner: $owner, name: $name) {
                pullRequests(first: 50, orderBy: {field: CREATED_AT, direction: DESC}, after: $prCursor) {
                  nodes {
                    number
                    title
                    author { login }
                    createdAt
                    mergedAt
                    closedAt
                    state
                    merged
                    additions
                    deletions
                    changedFiles
                    comments { totalCount }
                    reviews(first: 100) {
                      nodes {
                        author { login }
                        submittedAt
                        state
                      }
                    }
                    reviewRequests(first: 10) { totalCount }
                    commits(first: 250) {
                      totalCount
                      nodes {
                        commit {
                          oid
                          author {
                            user { login }
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
                releases(first: 100, after: $releaseCursor, orderBy: {field: CREATED_AT, direction: DESC}) {
                  nodes {
                    name
                    tagName
                    createdAt
                    publishedAt
                    isPrerelease
                    isDraft
                    author { login }
                    tagCommit {
                      oid
                      committedDate
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

            try:
                data = self._execute_query(
                    query,
                    {
                        "owner": owner,
                        "name": repo_name,
                        "prCursor": pr_cursor if not pr_done else None,
                        "releaseCursor": release_cursor if not release_done else None,
                    },
                )

                repo_data = data.get("repository", {})

                # Process PRs if not done
                if not pr_done and "pullRequests" in repo_data:
                    pr_data = repo_data["pullRequests"]
                    prs_in_page = pr_data.get("nodes", [])

                    # Filter by date and extract PRs/reviews/commits
                    for pr in prs_in_page:
                        if not self._is_pr_in_date_range(pr):
                            pr_done = True
                            break

                        # Extract PR, reviews, commits
                        pull_requests.append(self._extract_pr_data(pr))
                        reviews.extend(self._extract_review_data(pr))
                        commits.extend(self._extract_commit_data(pr))

                    # Check pagination
                    page_info = pr_data.get("pageInfo", {})
                    if not page_info.get("hasNextPage", False) or pr_done:
                        pr_done = True
                    else:
                        pr_cursor = page_info.get("endCursor")

                # Process releases if not done
                if not release_done and "releases" in repo_data:
                    release_data = repo_data["releases"]
                    releases_in_page = release_data.get("nodes", [])

                    # Filter by date and classify environment
                    for release in releases_in_page:
                        if not self._is_release_in_date_range(release):
                            release_done = True
                            break

                        if not release.get("isDraft", False):
                            # Classify environment (same logic as _collect_releases_graphql)
                            tag_name = release.get("tagName", "")
                            name = release.get("name", "")
                            environment = self._classify_release_environment(tag_name, name)

                            releases.append(
                                {
                                    "name": release.get("name"),
                                    "tag": release.get("tagName"),
                                    "created_at": release.get("createdAt"),
                                    "published_at": release.get("publishedAt"),
                                    "is_prerelease": release.get("isPrerelease", False),
                                    "author": release.get("author", {}).get("login") if release.get("author") else None,
                                    "environment": environment,
                                    "commit_sha": (
                                        release.get("tagCommit", {}).get("oid") if release.get("tagCommit") else None
                                    ),
                                    "commit_date": (
                                        release.get("tagCommit", {}).get("committedDate")
                                        if release.get("tagCommit")
                                        else None
                                    ),
                                }
                            )

                    # Check pagination
                    page_info = release_data.get("pageInfo", {})
                    if not page_info.get("hasNextPage", False) or release_done:
                        release_done = True
                    else:
                        release_cursor = page_info.get("endCursor")

            except Exception as e:
                self.out.error(f"Error in batched query: {e}", indent=2)
                break

        return {"pull_requests": pull_requests, "reviews": reviews, "commits": commits, "releases": releases}

    def _collect_repository_metrics(self, owner: str, repo_name: str) -> Dict:
        """Collect PRs, reviews, and commits for a repository using a single GraphQL query"""
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
                data = self._execute_query(query, {"owner": owner, "name": repo_name, "cursor": cursor})

                if not data.get("repository"):
                    break

                pr_data = data["repository"]["pullRequests"]
                prs = pr_data["nodes"]

                prs_in_date_range_on_this_page = 0

                for pr in prs:
                    total_prs_fetched += 1

                    # Skip PRs created before our since_date
                    pr_created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
                    if pr_created < self.since_date:
                        total_prs_filtered_out += 1
                        continue

                    prs_in_date_range_on_this_page += 1

                    pr_author = pr["author"]["login"] if pr["author"] else "unknown"

                    # Calculate cycle time
                    cycle_time_hours = None
                    if pr["mergedAt"]:
                        merged_at = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
                        cycle_time_hours = (merged_at - pr_created).total_seconds() / 3600
                    elif pr["closedAt"]:
                        closed_at = datetime.fromisoformat(pr["closedAt"].replace("Z", "+00:00"))
                        cycle_time_hours = (closed_at - pr_created).total_seconds() / 3600

                    # Calculate time to first review
                    time_to_first_review_hours = None
                    if pr["reviews"]["nodes"]:
                        review_times = [
                            datetime.fromisoformat(r["submittedAt"].replace("Z", "+00:00"))
                            for r in pr["reviews"]["nodes"]
                            if r["submittedAt"]
                        ]
                        if review_times:
                            first_review = min(review_times)
                            time_to_first_review_hours = (first_review - pr_created).total_seconds() / 3600

                    pr_entry = {
                        "repo": f"{owner}/{repo_name}",
                        "pr_number": pr["number"],
                        "title": pr["title"],
                        "author": pr_author,
                        "created_at": pr_created,
                        "merged_at": (
                            datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")) if pr["mergedAt"] else None
                        ),
                        "closed_at": (
                            datetime.fromisoformat(pr["closedAt"].replace("Z", "+00:00")) if pr["closedAt"] else None
                        ),
                        "state": pr["state"].lower(),
                        "merged": pr["merged"],
                        "additions": pr["additions"],
                        "deletions": pr["deletions"],
                        "changed_files": pr["changedFiles"],
                        "comments": pr["comments"]["totalCount"],
                        "review_comments": len(pr["reviews"]["nodes"]),
                        "commits": pr["commits"]["totalCount"],
                        "cycle_time_hours": cycle_time_hours,
                        "time_to_first_review_hours": time_to_first_review_hours,
                    }

                    pull_requests.append(pr_entry)

                    # Extract reviews (filter by submission date to match PR filtering)
                    for review in pr["reviews"]["nodes"]:
                        if review["author"] and review["submittedAt"]:
                            # Apply date filtering to reviews to ensure consistency with PR filtering
                            submitted = datetime.fromisoformat(review["submittedAt"].replace("Z", "+00:00"))
                            if submitted < self.since_date:
                                continue  # Skip reviews outside date range

                            reviews.append(
                                {
                                    "repo": f"{owner}/{repo_name}",
                                    "pr_number": pr["number"],
                                    "reviewer": review["author"]["login"],
                                    "submitted_at": submitted,
                                    "state": review["state"],
                                    "pr_author": pr_author,
                                }
                            )

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

                            commits_data.append(
                                {
                                    "repo": f"{owner}/{repo_name}",
                                    "sha": commit["oid"],
                                    "author": author,
                                    "email": commit["author"]["email"],
                                    "date": (
                                        datetime.fromisoformat(commit["author"]["date"].replace("Z", "+00:00"))
                                        if commit["author"]["date"]
                                        else None
                                    ),
                                    "committed_date": (
                                        datetime.fromisoformat(commit["committedDate"].replace("Z", "+00:00"))
                                        if commit["committedDate"]
                                        else None
                                    ),
                                    "additions": commit["additions"],
                                    "deletions": commit["deletions"],
                                    "pr_number": pr["number"],
                                    "pr_created_at": pr_created,
                                }
                            )

                # Early termination: if no PRs in date range on this page, stop paginating
                if prs_in_date_range_on_this_page == 0:
                    self.out.info(f"No more PRs in date range, stopping pagination at page {page_count + 1}", indent=2)
                    break

                if not pr_data["pageInfo"]["hasNextPage"]:
                    break

                cursor = pr_data["pageInfo"]["endCursor"]
                page_count += 1

            except Exception as e:
                self.out.error(f"Error in pagination: {e}", indent=2)
                break

        # Check if we hit the page limit
        if page_count >= max_pages and pr_data.get("pageInfo", {}).get("hasNextPage"):
            hit_page_limit = True

        # Log stats
        self.out.info(
            f"Fetched {total_prs_fetched} PRs, filtered out {total_prs_filtered_out} (outside date range)", indent=2
        )
        if hit_page_limit:
            self.out.warning(f"WARNING: Hit {max_pages}-page limit. Some PRs may be missing!", indent=2)

        # Deduplicate commits (same commit can be in multiple PRs)
        seen_shas = set()
        unique_commits = []
        for commit in commits_data:
            if commit["sha"] not in seen_shas:
                seen_shas.add(commit["sha"])
                unique_commits.append(commit)

        # NOTE: We now collect commits from PRs instead of default branch
        # This ensures PRs and commits use consistent date filtering (PR creation date)
        # Old method: self._collect_commits_graphql(owner, repo_name) - used default branch

        # Collect releases/deployments for the repository
        releases = self._collect_releases_graphql(owner, repo_name)

        return {"pull_requests": pull_requests, "reviews": reviews, "commits": unique_commits, "releases": releases}

    def collect_team_metrics(
        self,
        team_name: str,
        team_members: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
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
        for pr in data["pull_requests"]:
            pr["team"] = team_name
        for review in data["reviews"]:
            review["team"] = team_name
        for commit in data["commits"]:
            commit["team"] = team_name

        # Restore original settings
        self.team_members = original_members
        self.since_date = original_since
        if hasattr(self, "end_date"):
            delattr(self, "end_date")

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
        if hasattr(self, "end_date"):
            data["pull_requests"] = [pr for pr in data["pull_requests"] if pr["created_at"] <= self.end_date]
            data["reviews"] = [r for r in data["reviews"] if r["submitted_at"] and r["submitted_at"] <= self.end_date]
            data["commits"] = [c for c in data["commits"] if c["date"] <= self.end_date]

        # Restore
        self.team_members = original_members
        self.since_date = original_since
        if hasattr(self, "end_date"):
            delattr(self, "end_date")

        return data

    def get_dataframes(self):
        """Return all metrics as pandas DataFrames"""
        data = self.collect_all_metrics()

        return {
            "pull_requests": pd.DataFrame(data["pull_requests"]),
            "reviews": pd.DataFrame(data["reviews"]),
            "commits": pd.DataFrame(data["commits"]),
            "deployments": pd.DataFrame(data["deployments"]),
            "releases": pd.DataFrame(data["releases"]),
        }

    def close(self):
        """Close the HTTP session and cleanup connections"""
        if hasattr(self, "session"):
            self.session.close()
