from conftest import create_user, login_as
from models import db, Todo


def test_crud_and_user_isolation(app):
    alice_id = create_user(app, "alice")
    bob_id = create_user(app, "bob")
    alice = login_as(app.test_client(), alice_id)
    bob = login_as(app.test_client(), bob_id)

    assert alice.post("/todos", data={"title": "Alice todo", "priority": "5"}).status_code == 302
    assert bob.post("/todos", data={"title": "Bob todo", "priority": "1"}).status_code == 302
    assert b"Alice todo" in alice.get("/").data
    assert b"Bob todo" not in alice.get("/").data

    with app.app_context():
        todo_id = Todo.query.filter_by(user_id=alice_id).first().id
    assert bob.post(f"/todos/{todo_id}/complete").status_code == 404
    assert alice.post(f"/todos/{todo_id}/complete").status_code == 302
    assert alice.post(f"/todos/{todo_id}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(Todo, todo_id) is None
