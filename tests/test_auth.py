from conftest import build_app


def test_signup_login_and_logout(app):
    client = app.test_client()
    response = client.post("/signup", data={"username": "alice", "password": "secret"})
    assert response.status_code == 302
    assert client.get("/").status_code == 200

    client.post("/logout")
    response = client.post("/login", data={"username": "alice", "password": "wrong"})
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data
    assert client.get("/").status_code == 302

    response = client.post("/login", data={"username": "alice", "password": "secret"})
    assert response.status_code == 302


def test_session_is_stored_server_side_and_revoked_on_logout(app):
    client = app.test_client()
    client.post("/signup", data={"username": "alice", "password": "secret"})
    cookie = client.get_cookie("session")
    # The cookie only holds an opaque id, no user data.
    assert "alice" not in cookie.value and "user_id" not in cookie.value

    client.post("/logout")
    # Replaying the old session id after logout must not authenticate.
    attacker = app.test_client()
    attacker.set_cookie("session", cookie.value)
    assert attacker.get("/").status_code == 302


def test_login_rotates_session_id(app):
    client = app.test_client()
    client.post("/signup", data={"username": "alice", "password": "secret"})
    client.post("/logout")
    client.get("/login")
    with client.session_transaction() as sess:
        sess["probe"] = True
    before = client.get_cookie("session").value
    client.post("/login", data={"username": "alice", "password": "secret"})
    assert client.get_cookie("session").value != before


def test_post_without_csrf_token_is_rejected():
    app = build_app(WTF_CSRF_ENABLED=True)
    client = app.test_client()
    response = client.post("/login", data={"username": "alice", "password": "secret"})
    assert response.status_code == 400
