
from datetime import datetime
from flask import Blueprint, g, abort, redirect, render_template, request, session, url_for
from sqlalchemy import desc
from models import db, Event, Todo
from flags import is_on<<<<<<< feature-tests
from metrics import record
from authz import get_todo_or_404, require_permission

todos_bp = Blueprint("todos", __name__)

FAST_DELETE_SECONDS = 300  # guardrail H1: a todo deleted this fast was probably junk


def safe_next():
    """Redirect target from the form, limited to local paths (no open redirect)."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("todos.index")


def owned_todo_or_404(todo_id, user_id):
    todo = db.session.get(Todo, todo_id)
    # TODO(team): RBAC roles can replace this owner-only server check.
    if todo is None or todo.user_id != user_id:
        abort(404)
    return todo


def variant_label(enabled):
    return "on" if enabled else "off"


@todos_bp.route("/")
@require_permission("todo:read:own")
def index():
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    # Server-side flag checks happen here, before the query and the template.
    priority_enabled = is_on("priority_sort", user_id)
    nudge = is_on("empty_state_nudge", user_id)
    priority_flag = is_on("priority_flag", user_id)
    query = Todo.query.filter_by(user_id=user_id)
    todos = (query.order_by(desc(Todo.priority), desc(Todo.created_at)).all()
             if priority_enabled else query.order_by(desc(Todo.created_at)).all())

    if not todos:
        # Exposure for H1: the first time this user sees an empty list, per variant.
        record("empty_list_view", "empty_state_nudge", variant_label(nudge), user_id, once=True)
    else:
        record("exposure", "priority_flag", variant_label(priority_flag), user_id, once=True)

    return render_template("index.html", todos=todos, quick_add=is_on("quick_add", user_id),
                           priority_sort=priority_enabled, empty_state_nudge=nudge,
                           priority_flag=priority_flag)


@todos_bp.route("/todos", methods=["POST"])
@require_permission("todo:write:own")
def create():
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
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
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    todo = owned_todo_or_404(todo_id, user_id)
    if not todo.completed:
        todo.completed = True
        todo.completed_at = datetime.utcnow()
        db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.route("/todos/<int:todo_id>/flag", methods=["POST"])
def flag(todo_id):
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    # The real access check: a hidden button is not access control.
    if not is_on("priority_flag", user_id):
        record("flag_denied", "priority_flag", "off", user_id)
        abort(403)
    todo = owned_todo_or_404(todo_id, user_id)
    todo.flagged = not todo.flagged
    db.session.commit()
    record("flag_set" if todo.flagged else "flag_cleared", "priority_flag", "on", user_id)
    return redirect(url_for("todos.index"))


@todos_bp.route("/todos/<int:todo_id>/delete", methods=["POST"])
@require_permission("todo:write:own")
def delete(todo_id):
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    todo = owned_todo_or_404(todo_id, user_id)
    age = (datetime.utcnow() - todo.created_at).total_seconds()
    db.session.delete(todo)
    db.session.commit()
    if age < FAST_DELETE_SECONDS:
        record("todo_deleted_fast", "empty_state_nudge",
               variant_label(is_on("empty_state_nudge", user_id)), user_id, age)
    return redirect(url_for("todos.index"))
