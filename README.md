# DevOps-project
DevOps-project
===============

A minimal Flask + SQLite todo-list scaffold.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

## Tests and lint

```bash
ruff check .
pytest
```

## Demo data

Run `python seed.py` to reset and seed 20 demo users. Each username is `demo1`
through `demo20`; the password for every demo user is `demo`.

## Feature flags

`flags.json` controls `quick_add` and `priority_sort`. Both flags support an
enabled kill switch and a 0–100 rollout percentage. Bucketing is sticky:
`SHA-256("flag_name:user_id") % 100` determines membership. The server checks
flags in todo routes, and the UI only receives feature state for the current
user.

- `quick_add`: the `n` key focuses the add-todo input.
- `priority_sort`: todos are sorted by priority descending; otherwise they are
  sorted by creation time descending. A `sort=priority` query parameter is
  ignored when this flag is off.

### Experiment flags (Task 3)

| Flag | ON | OFF |
| --- | --- | --- |
| `empty_state_nudge` | Empty list shows "Add your first todo to get started", input is auto-focused | "No todos yet." |
| `priority_flag` | One-click 🚩 button per todo, flagged rows turn red | No button; `POST /todos/<id>/flag` returns **403** |

Flagged state stays in the database while the flag is OFF, so switching back loses nothing.

### Operating the toggles

```bash
python flagctl.py status                          # config + ON/OFF per demo user (sticky bucket)
python flagctl.py set priority_flag --rollout 20  # gradual rollout
python flagctl.py set priority_flag --on          # enable (keeps rollout)
python flagctl.py kill priority_flag              # kill switch: OFF for everyone
python flagctl.py report                          # success + guardrail metrics per variant
```

- `flags.json` is re-read on every request: changes apply without a restart.
- Emergency kill switch without touching the file: `FLAGS_KILL=priority_flag,empty_state_nudge`
  (PowerShell: `$env:FLAGS_KILL="priority_flag"; python app.py`).
- `GET /healthz` shows what the running server sees (enabled, rollout, killed).
- Broken or missing `flags.json` → every flag is OFF (fail closed), the app keeps running.
- Normal changes to `flags.json` go through a pull request; CI runs
  `tests/test_experiment_flags.py`, which also validates the shipped file.

## Secrets

- Locally: `cp .env.example .env` and set `SECRET_KEY` (`.env` is git-ignored).
  Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
- CI/CD: `SECRET_KEY` is stored in **GitHub → Settings → Environments → production**
  and injected as an environment variable by `.github/workflows/ci.yml`.
- The app refuses to start without `SECRET_KEY` (no hardcoded fallback).
- Secret scanning with push protection is enabled: commits containing tokens are blocked.
