from conftest import create_user, login_as
from models import db, User


def test_admin_pages_require_admin_role(app):
    alice = create_user(app, "alice")
    bob = create_user(app, "bob")
    client = login_as(app.test_client(), alice)
    assert client.get("/admin/users").status_code == 403
    assert client.get(f"/admin/users/{bob}").status_code == 403
    assert client.post(f"/admin/users/{bob}/role", data={"role": "admin"}).status_code == 403
    assert client.post(f"/admin/users/{bob}/active", data={"active": "0"}).status_code == 403
    assert b"Admin</a>" not in client.get("/").data


def test_admin_changes_role_and_status(app):
    admin = create_user(app, "root", role="admin")
    alice = create_user(app, "alice")
    client = login_as(app.test_client(), admin)
    assert client.get("/admin/users").status_code == 200
    assert client.get(f"/admin/users/{alice}").status_code == 200
    assert client.post(f"/admin/users/{alice}/role", data={"role": "admin"}).status_code == 302
    assert client.post(f"/admin/users/{alice}/active", data={"active": "0"}).status_code == 302
    with app.app_context():
        user = db.session.get(User, alice)
        assert user.role == "admin" and user.is_active is False


def test_admin_cannot_lock_out_themselves_or_set_unknown_roles(app):
    admin = create_user(app, "root", role="admin")
    alice = create_user(app, "alice")
    client = login_as(app.test_client(), admin)
    assert client.post(f"/admin/users/{admin}/role", data={"role": "user"}).status_code == 400
    assert client.post(f"/admin/users/{admin}/active", data={"active": "0"}).status_code == 400
    assert client.post(f"/admin/users/{alice}/role", data={"role": "superuser"}).status_code == 400


def test_set_role_cli(app):
    create_user(app, "alice")
    result = app.test_cli_runner().invoke(args=["admin", "set-role", "alice", "admin"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert User.query.filter_by(username="alice").first().role == "admin"
    result = app.test_cli_runner().invoke(args=["admin", "set-role", "nobody", "admin"])
    assert result.exit_code != 0
