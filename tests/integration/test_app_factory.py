# tests/integration/test_app_factory.py
"""Integration tests for the Flask application factory."""

from flask import Flask


class TestAppFactory:
    """Tests for create_app() and CLI commands."""

    def test_create_app_returns_flask(self, app):
        assert isinstance(app, Flask)

    def test_testing_config_applied(self, app):
        assert app.config["TESTING"] is True

    def test_init_db_command(self, app):
        runner = app.test_cli_runner()
        result = runner.invoke(args=["init-db"])
        assert result.exit_code == 0
        assert "DB initialized" in result.output
