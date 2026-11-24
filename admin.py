import click
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import desc, func
from authz import require_permission
from models import ROLES, db, Todo, User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def get_other_user_or_404(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == g.user.id:
        # Admins cannot demote or deactivate themselves, so the last admin cannot lock everyone out.
        abort(400)
    return user


@admin_bp.route("/users")
@require_permission("user:manage")
def users():
    rows = (db.session.query(User, func.count(Todo.id))
            .outerjoin(Todo).group_by(User.id).order_by(User.id).all())
    return render_template("admin/users.html", rows=rows, roles=ROLES)


@admin_bp.route("/users/<int:user_id>")
@require_permission("todo:read:any")
def user_todos(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    todos = Todo.query.filter_by(user_id=user.id).order_by(desc(Todo.created_at), desc(Todo.id)).all()
    return render_template("admin/user_todos.html", user=user, todos=todos)


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@require_permission("user:manage")
def set_role(user_id):
    user = get_other_user_or_404(user_id)
    role = request.form.get("role", "")
    if role not in ROLES:
        abort(400)
    user.role = role
    db.session.commit()
    flash(f"{user.email} is now {role}.")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/active", methods=["POST"])
@require_permission("user:manage")
def set_active(user_id):
    user = get_other_user_or_404(user_id)
    user.is_active = request.form.get("active") == "1"
    db.session.commit()
    flash(f"{user.email} {'activated' if user.is_active else 'deactivated'}.")
    return redirect(url_for("admin.users"))


@admin_bp.cli.command("set-role")
@click.argument("email")
@click.argument("role", type=click.Choice(ROLES))
def set_role_command(email, role):
    """Assign ROLE to the user with EMAIL (bootstraps the first admin)."""
    user = User.query.filter_by(email=email.strip().lower()).first()
    if user is None:
        raise click.ClickException(f"No user {email!r}. The user has to sign in once first.")
    user.role = role
    db.session.commit()
    click.echo(f"{user.email} is now {role}.")
