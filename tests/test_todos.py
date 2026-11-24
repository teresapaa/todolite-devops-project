from models import db, User, Todo


def test_crud_and_user_isolation(app):
    with app.app_context():
        db.drop_all()
        db.create_all()
    clients = [app.test_client(), app.test_client()]
    for client, name in zip(clients, ("alice", "bob")):
        assert client.post("/signup", data={"username": name, "password": "secret"}).status_code == 302

    assert clients[0].post("/todos", data={"title": "Alice todo", "priority": "5"}).status_code == 302
    assert clients[1].post("/todos", data={"title": "Bob todo", "priority": "1"}).status_code == 302
    assert b"Alice todo" in clients[0].get("/").data
    assert b"Bob todo" not in clients[0].get("/").data

    with app.app_context():
        alice = User.query.filter_by(username="alice").first()
        todo = Todo.query.filter_by(user_id=alice.id).first()
        todo_id = todo.id
    assert clients[1].post(f"/todos/{todo_id}/complete").status_code == 404
    assert clients[0].post(f"/todos/{todo_id}/complete").status_code == 302
    assert clients[0].post(f"/todos/{todo_id}/delete").status_code == 302
