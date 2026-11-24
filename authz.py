"""Role-based access control. Every check here runs on the server; templates may use
can() to hide buttons, but that is cosmetic and never replaces these checks."""
from functools import wraps
from flask import Blueprint, abort, g, redirect, session, url_for
import flags
from models import db, Todo, User

authz_bp = Blueprint("authz", __name__)

# Permissions are "<resource>:<action>:<scope>". "own" means the user's own objects,
# "any" means objects of every user. "feature:<flag>" allows a role to take part in a
# toggled feature; "feature:bypass_rollout" skips the rollout bucket (for QA and demos).
FEATURES = ("quick_add", "priority_sort")
FEATURE_PERMISSIONS = frozenset(f"feature:{name}" for name in FEATURES)

ROLE_PERMISSIONS = {
    "user": frozenset({"todo:read:own", "todo:write:own"}) | FEATURE_PERMISSIONS,
    "admin": frozenset({
        "todo:read:own", "todo:write:own",
        "todo:read:any", "todo:write:any",
        "user:manage",
        "feature:bypass_rollout",
    }) | FEATURE_PERMISSIONS,
}


@authz_bp.before_app_request
def load_current_user():
    """Load the user from the database on every request instead of trusting session data."""
    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id is not None else None
    if g.user is not None and not g.user.is_active:
        # Deactivated users lose their session immediately.
        session.clear()
        g.user = None


@authz_bp.app_context_processor
def inject_authz():
    return {"can": can, "feature_enabled": feature_enabled, "current_user": g.get("user")}


def can(permission):
    user = g.get("user")
    return user is not None and permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def feature_enabled(name):
    """Decide on the server whether the current user gets a toggled feature.

    Order: kill switch (off for everyone, admins included) -> role permission ->
    sticky rollout bucket (skipped by roles with feature:bypass_rollout)."""
    user = g.get("user")
    if user is None or not flags.is_enabled(name) or not can(f"feature:{name}"):
        return False
    if can("feature:bypass_rollout"):
        return True
    return flags.is_on(name, user.id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def require_permission(permission):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not can(permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_todo_or_404(todo_id, action):
    """Return the todo if the current user may perform action ("read" or "write") on it.

    Answers 404 instead of 403 so that foreign todo ids cannot be enumerated."""
    todo = db.session.get(Todo, todo_id)
    if todo is None:
        abort(404)
    if todo.user_id == g.user.id and can(f"todo:{action}:own"):
        return todo
    if can(f"todo:{action}:any"):
        return todo
    abort(404)
