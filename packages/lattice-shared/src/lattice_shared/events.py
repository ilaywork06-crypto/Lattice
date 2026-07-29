"""Event bus contract shared between services (Redis pub/sub).

The core-api *publishes* domain events; the notification-service *subscribes*
and turns them into in-app notifications + emails. Keeping the schema here means
both sides agree on the wire format.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

import redis.asyncio as aioredis
from pydantic import BaseModel, Field


class EventType(str, Enum):
    CHANGE_REQUEST_SUBMITTED = "change_request.submitted"
    CHANGE_REQUEST_APPROVED = "change_request.approved"
    CHANGE_REQUEST_REJECTED = "change_request.rejected"
    LOW_STOCK = "inventory.low_stock"
    ITEM_STATE_CHANGED = "item.state_changed"


class Recipient(BaseModel):
    """Who should receive the notification produced from an event."""

    user_id: int | None = None
    email: str | None = None
    role: str | None = None


class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EventType
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Human-facing title/body templates filled by the publisher.
    title: str
    body: str
    # Optional deep-link (frontend route) the notification points at.
    link: str | None = None
    recipients: list[Recipient] = Field(default_factory=list)
    # Free-form structured context (item ids, quantities, etc.).
    payload: dict = Field(default_factory=dict)


class EventBus:
    """Thin async wrapper around Redis pub/sub."""

    CHANNEL = "lattice:events"

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def publish(self, event: Event) -> None:
        await self._redis.publish(self.CHANNEL, event.model_dump_json())

    async def subscribe(self) -> AsyncIterator[Event]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.CHANNEL)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = json.loads(message["data"])
                yield Event.model_validate(data)
        finally:
            await pubsub.unsubscribe(self.CHANNEL)
            await pubsub.aclose()

    async def close(self) -> None:
        await self._redis.aclose()
