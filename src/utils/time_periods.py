from datetime import datetime, timedelta, timezone
from typing import Tuple, List, Dict
import re


def get_quarter_dates(year: int, quarter: int) -> Tuple[datetime, datetime]:
    """Get start and end dates for a calendar quarter

    Args:
        year: Year (e.g., 2024)
        quarter: Quarter number (1-4)

    Returns:
        Tuple of (start_date, end_date)
    """
    if quarter < 1 or quarter > 4:
        raise ValueError("Quarter must be between 1 and 4")

    quarter_starts = {
        1: (1, 1),
        2: (4, 1),
        3: (7, 1),
        4: (10, 1)
    }

    quarter_ends = {
        1: (3, 31),
        2: (6, 30),
        3: (9, 30),
        4: (12, 31)
    }

    start_month, start_day = quarter_starts[quarter]
    end_month, end_day = quarter_ends[quarter]

    start_date = datetime(year, start_month, start_day, 0, 0, 0)
    end_date = datetime(year, end_month, end_day, 23, 59, 59)

    return start_date, end_date


def get_last_n_days(n: int) -> Tuple[datetime, datetime]:
    """Get date range for last N days

    Args:
        n: Number of days to look back

    Returns:
        Tuple of (start_date, end_date)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=n)
    return start_date, end_date


def get_current_year() -> Tuple[datetime, datetime]:
    """Get current calendar year dates

    Returns:
        Tuple of (start_date, end_date)
    """
    current_year = datetime.now().year
    start_date = datetime(current_year, 1, 1, 0, 0, 0)
    end_date = datetime(current_year, 12, 31, 23, 59, 59)
    return start_date, end_date


def get_previous_year() -> Tuple[datetime, datetime]:
    """Get previous calendar year dates

    Returns:
        Tuple of (start_date, end_date)
    """
    previous_year = datetime.now().year - 1
    start_date = datetime(previous_year, 1, 1, 0, 0, 0)
    end_date = datetime(previous_year, 12, 31, 23, 59, 59)
    return start_date, end_date


def parse_period_param(period: str) -> Tuple[datetime, datetime]:
    """Parse period string like '30d', 'Q1-2024', 'current-year', 'previous-year'

    Args:
        period: Period string to parse

    Returns:
        Tuple of (start_date, end_date)

    Examples:
        '30d' -> last 30 days
        'Q1-2024' -> Q1 of 2024
        'current-year' -> current calendar year
        'previous-year' -> previous calendar year
    """
    period = period.lower().strip()

    # Check for 'Nd' format (e.g., '30d', '90d')
    days_match = re.match(r'^(\d+)d$', period)
    if days_match:
        n = int(days_match.group(1))
        return get_last_n_days(n)

    # Check for 'QX-YYYY' format (e.g., 'Q1-2024')
    quarter_match = re.match(r'^q(\d)-(\d{4})$', period)
    if quarter_match:
        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2))
        return get_quarter_dates(year, quarter)

    # Check for special keywords
    if period == 'current-year':
        return get_current_year()

    if period == 'previous-year':
        return get_previous_year()

    raise ValueError(f"Invalid period format: {period}. "
                     "Expected formats: 'Nd', 'QX-YYYY', 'current-year', 'previous-year'")


def get_current_quarter() -> Tuple[int, int]:
    """Get current quarter and year

    Returns:
        Tuple of (quarter, year)
    """
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    return quarter, now.year


def get_previous_quarter() -> Tuple[int, int]:
    """Get previous quarter and year

    Returns:
        Tuple of (quarter, year)
    """
    now = datetime.now()
    current_quarter = (now.month - 1) // 3 + 1

    if current_quarter == 1:
        return 4, now.year - 1
    else:
        return current_quarter - 1, now.year


def get_period_options(start_year=2025) -> List[Dict[str, str]]:
    """
    Return list of period options for dropdown.

    Args:
        start_year: First year to include in options (default: 2025)

    Returns:
        List of dicts with 'value' and 'label' keys
    """
    current_year = datetime.now().year
    years = range(start_year, current_year + 1)

    options = [
        {'value': '90d', 'label': 'Last 90 Days (Default)'},
        {'value': '180d', 'label': 'Last 180 Days'},
        {'value': '365d', 'label': 'Last 365 Days'},
    ]

    for year in years:
        options.extend([
            {'value': f'H1-{year}', 'label': f'H1 {year} (Jan-Jun)'},
            {'value': f'H2-{year}', 'label': f'H2 {year} (Jul-Dec)'},
            {'value': f'Q1-{year}', 'label': f'Q1 {year} (Jan-Mar)'},
            {'value': f'Q2-{year}', 'label': f'Q2 {year} (Apr-Jun)'},
            {'value': f'Q3-{year}', 'label': f'Q3 {year} (Jul-Sep)'},
            {'value': f'Q4-{year}', 'label': f'Q4 {year} (Oct-Dec)'},
        ])

    return options


def parse_period_to_dates(period_str: str) -> Tuple[datetime, datetime]:
    """
    Convert period string to start_date and end_date with timezone support.

    Args:
        period_str: Period identifier (e.g., '90d', 'Q1-2025', 'H1-2026')

    Returns:
        Tuple of (start_date, end_date) as datetime objects with UTC timezone

    Examples:
        '90d' -> last 90 days
        'Q1-2025' -> Q1 of 2025
        'H1-2025' -> First half of 2025
        'H2-2025' -> Second half of 2025
    """
    period_str = period_str.strip()
    now = datetime.now(timezone.utc)

    # Handle day-based periods (e.g., '90d', '180d')
    days_match = re.match(r'^(\d+)d$', period_str)
    if days_match:
        days = int(days_match.group(1))
        end_date = now
        start_date = end_date - timedelta(days=days)
        return (start_date, end_date)

    # Handle quarter periods (e.g., 'Q1-2025')
    quarter_match = re.match(r'^[Qq](\d)-(\d{4})$', period_str)
    if quarter_match:
        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2))

        if quarter < 1 or quarter > 4:
            raise ValueError(f"Invalid quarter: {quarter}. Must be 1-4")

        quarter_map = {
            1: (1, 1, 3, 31),   # Jan 1 - Mar 31
            2: (4, 1, 6, 30),   # Apr 1 - Jun 30
            3: (7, 1, 9, 30),   # Jul 1 - Sep 30
            4: (10, 1, 12, 31)  # Oct 1 - Dec 31
        }

        start_month, start_day, end_month, end_day = quarter_map[quarter]
        start_date = datetime(year, start_month, start_day, 0, 0, 0, tzinfo=timezone.utc)
        end_date = datetime(year, end_month, end_day, 23, 59, 59, tzinfo=timezone.utc)

        return (start_date, end_date)

    # Handle half-year periods (e.g., 'H1-2025', 'H2-2025')
    half_match = re.match(r'^[Hh]([12])-(\d{4})$', period_str)
    if half_match:
        half = int(half_match.group(1))
        year = int(half_match.group(2))

        if half == 1:
            # January 1 - June 30
            start_date = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
        elif half == 2:
            # July 1 - December 31
            start_date = datetime(year, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        else:
            raise ValueError(f"Invalid half: {half}. Must be 1 or 2")

        return (start_date, end_date)

    raise ValueError(f"Unsupported period format: {period_str}")


def format_period_label(period_str: str) -> str:
    """
    Get a human-readable label for a period string.

    Args:
        period_str: Period identifier

    Returns:
        Human-readable label
    """
    options = get_period_options()
    for option in options:
        if option['value'] == period_str:
            return option['label']

    # Fallback for unknown periods
    return period_str


def get_days_in_period(period_str: str) -> int:
    """
    Calculate the number of days in a period.

    Args:
        period_str: Period identifier

    Returns:
        Number of days as integer
    """
    start_date, end_date = parse_period_to_dates(period_str)
    delta = end_date - start_date
    return delta.days
