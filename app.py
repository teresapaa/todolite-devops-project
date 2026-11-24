import os
from flask import Flask
from dotenv import load_dotenv
from models import db

load_dotenv()


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
    return app


if __name__ == "__main__":
    create_app().run()
