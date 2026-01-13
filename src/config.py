import yaml
import os
from pathlib import Path


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

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    @property
    def github_token(self):
        return self.config.get('github', {}).get('token')

    @property
    def github_repositories(self):
        return self.config.get('github', {}).get('repositories', [])

    @property
    def github_organization(self):
        return self.config.get('github', {}).get('organization')

    @property
    def github_base_url(self):
        return f"https://github.com/{self.github_organization}"

    @property
    def github_teams(self):
        return self.config.get('github', {}).get('teams', [])

    @property
    def github_team_members(self):
        return self.config.get('github', {}).get('team_member_usernames', [])

    @property
    def days_back(self):
        return self.config.get('github', {}).get('days_back', 90)

    @property
    def jira_config(self):
        return self.config.get('jira', {})

    @property
    def team_members(self):
        return self.config.get('team_members', [])

    @property
    def jira_team_members(self):
        """Get list of Jira usernames from team member mapping"""
        team_members = self.config.get('team_members', [])
        return [member.get('jira') for member in team_members if member.get('jira')]

    @property
    def dashboard_config(self):
        return self.config.get('dashboard', {
            'port': 5000,
            'debug': True,
            'cache_duration_minutes': 60
        })

    @property
    def teams(self):
        """Get list of team configurations"""
        return self.config.get('teams', [])

    def get_team_by_name(self, name):
        """Get team configuration by name"""
        for team in self.teams:
            if team.get('name', '').lower() == name.lower():
                return team
        return None

    @property
    def performance_weights(self):
        """Get performance score weights from config with validation

        Returns:
            dict: Weight values for each metric (keys: prs, reviews, commits,
                  cycle_time, jira_completed, merge_rate)

        Raises:
            ValueError: If weights don't sum to 1.0 (within tolerance)
        """
        # Default weights if not configured
        default_weights = {
            'prs': 0.20,
            'reviews': 0.20,
            'commits': 0.15,
            'cycle_time': 0.15,
            'jira_completed': 0.20,
            'merge_rate': 0.10
        }

        weights = self.config.get('performance_weights', default_weights)

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
        self.config['performance_weights'] = weights

        # Write to file
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

