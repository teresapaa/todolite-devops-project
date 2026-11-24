from datetime import datetime
from typing import Optional
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

db = SQLAlchemy()

ROLES = ("user", "admin")


class User(db.Model):
    # Accounts are identified by the OIDC issuer + subject pair. The subject is stable per
    # provider; email addresses can change or be reassigned, so they are only profile data.
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_sub"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    oidc_issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    oidc_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The role lives in our database, never in the session or an identity token,
    # so a role change or a deactivation takes effect on the very next request.
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    todos: Mapped[list["Todo"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Todo(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    # priority_flag: kept in the DB when the toggle is OFF, so nothing is lost on switch-back.
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    user: Mapped["User"] = relationship(back_populates="todos")


class Event(db.Model):
    """One monitoring event, tagged with the flag and the variant the user saw."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    flag: Mapped[str] = mapped_column(String(50), nullable=False)
    variant: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(nullable=True)
