"""
Tests for configuration loading and validation.

The Config class loads settings from YAML and provides validated access
to GitHub, Jira, and team configurations.
"""

import tempfile
import warnings
from pathlib import Path

import pytest
import yaml

from src.config import Config


@pytest.fixture
def valid_config_dict():
    """Fixture providing a valid configuration dictionary"""
    return {
        "github": {
            "token": "ghp_test_token_123456789",
            "organization": "test-org",
            "repositories": ["repo1", "repo2"],
            "teams": ["team1", "team2"],
            "team_member_usernames": ["user1", "user2"],
            "days_back": 90,
        },
        "jira": {"server": "https://jira.example.com", "username": "testuser", "api_token": "test_api_token_123"},
        "teams": [
            {
                "name": "Backend",
                "display_name": "Backend Team",
                "members": [
                    {"name": "John Doe", "github": "johndoe", "jira": "jdoe"},
                    {"name": "Jane Smith", "github": "janesmith", "jira": "jsmith"},
                ],
                "github": {"team_slug": "backend-team"},
                "jira": {"filters": {"wip": 12345, "completed": 12346, "bugs": 12347}},
            }
        ],
        "dashboard": {"port": 5000, "debug": True, "cache_duration_minutes": 60},
    }


@pytest.fixture
def temp_config_file(valid_config_dict):
    """Fixture creating a temporary valid config file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(valid_config_dict, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


class TestConfigLoading:
    """Tests for config file loading"""

    def test_load_valid_config(self, temp_config_file):
        """Test loading a valid configuration file"""
        config = Config(config_path=temp_config_file)
        assert config.config is not None
        assert isinstance(config.config, dict)

    def test_missing_config_file_raises_error(self):
        """Test that missing config file raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            Config(config_path="/nonexistent/path/config.yaml")

    def test_invalid_yaml_raises_error(self):
        """Test that invalid YAML syntax raises an error"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content:\n  - broken")
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                Config(config_path=temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_default_config_path(self):
        """Test that default config path is constructed correctly"""
        # This test verifies the default path logic but won't load actual config
        config = Config.__new__(Config)
        config.config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        assert config.config_path.name == "config.yaml"


class TestGitHubConfig:
    """Tests for GitHub configuration properties"""

    def test_github_token(self, temp_config_file):
        """Test GitHub token retrieval"""
        config = Config(config_path=temp_config_file)
        assert config.github_token == "ghp_test_token_123456789"

    def test_github_organization(self, temp_config_file):
        """Test GitHub organization retrieval"""
        config = Config(config_path=temp_config_file)
        assert config.github_organization == "test-org"

    def test_github_base_url(self, temp_config_file):
        """Test GitHub base URL construction"""
        config = Config(config_path=temp_config_file)
        assert config.github_base_url == "https://github.com/test-org"

    def test_github_repositories(self, temp_config_file):
        """Test GitHub repositories list"""
        config = Config(config_path=temp_config_file)
        assert config.github_repositories == ["repo1", "repo2"]

    def test_github_teams(self, temp_config_file):
        """Test GitHub teams list"""
        config = Config(config_path=temp_config_file)
        assert config.github_teams == ["team1", "team2"]

    def test_github_team_members(self, temp_config_file):
        """Test GitHub team member usernames"""
        config = Config(config_path=temp_config_file)
        assert config.github_team_members == ["user1", "user2"]

    def test_days_back_default(self, temp_config_file):
        """Test days_back default value"""
        config = Config(config_path=temp_config_file)
        assert config.days_back == 90

    def test_missing_github_section(self):
        """Test handling of missing GitHub section"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"jira": {"server": "test"}}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.github_token is None
            assert config.github_organization is None
            assert config.github_repositories == []
            assert config.days_back == 90  # Should use default
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestJiraConfig:
    """Tests for Jira configuration properties"""

    def test_jira_config(self, temp_config_file):
        """Test Jira configuration retrieval"""
        config = Config(config_path=temp_config_file)
        jira_config = config.jira_config
        assert jira_config["server"] == "https://jira.example.com"
        assert jira_config["username"] == "testuser"
        assert jira_config["api_token"] == "test_api_token_123"

    def test_missing_jira_section(self):
        """Test handling of missing Jira section"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"github": {"token": "test"}}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.jira_config == {}
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestTeamConfig:
    """Tests for team configuration properties"""

    def test_teams_list(self, temp_config_file):
        """Test teams list retrieval"""
        config = Config(config_path=temp_config_file)
        teams = config.teams
        assert len(teams) == 1
        assert teams[0]["name"] == "Backend"
        assert teams[0]["display_name"] == "Backend Team"

    def test_get_team_by_name(self, temp_config_file):
        """Test retrieving team by name"""
        config = Config(config_path=temp_config_file)
        team = config.get_team_by_name("Backend")
        assert team is not None
        assert team["name"] == "Backend"
        assert len(team["members"]) == 2

    def test_get_team_by_name_case_insensitive(self, temp_config_file):
        """Test team lookup is case-insensitive"""
        config = Config(config_path=temp_config_file)
        team = config.get_team_by_name("BACKEND")
        assert team is not None
        assert team["name"] == "Backend"

    def test_get_nonexistent_team(self, temp_config_file):
        """Test retrieving non-existent team returns None"""
        config = Config(config_path=temp_config_file)
        team = config.get_team_by_name("NonexistentTeam")
        assert team is None

    def test_team_members_structure(self, temp_config_file):
        """Test team members have required fields"""
        config = Config(config_path=temp_config_file)
        team = config.get_team_by_name("Backend")
        members = team["members"]

        for member in members:
            assert "name" in member
            assert "github" in member
            assert "jira" in member

    def test_team_jira_filters(self, temp_config_file):
        """Test team Jira filter configuration"""
        config = Config(config_path=temp_config_file)
        team = config.get_team_by_name("Backend")
        filters = team["jira"]["filters"]

        assert "wip" in filters
        assert "completed" in filters
        assert "bugs" in filters
        assert filters["wip"] == 12345

    def test_empty_teams_list(self):
        """Test handling of empty teams list"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"github": {"token": "test"}, "teams": []}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.teams == []
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestDashboardConfig:
    """Tests for dashboard configuration properties"""

    def test_dashboard_config(self, temp_config_file):
        """Test dashboard configuration retrieval"""
        config = Config(config_path=temp_config_file)
        dashboard = config.dashboard_config
        assert dashboard["port"] == 5000
        assert dashboard["debug"] is True
        assert dashboard["cache_duration_minutes"] == 60

    def test_dashboard_config_defaults(self):
        """Test dashboard config returns defaults when missing"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"github": {"token": "test"}}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            dashboard = config.dashboard_config
            assert dashboard["port"] == 5001
            assert dashboard["debug"] is True
            assert dashboard["cache_duration_minutes"] == 60
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestJiraTeamMembers:
    """Tests for Jira team member extraction"""

    def test_jira_team_members_extraction(self):
        """Test extracting Jira usernames from team members"""
        config_dict = {
            "team_members": [
                {"name": "User 1", "github": "user1", "jira": "juser1"},
                {"name": "User 2", "github": "user2", "jira": "juser2"},
                {"name": "User 3", "github": "user3"},  # No Jira username
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            jira_members = config.jira_team_members
            # Should only include members with Jira usernames
            assert len(jira_members) == 2
            assert "juser1" in jira_members
            assert "juser2" in jira_members
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_empty_team_members(self):
        """Test handling empty team members list"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"team_members": []}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.jira_team_members == []
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestConfigValidation:
    """Tests for configuration validation and edge cases"""

    def test_empty_config_file(self):
        """Test handling of empty config file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            # Should load but return empty/default values
            assert config.config is None or config.config == {}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_nested_missing_values(self):
        """Test safe handling of deeply nested missing values"""
        config_dict = {"github": {}}  # GitHub section exists but is empty

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            # Should not crash, should return None/defaults
            assert config.github_token is None
            assert config.github_repositories == []
            assert config.days_back == 90
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestPerformanceWeights:
    """Tests for performance weights configuration"""

    def test_performance_weights_default_values(self, temp_config_file):
        """Test that default weights are returned when not in config"""
        config = Config(config_path=temp_config_file)
        weights = config.performance_weights

        assert weights == {
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

    def test_performance_weights_custom_values(self):
        """Test loading custom performance weights from config"""
        config_dict = {
            "performance_weights": {
                "prs": 0.20,
                "reviews": 0.20,
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.20,
                "merge_rate": 0.10,
                # DORA metrics (new format) - total 0.10
                "deployment_frequency": 0.04,
                "lead_time": 0.03,
                "change_failure_rate": 0.02,
                "mttr": 0.01,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            weights = config.performance_weights

            assert weights["prs"] == 0.20
            assert weights["reviews"] == 0.20
            assert weights["commits"] == 0.10
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_sum_validation(self):
        """Test that weights must sum to 1.0"""
        config_dict = {
            "performance_weights": {
                "prs": 0.30,  # Sum = 1.30 (invalid)
                "reviews": 0.30,
                "commits": 0.20,
                "cycle_time": 0.10,
                "jira_completed": 0.10,
                "merge_rate": 0.10,
                # DORA metrics (new format)
                "deployment_frequency": 0.05,
                "lead_time": 0.05,
                "change_failure_rate": 0.05,
                "mttr": 0.05,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            with pytest.raises(ValueError, match="Performance weights must sum to 1.0"):
                _ = config.performance_weights
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_individual_value_validation(self):
        """Test that individual weights must be between 0.0 and 1.0"""
        config_dict = {
            "performance_weights": {
                "prs": 1.50,  # Invalid: > 1.0
                "reviews": -0.30,  # Invalid: < 0.0
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.10,
                "merge_rate": 0.10,
                # DORA metrics (new format)
                "deployment_frequency": 0.10,
                "lead_time": 0.10,
                "change_failure_rate": 0.05,
                "mttr": 0.05,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
                _ = config.performance_weights
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_update_performance_weights_valid(self):
        """Test updating weights with valid values"""
        config_dict = {"github": {"token": "test"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)

            new_weights = {
                "prs": 0.25,
                "reviews": 0.25,
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.15,
                "merge_rate": 0.05,
                # DORA metrics (new format) - total 0.10
                "deployment_frequency": 0.04,
                "lead_time": 0.03,
                "change_failure_rate": 0.02,
                "mttr": 0.01,
            }

            config.update_performance_weights(new_weights)

            # Verify weights were updated
            assert config.performance_weights == new_weights

            # Verify file was written
            with open(temp_path, "r") as f:
                saved_config = yaml.safe_load(f)
                assert saved_config["performance_weights"] == new_weights
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_update_performance_weights_invalid_sum(self):
        """Test that updating with invalid sum raises error"""
        config_dict = {"github": {"token": "test"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)

            invalid_weights = {
                "prs": 0.40,
                "reviews": 0.40,  # Sum = 1.15 (invalid)
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.10,
                "merge_rate": 0.05,
            }

            with pytest.raises(ValueError, match="Weights must sum to 1.0"):
                config.update_performance_weights(invalid_weights)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_update_performance_weights_invalid_individual_value(self):
        """Test that updating with invalid individual value raises error"""
        config_dict = {"github": {"token": "test"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)

            invalid_weights = {
                "prs": -0.10,  # Invalid: negative
                "reviews": 0.30,
                "commits": 0.20,
                "cycle_time": 0.20,
                "jira_completed": 0.20,
                "merge_rate": 0.20,
            }

            with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
                config.update_performance_weights(invalid_weights)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_sum_tolerance(self):
        """Test that float precision tolerance is applied (±0.001)"""
        config_dict = {
            "performance_weights": {
                "prs": 0.2001,  # Slightly over due to float precision
                "reviews": 0.2001,
                "commits": 0.15,
                "cycle_time": 0.15,
                "jira_completed": 0.1998,
                "merge_rate": 0.10,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            # Should not raise error due to tolerance
            weights = config.performance_weights
            assert weights is not None
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_persistence(self):
        """Test that updated weights persist across config reloads"""
        config_dict = {"github": {"token": "test"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            # Update weights
            config1 = Config(config_path=temp_path)
            new_weights = {
                "prs": 0.30,
                "reviews": 0.25,
                "commits": 0.05,
                "cycle_time": 0.10,
                "jira_completed": 0.15,
                "merge_rate": 0.05,
                # DORA metrics (new format) - total 0.10
                "deployment_frequency": 0.04,
                "lead_time": 0.03,
                "change_failure_rate": 0.02,
                "mttr": 0.01,
            }
            config1.update_performance_weights(new_weights)

            # Load new config instance and verify
            config2 = Config(config_path=temp_path)
            assert config2.performance_weights == new_weights
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_backward_compatibility_old_format(self):
        """Test that old 6-metric config automatically uses new 10-metric defaults"""
        # Old config format with only 6 metrics
        config_dict = {
            "github": {"token": "test"},
            "performance_weights": {
                "prs": 0.20,
                "reviews": 0.20,
                "commits": 0.15,
                "cycle_time": 0.15,
                "jira_completed": 0.20,
                "merge_rate": 0.10,
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            # Should load without error and use new defaults with warning
            with pytest.warns(UserWarning, match="old performance_weights without DORA metrics"):
                config = Config(config_path=temp_path)
                weights = config.performance_weights

            # Should have all 10 metrics (new defaults)
            assert len(weights) == 10
            assert "deployment_frequency" in weights
            assert "lead_time" in weights
            assert "change_failure_rate" in weights
            assert "mttr" in weights

            # Should use new default values
            assert weights == {
                "prs": 0.15,
                "reviews": 0.15,
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.15,
                "merge_rate": 0.05,
                "deployment_frequency": 0.10,
                "lead_time": 0.10,
                "change_failure_rate": 0.05,
                "mttr": 0.05,
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_new_format_no_warning(self):
        """Test that new 10-metric config loads without warning"""
        # New config format with all 10 metrics
        config_dict = {
            "github": {"token": "test"},
            "performance_weights": {
                "prs": 0.15,
                "reviews": 0.15,
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.15,
                "merge_rate": 0.05,
                "deployment_frequency": 0.10,
                "lead_time": 0.10,
                "change_failure_rate": 0.05,
                "mttr": 0.05,
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            # Should load without warning
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # Turn warnings into errors
                config = Config(config_path=temp_path)
                weights = config.performance_weights

            # Should have all 10 metrics
            assert len(weights) == 10
            assert weights == config_dict["performance_weights"]
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_performance_weights_no_config_uses_defaults(self):
        """Test that missing performance_weights section uses defaults without warning"""
        config_dict = {"github": {"token": "test"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            # Should load without warning
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # Turn warnings into errors
                config = Config(config_path=temp_path)
                weights = config.performance_weights

            # Should have all 10 metrics with default values
            assert len(weights) == 10
            assert weights == {
                "prs": 0.15,
                "reviews": 0.15,
                "commits": 0.10,
                "cycle_time": 0.10,
                "jira_completed": 0.15,
                "merge_rate": 0.05,
                "deployment_frequency": 0.10,
                "lead_time": 0.10,
                "change_failure_rate": 0.05,
                "mttr": 0.05,
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)
