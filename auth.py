"""Login via Google (OpenID Connect, authorization code flow with PKCE).

Google proves who the user is; what the user may do is decided by our own database
(see authz.py)."""
from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import (Blueprint, current_app, flash, g, redirect, render_template, session,
                   url_for)
from models import db, User

auth_bp = Blueprint("auth", __name__)

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def init_oauth(app):
    # One OAuth registry per app: Authlib caches clients on the registry, so a module-level
    # instance would keep the configuration of the first app it saw.
    oauth = OAuth(app)
    # Client id and secret are read from app.config["GOOGLE_CLIENT_ID" / "GOOGLE_CLIENT_SECRET"].
    oauth.register(
        "google",
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )


def google():
    return current_app.extensions["authlib.integrations.flask_client"].google


def email_allowed(email):
    domains = current_app.config.get("ALLOWED_EMAIL_DOMAINS") or []
    return not domains or email.rsplit("@", 1)[-1].lower() in domains


def start_session(user):
    session.clear()
    session["user_id"] = user.id
    # New session id after login prevents session fixation.
    current_app.session_interface.regenerate(session)


@auth_bp.route("/login")
def login():
    if g.get("user") is not None:
        return redirect(url_for("todos.index"))
    return render_template("login.html")


@auth_bp.route("/login/google")
def login_google():
    # Authlib stores state, nonce and the PKCE verifier in the (server-side) session.
    return google().authorize_redirect(url_for("auth.callback", _external=True))


@auth_bp.route("/auth/callback")
def callback():
    try:
        # Exchanges the code and validates state, nonce and the ID token
        # (signature against Google's JWKS, iss, aud, exp).
        token = google().authorize_access_token()
    except OAuthError as error:
        current_app.logger.warning("OIDC login failed: %s", error)
        flash("Login with Google failed. Please try again.")
        return redirect(url_for("auth.login"))

    claims = token.get("userinfo")
    if not claims or not claims.get("email") or not claims.get("email_verified"):
        flash("Your Google account needs a verified email address.")
        return redirect(url_for("auth.login"))
    email = claims["email"].lower()
    if not email_allowed(email):
        flash("This Google account is not allowed to sign in.")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(oidc_issuer=claims["iss"], oidc_sub=claims["sub"]).first()
    if user is None:
        # Just-in-time provisioning: the first login creates the account with the default role.
        user = User(oidc_issuer=claims["iss"], oidc_sub=claims["sub"], role="user")
        db.session.add(user)
    # Keep profile data in sync with Google; never derive the role from the token.
    user.email = email
    user.name = claims.get("name") or email
    db.session.commit()

    if not user.is_active:
        flash("Your account has been deactivated.")
        return redirect(url_for("auth.login"))
    start_session(user)
    return redirect(url_for("todos.index"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Clearing a server-side session deletes it from the store. Google offers no
    # RP-initiated logout, so the Google session itself stays signed in.
    # No flash() here: it would write into the session again and keep the old id alive.
    session.clear()
    return redirect(url_for("auth.login"))
