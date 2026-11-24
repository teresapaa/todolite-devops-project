import pytest
from cachelib import SimpleCache
from app import create_app


def build_app(**overrides):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "SESSION_COOKIE_SECURE": False,
        # In-memory session store so tests never touch instance/.
        "SESSION_CACHELIB": SimpleCache(),
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture
def app():
    return build_app()


def create_user(app, name, role="user"):
    from models import db, User
    with app.app_context():
        user = User(oidc_issuer="https://accounts.google.com", oidc_sub=f"sub-{name}",
                    email=f"{name}@example.com", name=name, role=role)
        db.session.add(user)
        db.session.commit()
        return user.id


def login_as(client, user_id):
    """Authenticate a test client by writing the user id into its server-side session."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client
