import hashlib
import json
from pathlib import Path

FLAGS_FILE = Path(__file__).with_name("flags.json")


def load_flags():
    if not FLAGS_FILE.exists():
        return {}
    return json.loads(FLAGS_FILE.read_text())


def is_enabled(flag_name):
    """Kill switch: False means the feature is off for everyone."""
    flag = load_flags().get(flag_name)
    return bool(flag and flag.get("enabled", False))


def is_on(flag_name, user_id):
    if not is_enabled(flag_name):
        return False
    flag = load_flags()[flag_name]
    bucket = int(hashlib.sha256(f"{flag_name}:{user_id}".encode()).hexdigest(), 16) % 100
    return bucket < max(0, min(100, int(flag.get("rollout", 0))))
