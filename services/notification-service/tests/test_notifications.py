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


def test_low_stock_components_reach_the_api_as_data(client, token_for):
    """The component list is what makes the alert readable, so it has to survive
    the trip as structured data — the UI renders a table, not the prose body."""
    event = Event(
        type=EventType.LOW_STOCK,
        title="Low stock: 2 component(s) below minimum",
        body="• FPGA Processing Core (unique) — 3 in stock, minimum 5",
        link="/inventory",
        recipients=[Recipient(user_id=7, email="noa@lattice.io", role="manager")],
        payload={
            "components": [
                {"name": "FPGA Processing Core", "current_quantity": 3, "min_quantity": 5},
                {"name": "COTS Ethernet NIC", "current_quantity": 4, "min_quantity": 6},
            ]
        },
    )
    assert _persist_notifications(event) == 1

    latest = client.get("/notifications", headers=token_for(7)).json()[0]
    assert [c["name"] for c in latest["payload"]["components"]] == [
        "FPGA Processing Core",
        "COTS Ethernet NIC",
    ]


def test_notifications_without_a_payload_stay_null(client, token_for):
    assert _persist_notifications(_event()) == 2
    assert client.get("/notifications", headers=token_for(3)).json()[0]["payload"] is None


def test_email_fanout_never_raises(client):
    # No SMTP server in tests → must be caught and logged, not raised.
    asyncio.run(_send_emails(_event()))


def test_all_read_and_unread_views(client, token_for):
    h = token_for(41)
    for _ in range(3):
        ev = _event()
        ev.recipients = [Recipient(user_id=41)]
        _persist_notifications(ev)
    first = client.get("/notifications", headers=h).json()[0]["id"]
    client.post(f"/notifications/{first}/read", headers=h)

    assert len(client.get("/notifications?status=all", headers=h).json()) == 3
    assert len(client.get("/notifications?status=unread", headers=h).json()) == 2
    read = client.get("/notifications?status=read", headers=h).json()
    assert [n["id"] for n in read] == [first]
    assert client.get("/notifications/count", headers=h).json() == {
        "total": 3, "unread": 2, "read": 1,
    }
    page = client.get("/notifications?limit=2&offset=2", headers=h).json()
    assert len(page) == 1
    assert client.get("/notifications?status=bogus", headers=h).status_code == 422
