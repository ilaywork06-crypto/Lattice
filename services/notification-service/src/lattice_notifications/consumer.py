"""Event consumer — turns Redis events into in-app notifications + emails.

Design:
* ``run_consumer()`` runs for the app's lifetime as a background asyncio task.
* Every event with ``user_id`` recipients yields one ``Notification`` row each.
* Every distinct ``email`` recipient (de-duplicated per event) gets one email.
* Email failures are caught/logged and never bubble up.
* The outer loop reconnects with exponential backoff if Redis drops, so a
  transient Redis outage doesn't kill the task.
"""

from __future__ import annotations

import asyncio
import contextlib

from lattice_shared.events import Event, EventBus
from lattice_shared.logging import configure_logging

from lattice_notifications.config import get_settings
from lattice_notifications.database import SessionLocal
from lattice_notifications.email_sender import send_email
from lattice_notifications.models import Notification

logger = configure_logging("lattice_notifications.consumer")
settings = get_settings()

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


def _persist_notifications(event: Event) -> int:
    """Insert one row per recipient that has a user_id. Runs in a worker thread."""
    recipients = [r for r in event.recipients if r.user_id is not None]
    if not recipients:
        return 0
    db = SessionLocal()
    try:
        for r in recipients:
            db.add(
                Notification(
                    user_id=r.user_id,
                    email=r.email,
                    type=event.type.value,
                    title=event.title,
                    body=event.body,
                    link=event.link,
                )
            )
        db.commit()
        return len(recipients)
    except Exception:
        db.rollback()
        logger.exception("Failed to persist notifications for event %s", event.id)
        return 0
    finally:
        db.close()


async def _send_emails(event: Event) -> None:
    """Send one email per distinct recipient email. Never raises."""
    emails = {r.email for r in event.recipients if r.email}
    for addr in emails:
        try:
            await send_email(addr, event.title, event.body)
            logger.info("Sent email to %s for event %s (%s)", addr, event.id, event.type.value)
        except Exception:
            # A dead SMTP server must not crash the consumer.
            logger.exception("Failed to send email to %s for event %s", addr, event.id)


async def _handle_event(event: Event) -> None:
    logger.info("Handling event %s (%s) → %d recipient(s)",
                event.id, event.type.value, len(event.recipients))
    # DB writes are synchronous SQLAlchemy — offload to a thread so we never
    # block the event loop (also keeps the SQLite session off the loop thread).
    await asyncio.to_thread(_persist_notifications, event)
    await _send_emails(event)


async def run_consumer() -> None:
    """Subscribe to the event bus forever, reconnecting on failure."""
    backoff = _INITIAL_BACKOFF
    logger.info("Starting event consumer (redis=%s, channel=%s)",
                settings.redis_url, EventBus.CHANNEL)
    while True:
        bus = EventBus(settings.redis_url)
        try:
            async for event in bus.subscribe():
                try:
                    await _handle_event(event)
                except Exception:
                    # Guard the whole iteration: one bad event never stops us.
                    logger.exception("Unhandled error processing an event")
                # A clean round-trip means the connection is healthy again.
                backoff = _INITIAL_BACKOFF
            # subscribe() returned normally (connection closed) — reconnect.
            logger.warning("Event stream ended; reconnecting in %.1fs", backoff)
        except asyncio.CancelledError:
            # App shutdown — close and stop.
            with contextlib.suppress(Exception):
                await bus.close()
            logger.info("Event consumer cancelled; shutting down.")
            raise
        except Exception:
            logger.warning(
                "Event consumer lost its Redis connection; reconnecting in %.1fs",
                backoff,
                exc_info=True,
            )
        # Clean up this connection before retrying.
        with contextlib.suppress(Exception):
            await bus.close()
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF)
