# tests/conftest.py
"""Shared fixtures for unit, integration, and e2e tests."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """Create a Flask app with an in-memory SQLite database."""
    application = create_app()
    application.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key",
    )

    with application.app_context():
        _db.create_all()

        from app.models import DetectionRule
        if DetectionRule.query.count() == 0:
            _db.session.add(
                DetectionRule(
                    name="Test Rule",
                    lookback_min=2,
                    threshold_pct=2.0,
                    color="#10b981",
                    sort_order=0,
                )
            )
            _db.session.commit()

        from app.settings import seed_defaults
        seed_defaults()

    yield application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Provide a DB session, rolled back after each test."""
    with app.app_context():
        yield _db.session
        _db.session.rollback()
