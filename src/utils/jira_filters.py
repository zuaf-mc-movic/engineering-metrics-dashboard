from typing import Dict, List, Optional

from jira import JIRA


def list_user_filters(jira_client: JIRA) -> List[Dict]:
    """List all accessible filters with IDs

    Args:
        jira_client: Authenticated JIRA client

    Returns:
        List of dictionaries with filter information
        Example: [{'id': '12345', 'name': 'My Filter', 'jql': '...', 'owner': 'user'}]
    """
    filters = []

    try:
        # Get favourite filters
        favourite_filters = jira_client.favourite_filters()

        for jira_filter in favourite_filters:
            filters.append(
                {
                    "id": jira_filter.id,
                    "name": jira_filter.name,
                    "jql": jira_filter.jql if hasattr(jira_filter, "jql") else "N/A",
                    "owner": jira_filter.owner.displayName if hasattr(jira_filter, "owner") else "N/A",
                    "favourite": True,
                }
            )

    except Exception as e:
        print(f"Error fetching favourite filters: {e}")

    return filters


def search_filters_by_name(jira_client: JIRA, search_term: str) -> List[Dict]:
    """Find filters matching a name pattern

    Args:
        jira_client: Authenticated JIRA client
        search_term: Search string (e.g., "Rescue Native")

    Returns:
        List of matching filters
    """
    all_filters = list_user_filters(jira_client)

    matching_filters = [f for f in all_filters if search_term.lower() in f["name"].lower()]

    return matching_filters


def get_filter_jql(jira_client: JIRA, filter_id: str) -> Optional[str]:
    """Get the JQL query for a specific filter

    Args:
        jira_client: Authenticated JIRA client
        filter_id: Filter ID

    Returns:
        JQL query string or None if not found
    """
    try:
        jira_filter = jira_client.filter(filter_id)
        return jira_filter.jql if hasattr(jira_filter, "jql") else None
    except Exception as e:
        print(f"Error fetching filter {filter_id}: {e}")
        return None


def export_filter_mapping(jira_client: JIRA, search_patterns: List[str]) -> Dict:
    """Export filter name → ID mapping for config

    Args:
        jira_client: Authenticated JIRA client
        search_patterns: List of search terms (e.g., ["Rescue Native", "Rescue WebTC"])

    Returns:
        Dictionary mapping search term to found filters
        Example: {
            'Rescue Native': [{'name': 'Rescue Native Team backlog', 'id': '12345'}, ...],
            'Rescue WebTC': [...]
        }
    """
    results = {}

    for pattern in search_patterns:
        matching = search_filters_by_name(jira_client, pattern)
        results[pattern] = [{"name": f["name"], "id": f["id"], "jql": f["jql"]} for f in matching]

    return results


def print_filters_table(filters: List[Dict]):
    """Print filters in a readable table format

    Args:
        filters: List of filter dictionaries
    """
    if not filters:
        print("No filters found.")
        return

    print(f"\n{'ID':<10} {'Name':<50} {'Owner':<25}")
    print("-" * 85)

    for f in filters:
        filter_id = str(f["id"])
        name = f["name"][:48]  # Truncate long names
        owner = f.get("owner", "N/A")[:23]

        print(f"{filter_id:<10} {name:<50} {owner:<25}")

    print()
