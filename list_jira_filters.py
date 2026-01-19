#!/usr/bin/env python3
"""
CLI tool to discover Jira filter IDs

Usage:
    python list_jira_filters.py                    # List all favourite filters
    python list_jira_filters.py "Rescue Native"   # Search for filters matching pattern
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from jira import JIRA

from src.config import Config
from src.utils.jira_filters import export_filter_mapping, list_user_filters, print_filters_table, search_filters_by_name


def main():
    # Load configuration
    try:
        config = Config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease create config/config.yaml from config/config.example.yaml")
        sys.exit(1)

    jira_config = config.jira_config

    if not jira_config.get("server"):
        print("Error: Jira not configured in config.yaml")
        print("Please add Jira server, email, and API token to your config.")
        sys.exit(1)

    # Connect to Jira
    print(f"Connecting to Jira at {jira_config['server']}...")
    try:
        # Support both 'email' and 'username' keys for backwards compatibility
        username = jira_config.get("email") or jira_config.get("username")
        jira_client = JIRA(server=jira_config["server"], basic_auth=(username, jira_config["api_token"]))
        print("Connected successfully!\n")
    except Exception as e:
        print(f"Error connecting to Jira: {e}")
        sys.exit(1)

    # Check if search term provided
    if len(sys.argv) > 1:
        search_term = sys.argv[1]
        print(f"Searching for filters matching '{search_term}'...\n")
        filters = search_filters_by_name(jira_client, search_term)

        if filters:
            print_filters_table(filters)
            print(f"\nFound {len(filters)} matching filter(s)")
        else:
            print(f"No filters found matching '{search_term}'")
            print("\nTry searching without the pattern to see all available filters:")
            print("  python list_jira_filters.py")

    else:
        # List all favourite filters
        print("Listing all your favourite filters...\n")
        filters = list_user_filters(jira_client)

        if filters:
            print_filters_table(filters)
            print(f"\nTotal: {len(filters)} filter(s)")

            print("\nUsage:")
            print('  - To search for specific filters: python list_jira_filters.py "search term"')
            print("  - Copy the filter IDs to your config.yaml under teams[].jira.filters")
        else:
            print("No favourite filters found.")
            print("\nYou can:")
            print("  1. Mark filters as favourites in Jira UI")
            print("  2. Use filter IDs directly if you know them")

    # If teams are configured, show suggestions
    teams = config.teams
    if teams and len(sys.argv) == 1:
        print("\n" + "=" * 85)
        print("TEAM FILTER SUGGESTIONS")
        print("=" * 85)

        for team in teams:
            team_name = team.get("display_name", team.get("name"))
            print(f"\nSearching for '{team_name}' filters...")

            # Try different search patterns
            search_patterns = [team.get("name"), team.get("display_name"), f"Rescue {team.get('name')}"]

            found_any = False
            for pattern in search_patterns:
                if pattern:
                    matching = search_filters_by_name(jira_client, pattern)
                    if matching:
                        print(f"\n  Filters matching '{pattern}':")
                        for f in matching:
                            print(f"    - {f['name']} (ID: {f['id']})")
                        found_any = True

            if not found_any:
                print(f'  No filters found. Try: python list_jira_filters.py "{team_name}"')


if __name__ == "__main__":
    main()
