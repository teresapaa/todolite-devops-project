from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
import pytest
from authlib.integrations.base_client import OAuthError
import auth
from conftest import build_app, create_user, login_as
from models import db, User

ISSUER = "https://accounts.google.com"
GOOGLE_METADATA = {
    "issuer": ISSUER,
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
}


def claims(**overrides):
    data = {"iss": ISSUER, "sub": "google-123", "email": "Alice@Example.com",
            "email_verified": True, "name": "Alice"}
    data.update(overrides)
    return data


def fake_google(monkeypatch, userinfo=None, error=None):
    """Replace the Google client: the callback then receives these already-validated claims."""
    def authorize_access_token():
        if error:
            raise error
        return {"access_token": "x", "id_token": "y", "userinfo": userinfo}
    monkeypatch.setattr(auth, "google", lambda: SimpleNamespace(authorize_access_token=authorize_access_token))


def test_login_page_offers_google(app):
    response = app.test_client().get("/login")
    assert response.status_code == 200
    assert b"Sign in with Google" in response.data


def test_google_redirect_uses_pkce_state_and_nonce(app, monkeypatch):
    with app.app_context():
        client = auth.google()
        monkeypatch.setattr(type(client), "load_server_metadata", lambda self: GOOGLE_METADATA)
    response = app.test_client().get("/login/google")
    assert response.status_code == 302
    location = urlparse(response.headers["Location"])
    params = parse_qs(location.query)
    assert location.netloc == "accounts.google.com"
    assert params["client_id"] == ["test-client-id"]
    assert params["scope"] == ["openid email profile"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost/auth/callback"]
    assert params["state"] and params["nonce"] and params["code_challenge"]


def test_first_login_provisions_user_with_default_role(app, monkeypatch):
    # A role claim in the token must be ignored: roles come only from our database.
    fake_google(monkeypatch, claims(role="admin"))
    client = app.test_client()
    response = client.get("/auth/callback?code=abc&state=xyz")
    assert response.status_code == 302 and response.headers["Location"] == "/"
    assert client.get("/").status_code == 200
    with app.app_context():
        user = User.query.one()
        assert (user.oidc_sub, user.email, user.name, user.role) == ("google-123", "alice@example.com", "Alice", "user")


def test_existing_user_is_matched_by_subject_not_email(app, monkeypatch):
    fake_google(monkeypatch, claims())
    app.test_client().get("/auth/callback")
    fake_google(monkeypatch, claims(email="new@example.com", name="Alice B."))
    app.test_client().get("/auth/callback")
    with app.app_context():
        user = User.query.one()
        assert (user.email, user.name) == ("new@example.com", "Alice B.")


@pytest.mark.parametrize("userinfo", [None, claims(email_verified=False), claims(email=None)])
def test_unverified_or_missing_identity_is_rejected(app, monkeypatch, userinfo):
    fake_google(monkeypatch, userinfo)
    client = app.test_client()
    response = client.get("/auth/callback")
    assert response.headers["Location"] == "/login"
    assert client.get("/").status_code == 302
    with app.app_context():
        assert User.query.count() == 0


def test_provider_error_is_handled(app, monkeypatch):
    fake_google(monkeypatch, error=OAuthError(error="access_denied"))
    client = app.test_client()
    assert client.get("/auth/callback?error=access_denied").headers["Location"] == "/login"
    assert b"Login with Google failed" in client.get("/login").data


def test_allowed_email_domains(monkeypatch):
    app = build_app(ALLOWED_EMAIL_DOMAINS=["ntust.edu.tw"])
    fake_google(monkeypatch, claims(email="alice@gmail.com"))
    assert app.test_client().get("/auth/callback").headers["Location"] == "/login"
    fake_google(monkeypatch, claims(email="alice@NTUST.edu.tw", sub="other"))
    assert app.test_client().get("/auth/callback").headers["Location"] == "/"


def test_deactivated_user_cannot_sign_in(app, monkeypatch):
    fake_google(monkeypatch, claims())
    app.test_client().get("/auth/callback")
    with app.app_context():
        User.query.one().is_active = False
        db.session.commit()
    client = app.test_client()
    assert client.get("/auth/callback").headers["Location"] == "/login"
    assert client.get("/").status_code == 302


def test_login_rotates_session_id(app, monkeypatch):
    fake_google(monkeypatch, claims())
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["probe"] = True
    before = client.get_cookie("session").value
    client.get("/auth/callback")
    assert client.get_cookie("session").value != before


def test_session_is_stored_server_side_and_revoked_on_logout(app):
    client = login_as(app.test_client(), create_user(app, "alice"))
    assert client.get("/").status_code == 200
    cookie = client.get_cookie("session")
    # The cookie only holds an opaque id, no user data.
    assert "alice" not in cookie.value and "user_id" not in cookie.value

    assert client.post("/logout").headers["Location"] == "/login"
    assert client.get("/").status_code == 302
    # Replaying the old session id after logout must not authenticate.
    attacker = app.test_client()
    attacker.set_cookie("session", cookie.value)
    assert attacker.get("/").status_code == 302


def test_post_without_csrf_token_is_rejected():
    app = build_app(WTF_CSRF_ENABLED=True)
    client = login_as(app.test_client(), create_user(app, "alice"))
    assert client.post("/todos", data={"title": "x"}).status_code == 400
    assert client.post("/logout").status_code == 400


def test_app_refuses_to_start_without_google_credentials():
    with pytest.raises(RuntimeError, match="GOOGLE_CLIENT_ID"):
        build_app(GOOGLE_CLIENT_ID=None)
