from app import create_app


def make_app():
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })


def test_login_and_signup_fields_have_labels():
    client = make_app().test_client()
    for page in ("/login", "/signup"):
        html = client.get(page).data
        assert b'<label for="username">' in html
        assert b'<label for="password">' in html
        assert b'id="username"' in html and b'id="password"' in html


def test_todo_buttons_say_which_todo_they_act_on():
    client = make_app().test_client()
    client.post("/signup", data={"username": "ana", "password": "secret"})
    client.post("/todos", data={"title": "Buy milk", "priority": "3"})
    html = client.get("/").data
    assert b'<label for="todo-title"' in html
    assert b'aria-label="Complete: Buy milk"' in html
    assert b'aria-label="Delete: Buy milk"' in html


def test_error_messages_are_announced():
    client = make_app().test_client()
    html = client.post("/login", data={"username": "nobody", "password": "wrong"},
                       follow_redirects=True).data
    assert b'role="alert"' in html
    assert b"Invalid username or password." in html
