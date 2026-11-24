"""Homemade feature toggles.

Where the flags live
--------------------
* ``flags.json`` (in the repo) holds the normal state of every flag:
  ``{"flag_name": {"enabled": true, "rollout": 20}}``.
  Changes go through a pull request, so CI tests them before they ship.
* The file is re-read on every check, so editing it on a running server
  takes effect on the next request; no restart and no redeploy.
* ``FLAGS_KILL`` (environment variable, comma separated) is the emergency
  kill switch. Any flag listed there is OFF for everyone, whatever the file
  says. Use it when there is no time for a pull request.

Safety rules
------------
* Unknown flag, missing file or broken JSON → the flag is OFF (fail closed),
  so a bad config never turns an unfinished feature on and never crashes the app.
* Bucketing is sticky: ``SHA-256("flag:user_id") % 100`` puts each user in
  the same bucket every time, so raising the rollout only adds users.
"""
import hashlib
import json
import logging
import os
from pathlib import Path

FLAGS_FILE = Path(__file__).with_name("flags.json")
log = logging.getLogger(__name__)


def load_flags():
    if not FLAGS_FILE.exists():
        return {}
    try:
        data = json.loads(FLAGS_FILE.read_text())
    except (OSError, ValueError) as error:
        log.error("flags.json unreadable, every flag is OFF: %s", error)
        return {}
    return data if isinstance(data, dict) else {}


def killed_flags():
    return {name.strip() for name in os.getenv("FLAGS_KILL", "").split(",") if name.strip()}


def bucket(flag_name, user_id):
    return int(hashlib.sha256(f"{flag_name}:{user_id}".encode()).hexdigest(), 16) % 100


def is_enabled(flag_name):
    """Kill switch: False means the feature is off for everyone (admins included)."""
    if flag_name in killed_flags():
        return False
    flag = load_flags().get(flag_name)
    return isinstance(flag, dict) and flag.get("enabled") is True


def is_on(flag_name, user_id):
    """Kill switch + sticky rollout bucket. Role checks live in authz.feature_enabled()."""
    if not is_enabled(flag_name):
        return False
    try:
        rollout = max(0, min(100, int(load_flags()[flag_name].get("rollout", 0))))
    except (KeyError, TypeError, ValueError):
        return False
    return bucket(flag_name, user_id) < rollout


def variant(flag_name, user_id):
    """'on' or 'off' from the bucket alone (no role check); used by flagctl and logs."""
    return "on" if is_on(flag_name, user_id) else "off"
