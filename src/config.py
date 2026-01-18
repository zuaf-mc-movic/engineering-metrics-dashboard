from pathlib import Path

import yaml


class Config:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"

        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self):
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found at {self.config_path}. "
                f"Please copy config.example.yaml to config.yaml and update with your settings."
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @property
    def github_token(self):
        return self.config.get("github", {}).get("token")

    @property
    def github_repositories(self):
        return self.config.get("github", {}).get("repositories", [])

    @property
    def github_organization(self):
        return self.config.get("github", {}).get("organization")

    @property
    def github_base_url(self):
        return f"https://github.com/{self.github_organization}"

    @property
    def github_teams(self):
        return self.config.get("github", {}).get("teams", [])

    @property
    def github_team_members(self):
        return self.config.get("github", {}).get("team_member_usernames", [])

    @property
    def days_back(self):
        return self.config.get("github", {}).get("days_back", 90)

    @property
    def jira_config(self):
        return self.config.get("jira", {})

    @property
    def team_members(self):
        return self.config.get("team_members", [])

    @property
    def jira_team_members(self):
        """Get list of Jira usernames from team member mapping"""
        team_members = self.config.get("team_members", [])
        return [member.get("jira") for member in team_members if member.get("jira")]

    @property
    def dashboard_config(self):
        return self.config.get(
            "dashboard", {"port": 5001, "debug": True, "cache_duration_minutes": 60, "jira_timeout_seconds": 120}
        )

    @property
    def teams(self):
        """Get list of team configurations"""
        return self.config.get("teams", [])

    def get_team_by_name(self, name):
        """Get team configuration by name"""
        for team in self.teams:
            if team.get("name", "").lower() == name.lower():
                return team
        return None

    @property
    def performance_weights(self):
        """Get performance score weights from config with validation

        Returns:
            dict: Weight values for each metric (keys: prs, reviews, commits,
                  cycle_time, jira_completed, merge_rate, deployment_frequency,
                  lead_time, change_failure_rate, mttr)

        Raises:
            ValueError: If weights don't sum to 1.0 (within tolerance)
        """
        # Default weights if not configured (including DORA metrics)
        default_weights = {
            "prs": 0.15,
            "reviews": 0.15,
            "commits": 0.10,
            "cycle_time": 0.10,
            "jira_completed": 0.15,
            "merge_rate": 0.05,
            # DORA metrics
            "deployment_frequency": 0.10,
            "lead_time": 0.10,
            "change_failure_rate": 0.05,
            "mttr": 0.05,
        }

        # Get weights from config, or use defaults
        config_weights = self.config.get("performance_weights", {})

        # Check if config has old weights (missing DORA metrics)
        dora_metrics = ["deployment_frequency", "lead_time", "change_failure_rate", "mttr"]
        has_dora = all(metric in config_weights for metric in dora_metrics)

        if config_weights and not has_dora:
            # Old config detected - use new defaults instead
            # User should update their config or remove performance_weights section
            import warnings

            warnings.warn(
                "Config has old performance_weights without DORA metrics. "
                "Using new defaults. Please update config.yaml or remove performance_weights section.",
                UserWarning,
            )
            weights = default_weights
        elif config_weights:
            # Config has all metrics including DORA
            weights = config_weights
        else:
            # No custom weights in config
            weights = default_weights

        # Validate individual weights are in valid range (check this first)
        for metric, weight in weights.items():
            if not (0.0 <= weight <= 1.0):
                raise ValueError(f"Weight for {metric} must be between 0.0 and 1.0, got {weight}")

        # Validate weights sum to 1.0 (with tolerance for float precision)
        total = sum(weights.values())
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"Performance weights must sum to 1.0, got {total}")

        return weights

    def update_performance_weights(self, weights):
        """Update performance weights in config file

        Args:
            weights (dict): New weight values for each metric

        Raises:
            ValueError: If weights are invalid (don't sum to 1.0 or out of range)
        """
        # Validate individual weights (check this first)
        for metric, weight in weights.items():
            if not (0.0 <= weight <= 1.0):
                raise ValueError(f"Weight for {metric} must be between 0.0 and 1.0, got {weight}")

        # Validate sum
        total = sum(weights.values())
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        # Update in-memory config
        self.config["performance_weights"] = weights

        # Write to file
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

    @property
    def parallel_config(self):
        """Get parallel collection configuration

        Returns:
            dict: Configuration for parallel collection with keys:
                  - enabled: bool (default True)
                  - person_workers: int (default 8)
                  - team_workers: int (default 3)
                  - repo_workers: int (default 5)
                  - filter_workers: int (default 4)
        """
        default_config = {
            "enabled": True,
            "person_workers": 8,
            "team_workers": 3,
            "repo_workers": 5,
            "filter_workers": 4,
        }

        config_parallel = self.config.get("parallel_collection", {})

        # Merge with defaults
        return {
            "enabled": config_parallel.get("enabled", default_config["enabled"]),
            "person_workers": config_parallel.get("person_workers", default_config["person_workers"]),
            "team_workers": config_parallel.get("team_workers", default_config["team_workers"]),
            "repo_workers": config_parallel.get("repo_workers", default_config["repo_workers"]),
            "filter_workers": config_parallel.get("filter_workers", default_config["filter_workers"]),
        }

    @property
    def dora_config(self):
        """Get DORA metrics configuration

        Returns:
            dict: Configuration for DORA metrics with keys:
                  - max_lead_time_days: int (default 180)
                  - cfr_correlation_window_hours: int (default 24)
        """
        default_config = {
            "max_lead_time_days": 180,
            "cfr_correlation_window_hours": 24,
        }

        config_dora = self.config.get("dora_metrics", {})

        # Merge with defaults
        return {
            "max_lead_time_days": config_dora.get("max_lead_time_days", default_config["max_lead_time_days"]),
            "cfr_correlation_window_hours": config_dora.get(
                "cfr_correlation_window_hours", default_config["cfr_correlation_window_hours"]
            ),
        }
