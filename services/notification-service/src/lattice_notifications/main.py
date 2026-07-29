"""Lattice notification-service — FastAPI app, event consumer & REST API."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from lattice_shared.logging import configure_logging
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlalchemy.orm import Session

from lattice_notifications.config import get_settings
from lattice_notifications.consumer import run_consumer
from lattice_notifications.database import get_db, init_db
from lattice_notifications.models import Notification
from lattice_notifications.security import get_current_user_id

logger = configure_logging("lattice_notifications")
settings = get_settings()


# ─────────────────────────── Schemas ───────────────────────────
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    body: str
    link: str | None = None
    read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    count: int


# ─────────────────────────── Lifespan ───────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database …")
    init_db()
    logger.info("Starting event consumer task …")
    consumer_task = asyncio.create_task(run_consumer())
    logger.info("Lattice notification-service ready.")
    try:
        yield
    finally:
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task
        logger.info("Lattice notification-service stopped.")


app = FastAPI(
    title="Lattice — Notification Service",
    version="0.1.0",
    description="Consumes domain events and fans out in-app notifications + emails.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────── Routes ───────────────────────────
router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        q = q.filter(Notification.read.is_(False))
    q = q.order_by(Notification.created_at.desc(), Notification.id.desc())
    if limit is not None and limit > 0:
        q = q.limit(limit)
    return q.all()


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read.is_(False))
        .count()
    )
    return UnreadCount(count=count)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if notif is None:
        # Either it doesn't exist or belongs to another user — same 404.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if not notif.read:
        notif.read = True
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read.is_(False))
        .values(read=True)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.include_router(router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "notification-service"}
