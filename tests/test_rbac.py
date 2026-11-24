from conftest import create_user, login_as
from models import db, Todo, User


def add_todo(app, user_id, title="Todo"):
    with app.app_context():
        todo = Todo(user_id=user_id, title=title)
        db.session.add(todo)
        db.session.commit()
        return todo.id


def test_anonymous_requests_are_redirected(app):
    client = app.test_client()
    assert client.get("/").status_code == 302
    assert client.post("/todos", data={"title": "x"}).status_code == 302
    assert client.post("/todos/1/delete").status_code == 302


def test_user_cannot_touch_foreign_todo(app):
    alice = create_user(app, "alice")
    bob = create_user(app, "bob")
    todo_id = add_todo(app, alice)
    client = login_as(app.test_client(), bob)
    assert client.post(f"/todos/{todo_id}/complete").status_code == 404
    assert client.post(f"/todos/{todo_id}/delete").status_code == 404
    with app.app_context():
        assert db.session.get(Todo, todo_id).completed is False


def test_admin_may_modify_any_todo(app):
    alice = create_user(app, "alice")
    admin = create_user(app, "root", role="admin")
    todo_id = add_todo(app, alice)
    client = login_as(app.test_client(), admin)
    assert client.post(f"/todos/{todo_id}/complete").status_code == 302
    assert client.post(f"/todos/{todo_id}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(Todo, todo_id) is None


def test_deactivated_user_loses_access_immediately(app):
    alice = create_user(app, "alice")
    client = login_as(app.test_client(), alice)
    assert client.get("/").status_code == 200
    with app.app_context():
        db.session.get(User, alice).is_active = False
        db.session.commit()
    assert client.get("/").status_code == 302
    # The session was cleared, so reactivating does not silently restore it.
    with app.app_context():
        db.session.get(User, alice).is_active = True
        db.session.commit()
    assert client.get("/").status_code == 302


def test_unknown_role_has_no_permissions(app):
    alice = create_user(app, "alice", role="guest")
    client = login_as(app.test_client(), alice)
    assert client.get("/").status_code == 403


def test_next_parameter_rejects_external_targets(app):
    alice = create_user(app, "alice")
    client = login_as(app.test_client(), alice)
    for target in ("https://evil.example", "//evil.example", "/\\evil.example"):
        todo_id = add_todo(app, alice)
        response = client.post(f"/todos/{todo_id}/complete", data={"next": target})
        assert response.headers["Location"] == "/"
