import json
import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.app import create_app
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import Role
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.orders.domain.models import Choice

live_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)
PATH = "/api/v1/staff/events"


def wait_listening(client: TestClient) -> None:
    hub = client.app.state.hub  # type: ignore[attr-defined]
    for _ in range(100):
        if hub.listening:
            return
        time.sleep(0.05)
    raise AssertionError("Слушатель PostgreSQL не подключился")


def next_event(ws: object, topic: str, kind: str = "") -> dict[str, str]:
    for _ in range(50):
        message = json.loads(ws.receive_text())  # type: ignore[attr-defined]
        if (
            message["topic"] == topic
            and message["kind"] != "resync"
            and (not kind or message["kind"] == kind)
        ):
            return dict(message)
    raise AssertionError("Событие не получено")


def test_committed_order_reaches_kitchen_socket_without_pickup_code(
    live_system: System, system: tuple[Settings, IdentityService, str]
) -> None:
    s = live_system
    origin = s.settings.allowed_origins[0]
    with TestClient(create_app(s.settings)) as client:
        wait_listening(client)
        with (
            pytest.raises(WebSocketDisconnect) as missing,
            client.websocket_connect(PATH, headers={"origin": origin}) as ws,
        ):
            ws.receive_text()
        assert missing.value.code == 4401
        client.cookies.set(s.settings.session_cookie, s.token)
        with (
            pytest.raises(WebSocketDisconnect) as foreign,
            client.websocket_connect(PATH, headers={"origin": "https://evil.test"}) as ws,
        ):
            ws.receive_text()
        assert foreign.value.code == 4403
        with client.websocket_connect(PATH, headers={"origin": origin}) as ws:
            entry, slot, _ = s.setup()
            guest = s.guest()
            draft = s.buy(guest, entry, slot)
            order = s.service.mock_payment(guest, draft.id, uuid4(), "success")
            event = next_event(ws, "orders", "confirmed")
            assert event["id"] == str(order.id)
            assert order.pickup_code and order.pickup_code not in json.dumps(event)

        _, identity, password = system
        keeper = identity.create_staff(
            s.token, "Склад", f"store.{uuid4().hex[:8]}", password, frozenset({Role.STOREKEEPER})
        )
        client.cookies.set(
            s.settings.session_cookie, identity.login(keeper.login, password, "live")[1]
        )
        with client.websocket_connect(PATH, headers={"origin": origin}) as ws:
            # Receiving stock writes a movement; the storekeeper sees the stock signal.
            s.setup()
            assert next_event(ws, "stock")["topic"] == "stock"


def test_failed_checkout_sends_nothing_before_next_real_change(live_system: System) -> None:
    s = live_system
    origin = s.settings.allowed_origins[0]
    entry, slot, _ = s.setup("1")
    with TestClient(create_app(s.settings)) as client:
        wait_listening(client)
        client.cookies.set(s.settings.session_cookie, s.token)
        with client.websocket_connect(PATH, headers={"origin": origin}) as ws:
            with pytest.raises(InventoryError):
                s.service.checkout(s.guest(), uuid4(), slot, [Choice(entry, 5, 12345)])
            draft = s.buy(s.guest(), entry, slot)
            event = next_event(ws, "orders", "created")
            assert event["id"] == str(draft.id)


def test_guest_socket_receives_own_ready_status_only(live_system: System) -> None:
    s = live_system
    origin = s.settings.allowed_origins[0]
    entry, slot, _ = s.setup()
    guest = s.guest()
    other = s.guest()
    order = s.service.mock_payment(guest, s.buy(guest, entry, slot).id, uuid4(), "success")
    foreign = s.service.mock_payment(other, s.buy(other, entry, slot).id, uuid4(), "success")
    with TestClient(create_app(s.settings)) as client:
        wait_listening(client)
        client.cookies.set(s.settings.guest_cookie, guest)
        with client.websocket_connect("/api/v1/orders/live", headers={"origin": origin}) as ws:
            for target in ("preparing", "ready"):
                s.service.transition(s.token, foreign.id, uuid4(), target, foreign.version)
                foreign = s.service.staff_order(s.token, foreign.id)
                s.service.transition(s.token, order.id, uuid4(), target, order.version)
                order = s.service.staff_order(s.token, order.id)
            seen = [next_event(ws, "orders") for _ in range(2)]
            assert [e["kind"] for e in seen] == ["preparing", "ready"]
            assert all(e["id"] == str(order.id) for e in seen)
            assert "guest" not in json.dumps(seen)
