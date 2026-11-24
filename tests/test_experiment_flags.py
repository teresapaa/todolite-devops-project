"""QA test cases for the two experiment toggles: empty_state_nudge and priority_flag.

Each test writes a real flags.json in a temp folder, so the tests use the same
code path as production: the file is re-read on every request.
"""
import json

import pytest

import flags
from conftest import build_app, create_user, login_as
from models import Event, Todo, db

ALL_ON = {"empty_state_nudge": {"enabled": True, "rollout": 100},
          "priority_flag": {"enabled": True, "rollout": 100}}
ALL_OFF = {"empty_state_nudge": {"enabled": False, "rollout": 100},
           "priority_flag": {"enabled": False, "rollout": 100}}


@pytest.fixture
def flag_file(tmp_path, monkeypatch):
    path = tmp_path / "flags.json"
    monkeypatch.setattr(flags, "FLAGS_FILE", path)
    monkeypatch.delenv("FLAGS_KILL", raising=False)

    def write(config):
        path.write_text(json.dumps(config))
    return write


def new_user(app, name="alice", role="user"):
    """A fresh account (as after the first Google sign-in), logged in on its own client."""
    return login_as(app.test_client(), create_user(app, name, role))


def first_todo(app):
    with app.app_context():
        return db.session.query(Todo).first()


# ---------- empty_state_nudge ----------

def test_nudge_on_shows_prompt_and_focuses_input(app, flag_file):
    flag_file(ALL_ON)
    html = new_user(app).get("/").get_data(as_text=True)
    assert "Add your first todo to get started" in html
    assert "autofocus" in html
    assert 'placeholder="Add your first todo…"' in html
    assert "No todos yet." not in html


def test_nudge_off_shows_old_empty_state(app, flag_file):
    flag_file(ALL_OFF)
    html = new_user(app).get("/").get_data(as_text=True)
    assert "No todos yet." in html
    assert "Add your first todo to get started" not in html
    assert "autofocus" not in html
    assert 'placeholder="Add a todo"' in html


def test_nudge_disappears_once_list_has_a_todo(app, flag_file):
    flag_file(ALL_ON)
    client = new_user(app)
    client.post("/todos", data={"title": "first", "priority": "3"})
    html = client.get("/").get_data(as_text=True)
    assert "Add your first todo to get started" not in html
    assert "autofocus" not in html


# ---------- priority_flag ----------

def test_flag_on_button_visible_and_toggles(app, flag_file):
    flag_file(ALL_ON)
    client = new_user(app)
    client.post("/todos", data={"title": "pay rent", "priority": "3"})
    assert 'data-testid="flag-button"' in client.get("/").get_data(as_text=True)

    todo_id = first_todo(app).id
    assert client.post(f"/todos/{todo_id}/flag").status_code == 302
    assert first_todo(app).flagged is True
    assert 'class=" flagged"' in client.get("/").get_data(as_text=True)

    client.post(f"/todos/{todo_id}/flag")          # second click removes it
    assert first_todo(app).flagged is False


def test_flag_off_button_hidden(app, flag_file):
    flag_file(ALL_OFF)
    client = new_user(app)
    client.post("/todos", data={"title": "pay rent", "priority": "3"})
    html = client.get("/").get_data(as_text=True)
    assert 'data-testid="flag-button"' not in html
    assert "P3" in html                              # 1-5 priority is still shown


def test_flag_off_is_blocked_on_server(app, flag_file):
    """A hidden button is not access control: a direct POST must also fail."""
    flag_file(ALL_OFF)
    client = new_user(app)
    client.post("/todos", data={"title": "pay rent", "priority": "3"})
    todo_id = first_todo(app).id
    assert client.post(f"/todos/{todo_id}/flag").status_code == 403
    assert first_todo(app).flagged is False
    with app.app_context():
        assert Event.query.filter_by(name="flag_denied").count() == 1


def test_flag_cannot_touch_other_users_todo(app, flag_file):
    flag_file(ALL_ON)
    alice, bob = new_user(app, "alice"), new_user(app, "bob")
    alice.post("/todos", data={"title": "alice only", "priority": "3"})
    todo_id = first_todo(app).id
    assert bob.post(f"/todos/{todo_id}/flag").status_code == 404
    assert first_todo(app).flagged is False


def test_logged_out_user_cannot_flag(app, flag_file):
    flag_file(ALL_ON)
    response = app.test_client().post("/todos/1/flag")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_flag_needs_write_permission_even_when_on(app, flag_file):
    """Toggle ON is not enough: RBAC still applies (unknown role has no permissions)."""
    flag_file(ALL_ON)
    owner = create_user(app, "guest", role="guest")
    with app.app_context():
        db.session.add(Todo(user_id=owner, title="x"))
        db.session.commit()
    client = login_as(app.test_client(), owner)
    assert client.post(f"/todos/{first_todo(app).id}/flag").status_code == 403
    assert first_todo(app).flagged is False


def test_flag_form_is_csrf_protected(flag_file):
    flag_file(ALL_ON)
    app = build_app(WTF_CSRF_ENABLED=True)
    client = new_user(app)
    with app.app_context():
        db.session.add(Todo(user_id=1, title="x"))
        db.session.commit()
    todo_id = first_todo(app).id
    assert client.post(f"/todos/{todo_id}/flag").status_code == 400   # no token → rejected
    html = client.get("/").get_data(as_text=True)
    token = html.split(f'/todos/{todo_id}/flag" method="post">')[1].split('value="')[1].split('"')[0]
    assert client.post(f"/todos/{todo_id}/flag", data={"csrf_token": token}).status_code == 302
    assert first_todo(app).flagged is True


# ---------- switching ----------

def test_switch_on_off_on_without_restart_keeps_data(app, flag_file):
    flag_file(ALL_ON)
    client = new_user(app)
    client.post("/todos", data={"title": "important", "priority": "2"})
    client.post(f"/todos/{first_todo(app).id}/flag")
    assert "🚩" in client.get("/").get_data(as_text=True)

    flag_file(ALL_OFF)                               # operator flips the file, same app instance
    html = client.get("/").get_data(as_text=True)
    assert "🚩" not in html and "flagged" not in html
    assert first_todo(app).flagged is True           # stored, just not shown

    flag_file(ALL_ON)                                # switch back: nothing was lost
    assert "🚩" in client.get("/").get_data(as_text=True)


def test_switching_nudge_mid_session(app, flag_file):
    client = new_user(app)
    flag_file(ALL_OFF)
    assert "No todos yet." in client.get("/").get_data(as_text=True)
    flag_file(ALL_ON)
    assert "Add your first todo to get started" in client.get("/").get_data(as_text=True)


# ---------- kill switch, rollout, bad config ----------

def test_env_kill_switch_beats_the_file(app, flag_file, monkeypatch):
    flag_file(ALL_ON)
    client = new_user(app)
    client.post("/todos", data={"title": "x", "priority": "3"})
    monkeypatch.setenv("FLAGS_KILL", "priority_flag")
    assert 'data-testid="flag-button"' not in client.get("/").get_data(as_text=True)
    assert client.post(f"/todos/{first_todo(app).id}/flag").status_code == 403
    assert app.test_client().get("/healthz").get_json()["flags"]["priority_flag"]["killed"] is True


def test_rollout_0_and_100_and_sticky(flag_file):
    flag_file({"f": {"enabled": True, "rollout": 0}})
    assert not any(flags.is_on("f", uid) for uid in range(500))
    flag_file({"f": {"enabled": True, "rollout": 100}})
    assert all(flags.is_on("f", uid) for uid in range(500))
    flag_file({"f": {"enabled": True, "rollout": 20}})
    first = [flags.is_on("f", uid) for uid in range(2000)]
    assert first == [flags.is_on("f", uid) for uid in range(2000)]  # same answer every time
    assert 300 < sum(first) < 500                                   # about 20 %


def test_raising_rollout_only_adds_users(flag_file):
    flag_file({"f": {"enabled": True, "rollout": 20}})
    at_20 = {uid for uid in range(1000) if flags.is_on("f", uid)}
    flag_file({"f": {"enabled": True, "rollout": 50}})
    at_50 = {uid for uid in range(1000) if flags.is_on("f", uid)}
    assert at_20 <= at_50


@pytest.mark.parametrize("content", ["{not json", "[]", '{"priority_flag": "yes"}',
                                     '{"priority_flag": {"enabled": "true", "rollout": 100}}',
                                     '{"priority_flag": {"enabled": true, "rollout": "lots"}}'])
def test_broken_config_fails_closed(app, flag_file, content):
    flags.FLAGS_FILE.write_text(content)
    client = new_user(app)
    client.post("/todos", data={"title": "x", "priority": "3"})
    response = client.get("/")
    assert response.status_code == 200               # app keeps working
    assert 'data-testid="flag-button"' not in response.get_data(as_text=True)


def test_repo_flags_json_is_valid():
    """CI guard: the shipped flags.json must parse and every rollout must be 0-100."""
    data = json.loads(flags.Path(flags.__file__).with_name("flags.json").read_text())
    for flag in ("empty_state_nudge", "priority_flag"):
        assert flag in data
    for name, cfg in data.items():
        assert isinstance(cfg["enabled"], bool), name
        assert isinstance(cfg["rollout"], int) and 0 <= cfg["rollout"] <= 100, name


# ---------- monitoring ----------

def test_events_are_tagged_with_variant(app, flag_file):
    flag_file(ALL_ON)
    client = new_user(app)
    client.get("/")
    client.post("/todos", data={"title": "first", "priority": "3"})
    with app.app_context():
        first = Event.query.filter_by(name="first_todo").one()
        assert first.variant == "on" and first.value is not None and first.value >= 0
        assert Event.query.filter_by(name="empty_list_view", variant="on").count() == 1


def test_server_error_is_counted_per_variant(app, flag_file):
    flag_file(ALL_ON)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    client = new_user(app)
    assert client.get("/boom").status_code == 500
    with app.app_context():
        assert Event.query.filter_by(name="error", flag="priority_flag", variant="on").count() == 1
