"""Date range utilities for flexible time window selection

This module provides utilities for parsing and managing date ranges used in
metrics collection and dashboard filtering. Supports preset ranges (30d, 90d, etc.),
quarters (Q1-2025), and custom date ranges.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


class DateRangeError(Exception):
    """Exception raised for invalid date range specifications"""


class DateRange:
    """Represents a date range with start and end dates

    Attributes:
        start_date: Start of the range (datetime)
        end_date: End of the range (datetime)
        range_key: String identifier for caching (e.g., "90d", "Q1-2025")
        description: Human-readable description
    """

    def __init__(self, start_date: datetime, end_date: datetime, range_key: str, description: str):
        """Initialize a DateRange

        Args:
            start_date: Start datetime (timezone-aware)
            end_date: End datetime (timezone-aware)
            range_key: Cache key identifier
            description: Human-readable description

        Raises:
            DateRangeError: If start_date >= end_date
        """
        if start_date >= end_date:
            raise DateRangeError(f"start_date must be before end_date: {start_date} >= {end_date}")

        self.start_date = start_date
        self.end_date = end_date
        self.range_key = range_key
        self.description = description

    @property
    def days(self) -> int:
        """Return the number of days in this range"""
        return (self.end_date - self.start_date).days

    def __repr__(self) -> str:
        return f"DateRange({self.range_key}: {self.start_date.date()} to {self.end_date.date()})"


def parse_date_range(range_spec: str, reference_date: Optional[datetime] = None) -> DateRange:
    """Parse a date range specification into a DateRange object

    Supported formats:
        - Days: "30d", "90d", "180d", "365d" (days back from reference_date)
        - Quarters: "Q1-2025", "Q2-2024", etc.
        - Years: "2024", "2025" (full calendar year)
        - Custom: "2024-01-01:2024-03-31" (ISO format start:end)

    Args:
        range_spec: String specification of the date range
        reference_date: Reference date for relative ranges (defaults to now)

    Returns:
        DateRange object

    Raises:
        DateRangeError: If range_spec is invalid or unsupported

    Examples:
        >>> parse_date_range("90d")
        DateRange(90d: 2024-10-13 to 2025-01-11)

        >>> parse_date_range("Q1-2025")
        DateRange(Q1-2025: 2025-01-01 to 2025-03-31)

        >>> parse_date_range("2024-01-01:2024-12-31")
        DateRange(custom: 2024-01-01 to 2024-12-31)
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    # Ensure reference_date is timezone-aware
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=timezone.utc)

    range_spec = range_spec.strip()

    # Days format: 30d, 90d, 180d, 365d
    # Check for negative days first
    if re.match(r"^-\d+d$", range_spec, re.IGNORECASE):
        raise DateRangeError("Days must be positive")

    days_match = re.match(r"^(\d+)d$", range_spec, re.IGNORECASE)
    if days_match:
        days = int(days_match.group(1))
        if days <= 0:
            raise DateRangeError(f"Days must be positive: {days}")
        if days > 3650:  # ~10 years maximum
            raise DateRangeError(f"Days too large (max 3650): {days}")

        end_date = reference_date
        start_date = end_date - timedelta(days=days)

        return DateRange(
            start_date=start_date, end_date=end_date, range_key=range_spec.lower(), description=f"Last {days} days"
        )

    # Quarter format: Q1-2025, Q2-2024, etc.
    quarter_match = re.match(r"^Q([1-4])-(\d{4})$", range_spec, re.IGNORECASE)
    if quarter_match:
        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2))

        if not (2000 <= year <= 2100):
            raise DateRangeError(f"Year out of range (2000-2100): {year}")

        # Calculate quarter start and end dates
        quarter_starts = {
            1: (1, 1),  # Q1: Jan 1 - Mar 31
            2: (4, 1),  # Q2: Apr 1 - Jun 30
            3: (7, 1),  # Q3: Jul 1 - Sep 30
            4: (10, 1),  # Q4: Oct 1 - Dec 31
        }
        quarter_ends = {
            1: (3, 31),
            2: (6, 30),
            3: (9, 30),
            4: (12, 31),
        }

        start_month, start_day = quarter_starts[quarter]
        end_month, end_day = quarter_ends[quarter]

        start_date = datetime(year, start_month, start_day, tzinfo=timezone.utc)
        end_date = datetime(year, end_month, end_day, 23, 59, 59, tzinfo=timezone.utc)

        return DateRange(
            start_date=start_date, end_date=end_date, range_key=range_spec.upper(), description=f"Q{quarter} {year}"
        )

    # Full year format: 2024, 2025
    year_match = re.match(r"^(\d{4})$", range_spec)
    if year_match:
        year = int(year_match.group(1))

        if not (2000 <= year <= 2100):
            raise DateRangeError(f"Year out of range (2000-2100): {year}")

        start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        return DateRange(start_date=start_date, end_date=end_date, range_key=str(year), description=f"Year {year}")

    # Custom format: 2024-01-01:2024-12-31
    custom_match = re.match(r"^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$", range_spec)
    if custom_match:
        start_str = custom_match.group(1)
        end_str = custom_match.group(2)

        try:
            start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
            end_date = datetime.fromisoformat(end_str).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except ValueError as e:
            raise DateRangeError(f"Invalid date format: {e}")

        return DateRange(
            start_date=start_date,
            end_date=end_date,
            range_key=f"custom_{start_str}_{end_str}",
            description=f"{start_str} to {end_str}",
        )

    # Invalid format
    raise DateRangeError(
        f"Invalid date range format: '{range_spec}'. " f"Supported: 30d, 90d, Q1-2025, 2024, 2024-01-01:2024-12-31"
    )


def get_preset_ranges() -> list:
    """Return list of commonly used preset ranges

    Returns:
        List of (range_spec, description) tuples
    """
    return [
        ("30d", "Last 30 days"),
        ("60d", "Last 60 days"),
        ("90d", "Last 90 days"),
        ("180d", "Last 180 days"),
        ("365d", "Last 365 days"),
    ]


def get_cache_filename(range_key: str) -> str:
    """Generate cache filename for a given range key with path traversal protection

    Args:
        range_key: Range identifier (e.g., "90d", "Q1-2025")

    Returns:
        Cache filename (e.g., "metrics_cache_90d.pkl")

    Raises:
        ValueError: If range_key contains invalid characters or patterns
    """
    # Security: Check for path traversal attempts
    if ".." in range_key or "/" in range_key or "\\" in range_key:
        raise ValueError(f"Invalid range_key: contains path traversal characters")

    # Validate against allowed patterns
    valid_patterns = [
        r"^\d+d$",  # Days: 30d, 90d, etc.
        r"^Q[1-4]-\d{4}$",  # Quarters: Q1-2025
        r"^\d{4}$",  # Years: 2024
        r"^custom_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$",  # Custom: custom_2024-01-01_2024-12-31
    ]

    if not any(re.match(pattern, range_key) for pattern in valid_patterns):
        raise ValueError(f"Invalid range_key format: {range_key}")

    # Additional safety: limit length
    if len(range_key) > 50:
        raise ValueError(f"range_key too long: {len(range_key)} chars")

    # Sanitize for filesystem (belt and suspenders)
    safe_key = range_key.replace(":", "_").replace("/", "_")
    return f"metrics_cache_{safe_key}.pkl"


def format_date_for_github_graphql(dt: datetime) -> str:
    """Format datetime for GitHub GraphQL API queries

    Args:
        dt: Datetime to format

    Returns:
        ISO 8601 formatted string (e.g., "2024-01-01T00:00:00Z")
    """
    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_date_for_jira_jql(dt: datetime) -> str:
    """Format datetime for Jira JQL queries

    Args:
        dt: Datetime to format

    Returns:
        JQL date format (e.g., "2024-01-01")
    """
    return dt.strftime("%Y-%m-%d")
