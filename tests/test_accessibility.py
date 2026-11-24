from conftest import create_user, login_as


def test_add_field_has_a_label(app):
    client = login_as(app.test_client(), create_user(app, "ana"))
    html = client.get("/").data
    assert b'<label for="todo-title"' in html
    assert b'id="todo-title"' in html


def test_todo_buttons_say_which_todo_they_act_on(app):
    client = login_as(app.test_client(), create_user(app, "ana"))
    client.post("/todos", data={"title": "Buy milk", "priority": "3"})
    html = client.get("/").data
    assert b'aria-label="Complete: Buy milk"' in html
    assert b'aria-label="Delete: Buy milk"' in html


def test_error_messages_are_announced(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_flashes"] = [("message", "Login with Google failed. Please try again.")]
    html = client.get("/login").data
    assert b'role="alert"' in html
    assert b"Login with Google failed." in html


def test_tab_title_says_todolite(app):
    html = app.test_client().get("/login").data
    assert b"TodoLite</title>" in html
