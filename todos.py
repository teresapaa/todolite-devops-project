from datetime import datetime
from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from sqlalchemy import desc
from models import db, Todo
from authz import feature_enabled, get_todo_or_404, require_permission

todos_bp = Blueprint("todos", __name__)

FAST_DELETE_SECONDS = 300  # guardrail H1: a todo deleted this fast was probably junk


def safe_next():
    """Redirect target from the form, limited to local paths (no open redirect)."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("todos.index")


def variant_label(enabled):
    return "on" if enabled else "off"


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
    user_id = g.user.id
    title = request.form.get("title", "").strip()
    try:
        priority = max(1, min(5, int(request.form.get("priority", 3))))
    except ValueError:
        priority = 3
    if title:
        is_first = Todo.query.filter_by(user_id=user_id).first() is None
        db.session.add(Todo(user_id=user_id, title=title, priority=priority))
        db.session.commit()

        nudge_variant = variant_label(is_on("empty_state_nudge", user_id))
        record("todo_created", "empty_state_nudge", nudge_variant, user_id)
        if is_first:
            # Success metric H1: seconds from first empty-list view to first todo.
            seen = (Event.query.filter_by(name="empty_list_view", flag="empty_state_nudge",
                                          user_id=user_id)
                    .order_by(Event.created_at).first())
            seconds = (datetime.utcnow() - seen.created_at).total_seconds() if seen else None
            record("first_todo", "empty_state_nudge", nudge_variant, user_id, seconds)
    return redirect(url_for("todos.index"))


@todos_bp.route("/todos/<int:todo_id>/complete", methods=["POST"])
@require_permission("todo:write:own")
def complete(todo_id):
    todo = get_todo_or_404(todo_id, "write")
    if not todo.completed:
        todo.completed = True
        todo.completed_at = datetime.utcnow()
        db.session.commit()
    return redirect(safe_next())


@todos_bp.route("/todos/<int:todo_id>/flag", methods=["POST"])
@require_permission("todo:write:own")
def flag(todo_id):
    user_id = g.user.id
    # The real access check: a hidden button is not access control.
    if not is_on("priority_flag", user_id):
        record("flag_denied", "priority_flag", "off", user_id)
        abort(403)
    todo = get_todo_or_404(todo_id, "write")
    todo.flagged = not todo.flagged
    db.session.commit()
    record("flag_set" if todo.flagged else "flag_cleared", "priority_flag", "on", user_id)
    return redirect(safe_next())


@todos_bp.route("/todos/<int:todo_id>/delete", methods=["POST"])
@require_permission("todo:write:own")
def delete(todo_id):
    user_id = g.user.id
    todo = get_todo_or_404(todo_id, "write")
    age = (datetime.utcnow() - todo.created_at).total_seconds()
    db.session.delete(todo)
    db.session.commit()
    if age < FAST_DELETE_SECONDS:
        record("todo_deleted_fast", "empty_state_nudge",
               variant_label(is_on("empty_state_nudge", user_id)), user_id, age)
    return redirect(safe_next())
