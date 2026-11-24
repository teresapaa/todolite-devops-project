import hashlib
import json
from unittest.mock import patch
import flags


def test_sticky_bucket_and_kill_switch(tmp_path):
    path = tmp_path / "flags.json"
    path.write_text(json.dumps({
        "test_flag": {"enabled": True, "rollout": 50},
        "off": {"enabled": False, "rollout": 100},
    }))
    with patch.object(flags, "FLAGS_FILE", path):
        bucket = int(hashlib.sha256(b"test_flag:123").hexdigest(), 16) % 100
        assert flags.is_on("test_flag", 123) is (bucket < 50)
        assert flags.is_on("test_flag", 123) == flags.is_on("test_flag", 123)
        assert not flags.is_on("off", 123)


def test_priority_sort_query_is_server_gated(app):
    client = app.test_client()
    client.post("/signup", data={"username": "user", "password": "secret"})
    client.post("/todos", data={"title": "high earlier", "priority": "5"})
    client.post("/todos", data={"title": "low later", "priority": "1"})
    with patch.object(flags, "load_flags", return_value={"priority_sort": {"enabled": False, "rollout": 100}}):
        response = client.get("/?sort=priority")
        assert response.status_code == 200
        assert response.data.find(b"low later") < response.data.find(b"high earlier")
