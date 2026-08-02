"""SQLAlchemy ORM models for the notification-service.

A single ``notifications`` table: one row per recipient (with a ``user_id``) of a
consumed event. Email-only recipients don't get a row — they get an email.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lattice_notifications.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    # The event's structured context, kept verbatim so the UI can render a
    # notification as data (e.g. the low-stock component table) instead of
    # re-parsing the prose in ``body``.
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    link: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
