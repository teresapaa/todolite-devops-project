"""Who may use each toggled feature, decided on the server."""
from unittest.mock import patch
import pytest
import authz
import flags
from conftest import create_user, login_as


def set_flags(enabled=True, rollout=100):
    config = {name: {"enabled": enabled, "rollout": rollout} for name in authz.FEATURES}
    return patch.object(flags, "load_flags", return_value=config)


def priority_sorted(client):
    client.post("/todos", data={"title": "low earlier", "priority": "1"})
    client.post("/todos", data={"title": "high later", "priority": "5"})
    client.post("/todos", data={"title": "mid latest", "priority": "3"})
    body = client.get("/").data
    # Creation order (newest first) would be mid, high, low; priority order is high, mid, low.
    return body.find(b"high later") < body.find(b"mid latest")


def quick_add_on(client):
    return b'data-quick-add="true"' in client.get("/").data


@pytest.mark.parametrize("role", ["user", "admin"])
def test_features_on_for_permitted_roles(app, role):
    client = login_as(app.test_client(), create_user(app, "alice", role=role))
    with set_flags(enabled=True, rollout=100):
        assert priority_sorted(client)
        assert quick_add_on(client)


@pytest.mark.parametrize("role", ["user", "admin"])
def test_kill_switch_turns_features_off_for_everyone(app, role):
    client = login_as(app.test_client(), create_user(app, "alice", role=role))
    with set_flags(enabled=False, rollout=100):
        assert not priority_sorted(client)
        assert not quick_add_on(client)


def test_role_without_feature_permission_never_gets_the_feature(app, monkeypatch):
    monkeypatch.setitem(authz.ROLE_PERMISSIONS, "user",
                        authz.ROLE_PERMISSIONS["user"] - authz.FEATURE_PERMISSIONS)
    client = login_as(app.test_client(), create_user(app, "alice"))
    with set_flags(enabled=True, rollout=100):
        # Even a crafted query string cannot switch the hidden feature on.
        assert not priority_sorted(client)
        body = client.get("/?sort=priority").data
        assert body.find(b"mid latest") < body.find(b"high later")
        assert not quick_add_on(client)


def test_rollout_applies_to_users_but_admins_bypass_it(app):
    user = login_as(app.test_client(), create_user(app, "alice"))
    admin = login_as(app.test_client(), create_user(app, "root", role="admin"))
    with set_flags(enabled=True, rollout=0):
        assert not priority_sorted(user)
        assert not quick_add_on(user)
        assert priority_sorted(admin)
        assert quick_add_on(admin)


def test_feature_enabled_is_false_without_login(app):
    with app.test_request_context("/"), set_flags(enabled=True, rollout=100):
        app.preprocess_request()
        assert authz.feature_enabled("priority_sort") is False
