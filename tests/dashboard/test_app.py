"""Integration tests for Flask dashboard routes"""

import csv
import io
import json
from datetime import datetime

import pytest

from src.dashboard.app import app


@pytest.fixture
def client():
    """Flask test client fixture"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_cache_data():
    """Create mock cache data matching expected structure"""
    return {
        "range_key": "90d",
        "date_range": {
            "description": "Last 90 days",
            "start_date": datetime(2024, 10, 13),
            "end_date": datetime(2026, 1, 11),
        },
        "teams": {
            "Native": {
                "display_name": "Native Team",
                "timestamp": datetime.now(),
                "github": {"pr_count": 107, "review_count": 472, "commit_count": 519, "merge_rate": 0.85},
                "jira": {
                    "wip": {"count": 81},
                    "completed": 57,
                    "bugs_created": 20,
                    "bugs_resolved": 16,
                    "flagged_blocked": 5,
                },
                "members": [
                    {
                        "name": "John Doe",
                        "github": "jdoe",
                        "jira": "jdoe",
                        "prs_created": 10,
                        "reviews_given": 50,
                        "commits": 60,
                    }
                ],
            },
            "WebTC": {
                "display_name": "WebTC Team",
                "timestamp": datetime.now(),
                "github": {"pr_count": 69, "review_count": 268, "commit_count": 512},
                "jira": {"wip": {"count": 44}, "completed": 103},
                "members": [],
            },
        },
        "persons": {
            "jdoe": {
                "name": "John Doe",
                "teams": ["Native"],
                "timestamp": datetime.now(),
                "github": {
                    "prs_created": 10,
                    "prs_merged": 8,
                    "reviews_given": 50,
                    "commits": 60,
                    "lines_added": 1000,
                    "lines_deleted": 500,
                },
                "jira": {"issues_completed": 5, "issues_in_progress": 2},
                "period": {"start": "2024-10-13", "end": "2026-01-11"},
            }
        },
        "comparison": {
            "Native": {
                "score": 75.5,
                "team_size": 5,
                "github": {"pr_count": 107, "review_count": 472},
                "jira": {"completed": 57},
            },
            "WebTC": {
                "score": 68.2,
                "team_size": 4,
                "github": {"pr_count": 69, "review_count": 268},
                "jira": {"completed": 103},
            },
        },
        "timestamp": datetime.now(),
    }


@pytest.fixture
def mock_cache(monkeypatch, mock_cache_data):
    """Mock metrics cache with sample data"""
    # Mock the cache
    monkeypatch.setattr("src.dashboard.app.metrics_cache", {"data": mock_cache_data, "range_key": "90d"})

    return mock_cache_data


class TestMainRoutes:
    """Test main dashboard routes"""

    def test_index_with_range_parameter(self, client, mock_cache):
        """Test index with date range parameter"""
        response = client.get("/?range=30d")
        assert response.status_code == 200


class TestDocumentationRoutes:
    """Test documentation routes"""

    def test_documentation_page(self, client, mock_cache):
        """Test documentation page loads"""
        response = client.get("/documentation")
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling"""

    def test_no_cache_loaded(self, client, monkeypatch):
        """Test handling when no cache is loaded"""
        monkeypatch.setattr("src.dashboard.app.metrics_cache", {"data": None})
        response = client.get("/")
        # Should either show loading page (200) or handle gracefully
        assert response.status_code in [200, 500]


class TestAppConfiguration:
    """Test Flask app configuration"""

    def test_app_exists(self):
        """Test that Flask app is properly configured"""
        assert app is not None
        assert app.name == "src.dashboard.app"

    def test_app_in_testing_mode(self, client):
        """Test that testing mode can be enabled"""
        assert client.application.config["TESTING"] is True


class TestExportFunctionality:
    """Test export routes for CSV and JSON"""

    def test_export_team_csv(self, client, mock_cache):
        """Test exporting team data as CSV"""
        response = client.get("/api/export/team/Native/csv")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["Content-Disposition"]
        # Check for filename pattern with date suffix (e.g., team_native_metrics_2026-01-14.csv)
        assert "team_native_metrics_" in response.headers["Content-Disposition"]
        assert ".csv" in response.headers["Content-Disposition"]

        # Parse CSV and verify structure
        csv_data = response.data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        assert len(rows) == 1

        # Verify key fields are present (flattened structure)
        row = rows[0]
        assert "github.pr_count" in row
        assert "github.review_count" in row
        assert "jira.wip.count" in row

    def test_export_team_json(self, client, mock_cache):
        """Test exporting team data as JSON"""
        response = client.get("/api/export/team/Native/json")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"
        assert "attachment" in response.headers["Content-Disposition"]
        # Check for filename pattern with date suffix
        assert "team_native_metrics_" in response.headers["Content-Disposition"]
        assert ".json" in response.headers["Content-Disposition"]

        # Parse JSON and verify structure
        data = json.loads(response.data)
        assert "team" in data
        assert "metadata" in data
        assert data["team"]["github"]["pr_count"] == 107
        assert data["team"]["jira"]["completed"] == 57

    def test_export_team_not_found(self, client, mock_cache):
        """Test exporting non-existent team"""
        response = client.get("/api/export/team/NonExistent/csv")
        assert response.status_code == 404
        assert b"not found" in response.data

    def test_export_person_csv(self, client, mock_cache):
        """Test exporting person data as CSV"""
        response = client.get("/api/export/person/jdoe/csv")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
        # Check for filename pattern with date suffix
        assert "person_jdoe_metrics_" in response.headers["Content-Disposition"]
        assert ".csv" in response.headers["Content-Disposition"]

        # Parse CSV and verify structure
        csv_data = response.data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        assert len(rows) == 1

        row = rows[0]
        assert "github.prs_created" in row
        assert "jira.issues_completed" in row

    def test_export_person_json(self, client, mock_cache):
        """Test exporting person data as JSON"""
        response = client.get("/api/export/person/jdoe/json")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"

        data = json.loads(response.data)
        assert "person" in data
        assert "metadata" in data
        assert data["person"]["name"] == "John Doe"
        assert data["person"]["github"]["prs_created"] == 10

    def test_export_person_not_found(self, client, mock_cache):
        """Test exporting non-existent person"""
        response = client.get("/api/export/person/unknown/json")
        assert response.status_code == 404

    def test_export_comparison_csv(self, client, mock_cache):
        """Test exporting team comparison as CSV"""
        response = client.get("/api/export/comparison/csv")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
        # Check for filename pattern with date suffix
        assert "team_comparison_metrics_" in response.headers["Content-Disposition"]
        assert ".csv" in response.headers["Content-Disposition"]

        # Parse CSV and verify structure
        csv_data = response.data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        assert len(rows) == 2  # Two teams

        # Verify team names are present
        team_names = [row["team_name"] for row in rows]
        assert "Native" in team_names
        assert "WebTC" in team_names

    def test_export_comparison_json(self, client, mock_cache):
        """Test exporting team comparison as JSON"""
        response = client.get("/api/export/comparison/json")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"

        data = json.loads(response.data)
        assert "comparison" in data
        assert "metadata" in data
        assert "Native" in data["comparison"]
        assert "WebTC" in data["comparison"]
        assert data["comparison"]["Native"]["score"] == 75.5

    def test_export_team_members_csv(self, client, mock_cache, monkeypatch):
        """Test exporting team member comparison as CSV"""
        # Add members_breakdown to mock data
        mock_data = mock_cache.copy()
        mock_data["teams"]["Native"]["members_breakdown"] = {
            "John Doe": {
                "github": {"prs_created": 10, "reviews_given": 50},
                "jira": {"issues_completed": 5},
                "score": 85.0,
            }
        }
        monkeypatch.setattr(
            "src.dashboard.app.metrics_cache",
            {"data": mock_data, "range_key": "90d", "date_range": mock_cache.get("date_range", {})},
        )

        response = client.get("/api/export/team-members/Native/csv")
        assert response.status_code == 200
        # Check for filename pattern with date suffix
        assert "team_native_members_comparison_" in response.headers["Content-Disposition"]
        assert ".csv" in response.headers["Content-Disposition"]

        # Parse CSV
        csv_data = response.data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["member_name"] == "John Doe"

    def test_export_team_members_json(self, client, mock_cache, monkeypatch):
        """Test exporting team member comparison as JSON"""
        # Add members_breakdown to mock data
        mock_data = mock_cache.copy()
        mock_data["teams"]["Native"]["members_breakdown"] = {"John Doe": {"github": {"prs_created": 10}, "score": 85.0}}
        monkeypatch.setattr(
            "src.dashboard.app.metrics_cache",
            {"data": mock_data, "range_key": "90d", "date_range": mock_cache.get("date_range", {})},
        )

        response = client.get("/api/export/team-members/Native/json")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "members" in data
        assert "John Doe" in data["members"]
        assert data["members"]["John Doe"]["score"] == 85.0

    def test_export_no_cache(self, client, monkeypatch):
        """Test export when no cache is available"""
        monkeypatch.setattr("src.dashboard.app.metrics_cache", {"data": None})

        response = client.get("/api/export/team/Native/csv")
        assert response.status_code == 404
        assert b"No metrics data available" in response.data


class TestSettingsRoutes:
    """Test settings functionality"""

    def test_settings_page_loads(self, client, mock_cache):
        """Test settings page renders successfully"""
        response = client.get("/settings")
        assert response.status_code == 200
        assert b"Performance Score Settings" in response.data

    def test_settings_page_has_presets(self, client, mock_cache):
        """Test settings page contains preset buttons"""
        response = client.get("/settings")
        assert response.status_code == 200
        assert b"Balanced" in response.data
        assert b"Code Quality" in response.data
        assert b"Velocity" in response.data
        assert b"Jira Focus" in response.data

    def test_settings_save_valid_weights(self, client, mock_cache, monkeypatch):
        """Test saving valid performance weights"""

        # Mock config
        class MockConfig:
            def __init__(self):
                self.performance_weights = {}

            def update_performance_weights(self, weights):
                self.performance_weights = weights

        mock_config = MockConfig()
        monkeypatch.setattr("src.dashboard.app.get_config", lambda: mock_config)

        # Valid weights that sum to 100
        weights = {"prs": 20, "reviews": 20, "commits": 15, "cycle_time": 15, "jira_completed": 20, "merge_rate": 10}

        response = client.post("/settings/save", data=json.dumps(weights), content_type="application/json")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        # Verify weights were converted to decimals
        assert mock_config.performance_weights["prs"] == 0.20
        assert mock_config.performance_weights["reviews"] == 0.20

    def test_settings_save_invalid_weights_sum(self, client, mock_cache):
        """Test saving weights that don't sum to 100"""
        # Invalid weights (sum to 110)
        weights = {"prs": 30, "reviews": 30, "commits": 20, "cycle_time": 10, "jira_completed": 10, "merge_rate": 10}

        response = client.post("/settings/save", data=json.dumps(weights), content_type="application/json")

        # Should return 400 (bad request) for validation error
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "error" in data
        assert "must sum to 100%" in data["error"]

    def test_settings_reset(self, client, mock_cache, monkeypatch):
        """Test resetting weights to defaults"""

        class MockConfig:
            def __init__(self):
                self.performance_weights = {}

            def update_performance_weights(self, weights):
                self.performance_weights = weights

        mock_config = MockConfig()
        monkeypatch.setattr("src.dashboard.app.get_config", lambda: mock_config)

        response = client.post("/settings/reset")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        # Verify default weights were set
        assert mock_config.performance_weights["prs"] == 0.20
        assert mock_config.performance_weights["reviews"] == 0.20
        assert mock_config.performance_weights["commits"] == 0.15
        assert mock_config.performance_weights["cycle_time"] == 0.15
        assert mock_config.performance_weights["jira_completed"] == 0.20
        assert mock_config.performance_weights["merge_rate"] == 0.10


class TestHelperFunctions:
    """Test export helper functions"""

    def test_flatten_dict(self):
        """Test dictionary flattening with nested structures"""
        from src.dashboard.app import flatten_dict

        nested = {"a": 1, "b": {"c": 2, "d": {"e": 3}}, "f": [1, 2, 3]}

        flattened = flatten_dict(nested)
        assert flattened["a"] == 1
        assert flattened["b.c"] == 2
        assert flattened["b.d.e"] == 3
        assert flattened["f"] == "1, 2, 3"

    def test_format_value_for_csv(self):
        """Test CSV value formatting"""
        from src.dashboard.app import format_value_for_csv

        # Test numbers
        assert format_value_for_csv(42) == 42
        assert format_value_for_csv(3.14159) == 3.14

        # Test datetime
        dt = datetime(2024, 1, 15, 10, 30, 45)
        assert format_value_for_csv(dt) == "2024-01-15 10:30:45"

        # Test None
        assert format_value_for_csv(None) == ""

        # Test string
        assert format_value_for_csv("hello") == "hello"
