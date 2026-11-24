from flask import Blueprint, g, redirect, render_template, request, url_for
from sqlalchemy import desc
from models import db, Todo
from authz import feature_enabled, get_todo_or_404, require_permission

todos_bp = Blueprint("todos", __name__)


def safe_next():
    """Redirect target from the form, limited to local paths (no open redirect)."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("todos.index")


@todos_bp.route("/")
@require_permission("todo:read:own")
def index():
    # Feature access is decided on the server (kill switch, role permission, rollout);
    # the template only receives the result for the current user.
    priority_enabled = feature_enabled("priority_sort")
    # TODO(team): Emit telemetry/metric events for completion and time-to-first-todo experiments here.
    query = Todo.query.filter_by(user_id=g.user.id)
    # id breaks ties when two todos share the same created_at (coarse clocks on Windows).
    todos = (query.order_by(desc(Todo.priority), desc(Todo.created_at), desc(Todo.id)).all()
             if priority_enabled else query.order_by(desc(Todo.created_at), desc(Todo.id)).all())
    # quick_add is only a keyboard shortcut in the browser; creating todos stays open to
    # every user with todo:write:own, so there is no extra server action to protect.
    return render_template("index.html", todos=todos, quick_add=feature_enabled("quick_add"),
                           priority_sort=priority_enabled)


@todos_bp.route("/todos", methods=["POST"])
@require_permission("todo:write:own")
def create():
    # TODO(team): Server-side feature flag check happens here if create behavior is gated.
    title = request.form.get("title", "").strip()
    try:
        priority = max(1, min(5, int(request.form.get("priority", 3))))
    except ValueError:
        priority = 3
    if title:
        db.session.add(Todo(user_id=g.user.id, title=title, priority=priority))
        db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.route("/todos/<int:todo_id>/complete", methods=["POST"])
@require_permission("todo:write:own")
def complete(todo_id):
    todo = get_todo_or_404(todo_id, "write")
    # TODO(team): Server-side feature flag check happens here if completion behavior is gated.
    todo.completed = True
    db.session.commit()
    return redirect(safe_next())


@todos_bp.route("/todos/<int:todo_id>/delete", methods=["POST"])
@require_permission("todo:write:own")
def delete(todo_id):
    todo = get_todo_or_404(todo_id, "write")
    # TODO(team): Server-side feature flag check happens here if delete behavior is gated.
    db.session.delete(todo)
    db.session.commit()
    return redirect(safe_next())
