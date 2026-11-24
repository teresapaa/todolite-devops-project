"""Operator tool for the feature toggles.

  python flagctl.py status                         flags + which variant each user gets
  python flagctl.py set priority_flag --on         turn a flag on (keeps its rollout)
  python flagctl.py set priority_flag --rollout 20 roll out to 20% of users
  python flagctl.py kill priority_flag             kill switch: OFF for everyone
  python flagctl.py report                         success + guardrail metrics per variant

The server re-reads flags.json on every request, so changes apply without a restart.
"""
import argparse
import json
import os
import sys
from datetime import timedelta
from statistics import median

import flags

SUCCESS_SECONDS = 60          # H1: first todo within 60 s
COMPLETE_WINDOW = timedelta(days=7)  # H2: completed within 7 days


def write_flags(data):
    tmp = flags.FLAGS_FILE.with_suffix(".json.tmp")
    lines = ",\n".join(f'  "{name}": {json.dumps(cfg)}' for name, cfg in data.items())
    tmp.write_text("{\n" + lines + "\n}\n")
    os.replace(tmp, flags.FLAGS_FILE)  # atomic: the server never reads a half-written file


def app_context():
    from app import create_app
    return create_app().app_context()


def cmd_status(_args):
    data, killed = flags.load_flags(), flags.killed_flags()
    print(f"flags file: {flags.FLAGS_FILE}")
    print(f"FLAGS_KILL: {', '.join(sorted(killed)) or '(none)'}\n")
    print(f"{'flag':<20}{'enabled':<10}{'rollout':<10}state")
    for name, cfg in data.items():
        state = "KILLED (env)" if name in killed else ("live" if cfg.get("enabled") else "off")
        print(f"{name:<20}{str(cfg.get('enabled')):<10}{str(cfg.get('rollout')) + '%':<10}{state}")

    from models import User
    with app_context():
        users = User.query.order_by(User.id).all()
        if not users:
            return
        width = max(len(u.email) for u in users) + 2
        print(f"\n{'user':<{width}}{'role':<8}" + "".join(f"{n:<20}" for n in data))
        for user in users:
            cells = "".join(effective(n, user).ljust(20) for n in data)
            print(f"{user.email:<{width}}{user.role:<8}{cells}")
        print("\nb = sticky bucket 0-99; a user is ON when b < rollout. Admins bypass the rollout "
              "(feature:bypass_rollout),\nbut the kill switch turns the feature off for them too.")


def effective(name, user):
    """Same decision as authz.feature_enabled(), for a user outside a request."""
    from authz import ROLE_PERMISSIONS
    perms = ROLE_PERMISSIONS.get(user.role, frozenset())
    b = f"(b={flags.bucket(name, user.id):02d})"
    if not flags.is_enabled(name):
        return f"OFF {b}"
    if f"feature:{name}" not in perms:
        return "OFF (role)"
    if "feature:bypass_rollout" in perms:
        return "ON (admin)"
    return f"{flags.variant(name, user.id).upper()} {b}"


def cmd_set(args):
    data = flags.load_flags()
    cfg = data.setdefault(args.flag, {"enabled": False, "rollout": 0})
    if args.on:
        cfg["enabled"] = True
    if args.off:
        cfg["enabled"] = False
    if args.rollout is not None:
        if not 0 <= args.rollout <= 100:
            sys.exit("rollout must be 0-100")
        cfg["rollout"] = args.rollout
    write_flags(data)
    print(f"{args.flag}: {json.dumps(cfg)}")


def cmd_kill(args):
    args.on, args.off, args.rollout = False, True, None
    cmd_set(args)
    print("Kill switch active: the next request sees the feature OFF for every user.")


def pct(part, whole):
    return f"{100 * part / whole:5.1f}%" if whole else "   n/a"


def cmd_report(_args):
    from models import Event, Todo
    with app_context():
        def events(name, flag, var):
            return Event.query.filter_by(name=name, flag=flag, variant=var).all()

        print("H1  empty_state_nudge  (success: first todo within 60 s; "
              "guardrails: fast deletes, errors)")
        print(f"  {'variant':<8}{'users':>6}{'1st todo':>10}{'<=60s':>8}{'median s':>10}"
              f"{'created':>9}{'fast del':>10}{'errors':>8}")
        for var in ("off", "on"):
            users = {e.user_id for e in events("empty_list_view", "empty_state_nudge", var)}
            firsts = [e for e in events("first_todo", "empty_state_nudge", var) if e.value is not None]
            fast = [e for e in firsts if e.value <= SUCCESS_SECONDS]
            created = len(events("todo_created", "empty_state_nudge", var))
            deleted = len(events("todo_deleted_fast", "empty_state_nudge", var))
            errors = len(events("error", "empty_state_nudge", var))
            med = f"{median(e.value for e in firsts):.1f}" if firsts else "n/a"
            print(f"  {var:<8}{len(users):>6}{len(firsts):>10}{pct(len(fast), len(users)):>8}"
                  f"{med:>10}{created:>9}{pct(deleted, created):>10}{errors:>8}")

        print("\nH2  priority_flag  (success: flagged todos completed within 7 days more often; "
              "guardrails: overall completion, errors, server denials)")
        print(f"  {'variant':<8}{'users':>6}{'group':>12}{'todos':>7}{'done<=7d':>10}{'errors':>8}{'denied':>8}")
        for var in ("off", "on"):
            users = {e.user_id for e in events("exposure", "priority_flag", var)}
            todos = Todo.query.filter(Todo.user_id.in_(users)).all() if users else []
            groups = {"all": todos}
            if var == "on":
                groups["flagged"] = [t for t in todos if t.flagged]
                groups["unflagged"] = [t for t in todos if not t.flagged]
            errors = len(events("error", "priority_flag", var))
            denied = len(Event.query.filter_by(name="flag_denied", flag="priority_flag").all()) if var == "off" else 0
            for i, (group, items) in enumerate(groups.items()):
                done = [t for t in items if t.completed_at and t.completed_at - t.created_at <= COMPLETE_WINDOW]
                head = (f"  {var:<8}{len(users):>6}" if i == 0 else " " * 16)
                tail = f"{errors:>8}{denied:>8}" if i == 0 else ""
                print(f"{head}{group:>12}{len(items):>7}{pct(len(done), len(items)):>10}{tail}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p_set = sub.add_parser("set")
    p_set.add_argument("flag")
    group = p_set.add_mutually_exclusive_group()
    group.add_argument("--on", action="store_true")
    group.add_argument("--off", action="store_true")
    p_set.add_argument("--rollout", type=int)
    p_set.set_defaults(func=cmd_set)
    p_kill = sub.add_parser("kill")
    p_kill.add_argument("flag")
    p_kill.set_defaults(func=cmd_kill)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
