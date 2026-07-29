"""Behavioural tests for the notification-service REST + event fan-out."""

import asyncio

from lattice_notifications.consumer import _persist_notifications, _send_emails
from lattice_shared.events import Event, EventType, Recipient


def _event() -> Event:
    return Event(
        type=EventType.CHANGE_REQUEST_SUBMITTED,
        title="New change request",
        body="Please review CR #7",
        link="/change-requests/7",
        recipients=[
            Recipient(user_id=2, email="noa@lattice.io", role="manager"),
            Recipient(user_id=3, role="manager"),
        ],
    )


def test_health(client):
    assert client.get("/health").json()["service"] == "notification-service"


def test_requires_auth(client):
    assert client.get("/notifications").status_code == 401


def test_persist_and_list(client, token_for):
    assert _persist_notifications(_event()) == 2  # 2 recipients with user_id
    lst = client.get("/notifications", headers=token_for(2)).json()
    assert len(lst) == 1
    assert lst[0]["read"] is False
    assert lst[0]["link"] == "/change-requests/7"


def test_unread_count_and_mark_read(client, token_for):
    h = token_for(2)
    before = client.get("/notifications/unread-count", headers=h).json()["count"]
    assert before >= 1
    nid = client.get("/notifications", headers=h).json()[0]["id"]
    assert client.post(f"/notifications/{nid}/read", headers=h).status_code == 204
    assert client.get("/notifications/unread-count", headers=h).json()["count"] == before - 1


def test_cannot_read_others_notification(client, token_for):
    nid = client.get("/notifications", headers=token_for(2)).json()[0]["id"]
    assert client.post(f"/notifications/{nid}/read", headers=token_for(99)).status_code == 404


def test_read_all(client, token_for):
    h = token_for(2)
    _persist_notifications(_event())
    assert client.get("/notifications/unread-count", headers=h).json()["count"] >= 1
    assert client.post("/notifications/read-all", headers=h).status_code == 204
    assert client.get("/notifications/unread-count", headers=h).json()["count"] == 0


def test_email_fanout_never_raises(client):
    # No SMTP server in tests → must be caught and logged, not raised.
    asyncio.run(_send_emails(_event()))
