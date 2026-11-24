from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User

auth_bp = Blueprint("auth", __name__)


def start_session(user):
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    # New session id after login prevents session fixation.
    current_app.session_interface.regenerate(session)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password are required.")
        elif User.query.filter_by(username=username).first():
            flash("Username already taken.")
        else:
            user = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            start_session(user)
            return redirect(url_for("todos.index"))
    return render_template("signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        # TODO(team): Replace password login here when OAuth is added.
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            start_session(user)
            return redirect(url_for("todos.index"))
        flash("Invalid username or password.")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Clearing a server-side session deletes it from the store.
    session.clear()
    return redirect(url_for("auth.login"))
