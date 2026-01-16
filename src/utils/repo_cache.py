"""Repository caching module for GitHub GraphQL collector

Caches team repository lists to avoid redundant GraphQL queries.
Repository lists rarely change, so caching provides 5-15 second speedup
on subsequent collections within the expiration window.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, cast

CACHE_DIR = Path("data/repo_cache")
CACHE_EXPIRATION_HOURS = 24


def _get_cache_key(organization: str, teams: List[str]) -> str:
    """Generate cache key from organization and team slugs

    Args:
        organization: GitHub organization name
        teams: List of team slugs

    Returns:
        Cache key string in format "org:team1,team2,..."
    """
    teams_str = ",".join(sorted(teams))
    return f"{organization}:{teams_str}"


def _get_cache_filename(cache_key: str) -> Path:
    """Generate cache filename from cache key

    Args:
        cache_key: Cache key string

    Returns:
        Path to cache file
    """
    key_hash = hashlib.md5(cache_key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{key_hash}.json"


def get_cached_repositories(organization: str, teams: List[str]) -> Optional[List[str]]:
    """Retrieve cached repository list if valid

    Args:
        organization: GitHub organization name
        teams: List of team slugs

    Returns:
        List of repository names if cache is valid, None otherwise
    """
    if not organization or not teams:
        return None

    cache_key = _get_cache_key(organization, teams)
    cache_file = _get_cache_filename(cache_key)

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r") as f:
            cache_data = json.load(f)

        # Check expiration
        cached_time = datetime.fromisoformat(cache_data["timestamp"])
        age = datetime.now() - cached_time

        if age > timedelta(hours=CACHE_EXPIRATION_HOURS):
            print(f"  📦 Repository cache expired (age: {age.total_seconds()/3600:.1f}h)")
            return None

        print(f"  ✅ Using cached repositories (age: {age.total_seconds()/3600:.1f}h)")
        return cast(List[str], cache_data["repositories"])

    except Exception as e:
        print(f"  ⚠️  Cache read error: {e}")
        return None


def save_cached_repositories(organization: str, teams: List[str], repositories: List[str]):
    """Save repository list to cache

    Args:
        organization: GitHub organization name
        teams: List of team slugs
        repositories: List of repository names
    """
    if not organization or not teams or not repositories:
        return

    try:
        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        cache_key = _get_cache_key(organization, teams)
        cache_file = _get_cache_filename(cache_key)

        cache_data = {
            "cache_key": cache_key,
            "organization": organization,
            "teams": teams,
            "repositories": repositories,
            "timestamp": datetime.now().isoformat(),
            "count": len(repositories),
        }

        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)

        print(f"  💾 Cached {len(repositories)} repositories")

    except Exception as e:
        print(f"  ⚠️  Cache write error: {e}")


def clear_cache():
    """Clear all repository caches"""
    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            cache_file.unlink()
        print(f"✅ Cleared repository cache")
