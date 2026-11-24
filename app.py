import logging
import os
from flask import Flask, jsonify, session
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from models import db

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

EXPERIMENT_FLAGS = ("empty_state_nudge", "priority_flag")


def add_missing_columns():
    """Tiny migration: older todo.db files predate the toggle columns."""
    existing = {column["name"] for column in inspect(db.engine).get_columns("todo")}
    new_columns = {"flagged": "BOOLEAN NOT NULL DEFAULT 0", "completed_at": "DATETIME"}
    with db.engine.begin() as connection:
        for name, ddl in new_columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE todo ADD COLUMN {name} {ddl}"))


def create_app(test_config=None):
    app = Flask(__name__)
    # Secrets come only from the environment (.env locally, GitHub Secrets in CI/CD).
    # No hardcoded fallback: a known default key would let anyone forge session cookies.
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///todo.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Put it in .env (local) or in GitHub Secrets (CI/CD); "
            "generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    db.init_app(app)

    from auth import auth_bp
    from todos import todos_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(todos_bp)
    with app.app_context():
        db.create_all()
        add_missing_columns()

    @app.get("/healthz")
    def healthz():
        # Lets the operator confirm what the running server sees, e.g. after a kill switch.
        from flags import killed_flags, load_flags
        killed = killed_flags()
        return jsonify(status="ok", flags={
            name: {"enabled": cfg.get("enabled") is True and name not in killed,
                   "rollout": cfg.get("rollout", 0), "killed": name in killed}
            for name, cfg in load_flags().items() if isinstance(cfg, dict)
        })

    @app.errorhandler(500)
    def server_error(error):
        # Guardrail: count server errors per variant of each experiment flag.
        from flags import variant
        from metrics import record
        db.session.rollback()
        user_id = session.get("user_id")
        if user_id is not None:
            for name in EXPERIMENT_FLAGS:
                record("error", name, variant(name, user_id), user_id)
        return "Internal server error", 500

    return app


if __name__ == "__main__":
    create_app().run()
