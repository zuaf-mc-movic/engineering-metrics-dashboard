"""
Logging configuration loader and setup.

This module handles loading logging configuration from YAML files
and setting up the logging system.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, cast

import yaml

from .console import ConsoleOutput
from .formatters import JSONFormatter
from .handlers import create_rotating_handler

# Module-level cache for logger instances
_loggers: Dict[str, ConsoleOutput] = {}


def load_config(config_file: Optional[str] = None) -> Dict:
    """
    Load logging configuration from YAML file.

    Args:
        config_file: Path to YAML config file (default: config/logging.yaml)

    Returns:
        Dictionary containing logging configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    if config_file is None:
        # Default to config/logging.yaml
        config_file = "config/logging.yaml"

    config_path = Path(config_file)

    if not config_path.exists():
        raise FileNotFoundError(f"Logging config file not found: {config_file}")

    with open(config_path, "r") as f:
        config = cast(Dict[Any, Any], yaml.safe_load(f))

    return config


def setup_logging(
    log_level: str = "INFO", log_file: Optional[str] = None, config_file: Optional[str] = None
) -> logging.Logger:
    """
    Setup logging infrastructure.

    This function initializes the logging system with:
    - Rotating file handlers with compression
    - JSON formatting for file logs
    - Console output wrapper for interactive mode
    - Configuration from YAML file

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional override for main log file path
        config_file: Optional path to logging config YAML

    Returns:
        Root logger instance

    Example:
        >>> logger = setup_logging(log_level='INFO')
        >>> out = get_logger('team_metrics.collection')
        >>> out.info("Starting collection", emoji="📊")
    """
    # Load configuration
    try:
        config = load_config(config_file)
    except FileNotFoundError:
        # Use default configuration if file not found
        config = _get_default_config()

    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Get root logger
    root_logger = logging.getLogger("team_metrics")
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create log directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Setup main log file
    main_log_file = log_file or config.get("files", {}).get("main", "logs/team_metrics.log")
    main_handler = create_rotating_handler(
        log_file=main_log_file,
        max_bytes=config.get("rotation", {}).get("max_bytes", 10485760),
        backup_count=config.get("rotation", {}).get("backup_count", 10),
        compress=config.get("rotation", {}).get("compress", True),
        formatter=JSONFormatter(),
    )
    main_handler.setLevel(numeric_level)
    root_logger.addHandler(main_handler)

    # Setup error log file (warnings and errors only)
    error_log_file = config.get("files", {}).get("error", "logs/team_metrics_error.log")
    error_handler = create_rotating_handler(
        log_file=error_log_file,
        max_bytes=config.get("rotation", {}).get("max_bytes", 10485760),
        backup_count=config.get("rotation", {}).get("backup_count", 10),
        compress=config.get("rotation", {}).get("compress", True),
        formatter=JSONFormatter(),
    )
    error_handler.setLevel(logging.WARNING)
    root_logger.addHandler(error_handler)

    # Configure child loggers from config
    for logger_name, logger_config in config.get("loggers", {}).items():
        child_logger = logging.getLogger(logger_name)
        child_level = logger_config.get("level", log_level.upper())
        child_logger.setLevel(getattr(logging, child_level, logging.INFO))

    return root_logger


def get_logger(name: str) -> ConsoleOutput:
    """
    Get a ConsoleOutput logger instance.

    This function returns a cached ConsoleOutput wrapper for the given logger name.
    The wrapper provides both console output (with emojis) and file logging.

    Args:
        name: Logger name (e.g., 'team_metrics.collection')

    Returns:
        ConsoleOutput instance wrapping the named logger

    Example:
        >>> out = get_logger('team_metrics.collectors.github')
        >>> out.info("Fetching repositories", emoji="🔍")
        >>> out.progress(5, 10, "goto-itsg/repo1", status_emoji="✓")
    """
    if name not in _loggers:
        logger = logging.getLogger(name)
        _loggers[name] = ConsoleOutput(logger)

    return _loggers[name]


def _get_default_config() -> Dict:
    """
    Get default logging configuration.

    Returns:
        Dictionary containing default configuration
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "default_level": "INFO",
        "rotation": {"max_bytes": 10485760, "backup_count": 10, "compress": True},  # 10MB
        "files": {"main": "logs/team_metrics.log", "error": "logs/team_metrics_error.log"},
        "loggers": {
            "team_metrics.collectors.github": {"level": "INFO"},
            "team_metrics.collectors.jira": {"level": "INFO"},
            "team_metrics.collection": {"level": "INFO"},
            "team_metrics.dashboard": {"level": "INFO"},
        },
    }
