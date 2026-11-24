import os
from datetime import timedelta
from cachelib import FileSystemCache
from flask import Flask
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from models import db

load_dotenv()

csrf = CSRFProtect()


def env_flag(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


def create_app(test_config=None):
    app = Flask(__name__)
    # Secrets come only from the environment (.env locally, GitHub Secrets in CI/CD).
    # No hardcoded fallback: a known default key would let anyone forge CSRF tokens.
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///todo.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Server-side sessions: the cookie only carries a random session id, the data
    # lives on the server, so logout really invalidates the session.
    app.config.update(
        SESSION_TYPE="cachelib",
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        # Secure by default; set SESSION_COOKIE_SECURE=false only for local http.
        SESSION_COOKIE_SECURE=env_flag("SESSION_COOKIE_SECURE", True),
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Put it in .env (local) or in GitHub Secrets (CI/CD); "
            "generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    if "SESSION_CACHELIB" not in app.config:
        # File-based store under instance/ (git-ignored); shared by all workers on one host.
        app.config["SESSION_CACHELIB"] = FileSystemCache(
            os.path.join(app.instance_path, "sessions"),
            threshold=5000,
            default_timeout=int(app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()),
        )

    db.init_app(app)
    Session(app)
    csrf.init_app(app)

    from auth import auth_bp
    from authz import authz_bp
    from todos import todos_bp
    app.register_blueprint(authz_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(todos_bp)
    with app.app_context():
        db.create_all()
    return app


if __name__ == "__main__":
    create_app().run()
