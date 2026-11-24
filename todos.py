from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from sqlalchemy import desc
from models import db, Todo
from flags import is_on

todos_bp = Blueprint("todos", __name__)


def current_user_id():
    return session.get("user_id")


@todos_bp.route("/")
def index():
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    # TODO(team): Server-side flag check happens here before constructing the todo query.
    priority_enabled = is_on("priority_sort", user_id)
    # TODO(team): Emit telemetry/metric events for completion and time-to-first-todo experiments here.
    query = Todo.query.filter_by(user_id=user_id)
    # id breaks ties when two todos share the same created_at (coarse clocks on Windows).
    todos = (query.order_by(desc(Todo.priority), desc(Todo.created_at), desc(Todo.id)).all()
             if priority_enabled else query.order_by(desc(Todo.created_at), desc(Todo.id)).all())
    return render_template("index.html", todos=todos, quick_add=is_on("quick_add", user_id),
                           priority_sort=priority_enabled)


@todos_bp.route("/todos", methods=["POST"])
def create():
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    # TODO(team): Server-side feature flag check happens here if create behavior is gated.
    title = request.form.get("title", "").strip()
    try:
        priority = max(1, min(5, int(request.form.get("priority", 3))))
    except ValueError:
        priority = 3
    if title:
        db.session.add(Todo(user_id=user_id, title=title, priority=priority))
        db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.route("/todos/<int:todo_id>/complete", methods=["POST"])
def complete(todo_id):
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    todo = db.session.get(Todo, todo_id)
    # TODO(team): RBAC roles can replace this owner-only server check.
    if todo is None or todo.user_id != user_id:
        abort(404)
    # TODO(team): Server-side feature flag check happens here if completion behavior is gated.
    todo.completed = True
    db.session.commit()
    return redirect(url_for("todos.index"))


@todos_bp.route("/todos/<int:todo_id>/delete", methods=["POST"])
def delete(todo_id):
    user_id = current_user_id()
    if user_id is None:
        return redirect(url_for("auth.login"))
    todo = db.session.get(Todo, todo_id)
    # TODO(team): RBAC roles can replace this owner-only server check.
    if todo is None or todo.user_id != user_id:
        abort(404)
    # TODO(team): Server-side feature flag check happens here if delete behavior is gated.
    db.session.delete(todo)
    db.session.commit()
    return redirect(url_for("todos.index"))
