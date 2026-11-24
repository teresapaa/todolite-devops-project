import pytest
from cachelib import SimpleCache
from app import create_app


def build_app(**overrides):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SESSION_COOKIE_SECURE": False,
        # In-memory session store so tests never touch instance/.
        "SESSION_CACHELIB": SimpleCache(),
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture
def app():
    return build_app()
