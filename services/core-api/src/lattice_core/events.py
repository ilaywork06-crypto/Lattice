"""Publishing side of the event bus (fire-and-forget, never blocks a request)."""

import logging

from lattice_shared.events import Event, EventBus

from lattice_core.config import get_settings

logger = logging.getLogger("lattice_core.events")

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus(get_settings().redis_url)
    return _bus


async def publish_event(event: Event) -> None:
    """Publish an event; swallow errors so notifications never break the API."""
    try:
        await get_event_bus().publish(event)
    except Exception as exc:  # noqa: BLE001 - best-effort side channel
        logger.warning("Failed to publish event %s: %s", event.type, exc)
