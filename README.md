# DevOps-project
DevOps-project
===============

A minimal Flask + SQLite todo-list scaffold.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in SECRET_KEY and the Google client (see below)
python app.py
```

Open `http://localhost:5000` (use the same host as the redirect URI registered
at Google, otherwise Google rejects the login).

## Google login (one-time setup)

1. [Google Cloud Console](https://console.cloud.google.com/) → create or pick a project.
2. **APIs & Services → OAuth consent screen**: user type *External*, add app
   name and support email. While the app is in *Testing*, only the listed
   test users can sign in. Add your team there, or publish the app.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**,
   type *Web application*, authorized redirect URIs:
   - `http://localhost:5000/auth/callback` (local)
   - `https://<your-domain>/auth/callback` (production)
4. Put the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`.
5. Sign in once, then make yourself admin:
   `flask --app app admin set-role you@gmail.com admin`

## Authentication and authorization

- **OIDC:** Sign-in uses Google with the authorization code flow and PKCE
  (Authlib). The state, the nonce and the ID token's signature, issuer,
  audience and expiry are checked before any account lookup. Accounts are keyed
  by the token's `(iss, sub)` pair. Email and name are only profile data and
  are refreshed on every login. The first login creates the account with role
  `user`. Unverified emails are rejected. `ALLOWED_EMAIL_DOMAINS` can limit
  sign-in to certain domains.
- **Server-side sessions:** Flask-Session keeps session data in
  `instance/sessions`. The cookie holds only a random id and is HttpOnly,
  SameSite=Lax and Secure outside local dev, with an 8 h lifetime. The id is
  regenerated on login, and logout deletes the session on the server. Google
  has no RP-initiated logout, so the Google session itself stays signed in.
- **RBAC:** `authz.py` maps roles to permissions:

  | Role | Permissions |
  |---|---|
  | `user` | `todo:read:own`, `todo:write:own` |
  | `admin` | additionally `todo:read:any`, `todo:write:any`, `user:manage` |

  Roles live in the database, never in the session or token. The current user
  is reloaded on every request, so role changes and deactivations apply
  immediately. Admins manage roles and accounts under `/admin/users`.
- **Server-side checks:** Every route is guarded by `require_permission`.
  Object access goes through `get_todo_or_404`, which checks ownership or the
  `any` permission and answers 404 so foreign ids cannot be probed. Hidden
  buttons in templates are cosmetic only. All POST forms carry a CSRF token
  (Flask-WTF).
- Behind a reverse proxy (TLS termination), wrap the app in Werkzeug's
  `ProxyFix` so the callback URL is built with `https`.

## Tests and lint

```bash
ruff check .
pytest
```

## Demo data

Run `python seed.py` to reset the database and seed 20 demo users (`demo1` to
`demo20`) with todos. Nobody can sign in as these users. They only fill the
admin area. **Warning:** seeding drops all tables, including real accounts.

There are no migrations, except that the startup adds the `todo.flagged` and
`todo.completed_at` toggle columns to older databases. After any other model
change, delete `instance/todo.db`. It is recreated on the next start.

## Feature flags

`flags.json` controls `quick_add` and `priority_sort`. Both flags support an
enabled kill switch and a 0–100 rollout percentage. Bucketing is sticky:
`SHA-256("flag_name:user_id") % 100` determines membership. The server checks
flags in todo routes, and the UI only receives feature state for the current
user.

Who gets a feature is decided on the server by `authz.feature_enabled()`, in
this order:

1. **Kill switch:** with `enabled: false` the feature is off for everyone,
   admins included.
2. **Role permission:** the role needs `feature:<flag>`. Both `user` and
   `admin` have it, anonymous and deactivated users never get a feature.
3. **Rollout bucket:** users are bucketed as described above. Roles with
   `feature:bypass_rollout` (admins) skip the bucket, so QA and demos can
   always see the ON state.

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
python flagctl.py status                          # config + ON/OFF per user (sticky bucket)
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

- Locally: `cp .env.example .env` and set `SECRET_KEY`, `GOOGLE_CLIENT_ID` and
  `GOOGLE_CLIENT_SECRET` (`.env` is git-ignored).
  Generate the key with `python -c "import secrets; print(secrets.token_hex(32))"`.
- CI/CD: `SECRET_KEY`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are stored in
  **GitHub → Settings → Environments → production** and injected as environment
  variables by `.github/workflows/ci.yml`.
- The app refuses to start without these values (no hardcoded fallback).
- Secret scanning with push protection is enabled: commits containing tokens are blocked.
