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
    def time_periods(self):
        """Get time period configurations"""
        return self.config.get('time_periods', {
            'last_n_days': [7, 14, 30, 60, 90],
            'quarters_enabled': True,
            'custom_range_enabled': True,
            'max_days_back': 365
        })

    @property
    def activity_thresholds(self):
        """Get activity threshold configurations"""
        return self.config.get('activity_thresholds', {
            'minimum_values': {
                'prs_per_month': 5,
                'reviews_per_month': 10,
                'commits_per_month': 20
            },
            'trend_decline_threshold_percent': 20,
            'below_average_threshold_percent': 70
        })
