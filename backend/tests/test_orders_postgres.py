import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from test_identity_postgres import headers

from ashana.bootstrap.app import create_app
from ashana.bootstrap.catalog import catalog_service
from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.inventory import inventory_service
from ashana.bootstrap.orders import order_service
from ashana.bootstrap.settings import Settings
from ashana.modules.catalog.application.service import CatalogService
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.inventory.infrastructure.database import batches
from ashana.modules.inventory.infrastructure.reservations import reservations
from ashana.modules.notifications.infrastructure.delivery import DeliveryFailed, deliver_one, outbox
from ashana.modules.orders.application.service import OrderService
from ashana.modules.orders.domain.models import Choice, Order, short_number
from ashana.modules.orders.infrastructure.database import (
    PostgresOrderRepository,
    drafts,
    orders,
    slots,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


@dataclass
class System:
    settings: Settings
    engine: Engine
    service: OrderService
    catalog: CatalogService
    stock: InventoryService
    token: str
    now: datetime

    def guest(self) -> str:
        result = self.service.start_guest("")
        assert result
        return result

    def setup(
        self, count: str = "10", capacity: int = 10, name: str | None = None
    ) -> tuple[UUID, UUID, UUID]:
        period = self.catalog.save_period(
            self.token,
            uuid4(),
            None,
            0,
            name or f"Период {uuid4()}",
            self.now - timedelta(hours=1),
            self.now + timedelta(hours=4),
            True,
        ).subject_id
        item = self.stock.create_item(
            self.token, uuid4(), name or f"Заказной товар {uuid4()}", "purchased", "pcs"
        ).subject_id
        batch = self.stock.receive(
            self.token,
            uuid4(),
            item,
            "Поставка",
            count,
            "pcs",
            100,
            self.now - timedelta(hours=1),
            self.now + timedelta(days=1),
            "Тест",
        ).subject_id
        entry = self.catalog.save_entry(
            self.token, uuid4(), period, None, 0, item, "Описание", "1 шт", 12345, True
        ).subject_id
        slot = self.service.save_slot(
            self.token,
            uuid4(),
            None,
            period,
            self.now + timedelta(hours=2),
            self.now + timedelta(hours=2, minutes=10),
            self.now + timedelta(hours=1, minutes=45),
            capacity,
            True,
            0,
        )
        return entry, slot, batch

    def buy(
        self, guest: str, entry: UUID, slot: UUID, amount: int = 1, key: UUID | None = None
    ) -> Order:
        return self.service.checkout(guest, key or uuid4(), slot, [Choice(entry, amount, 12345)])


@pytest.fixture(scope="module")
def order_system(
    system: tuple[Settings, IdentityService, str], operations_admin: str
) -> Iterator[System]:
    settings, identity, _ = system
    engine = create_database_engine(settings)
    yield System(
        settings,
        engine,
        order_service(engine, identity, settings),
        catalog_service(engine, identity),
        inventory_service(engine, identity),
        operations_admin,
        datetime.now(UTC),
    )
    engine.dispose()


def test_order_last_portion_and_last_slot_races(order_system: System) -> None:
    s = order_system
    for count, capacity in (("1", 10), ("5", 1)):
        entry, slot, batch = s.setup(count, capacity)
        guests = [s.guest(), s.guest()]

        def attempt(token: str, entry_id: UUID = entry, slot_id: UUID = slot) -> Order | str:
            try:
                return s.buy(token, entry_id, slot_id)
            except InventoryError as exc:
                return exc.code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(attempt, guests))
        assert sum(isinstance(r, Order) for r in results) == 1
        assert any(
            r in ("SLOT_UNAVAILABLE", "INSUFFICIENT_STOCK") for r in results if isinstance(r, str)
        )
        with s.engine.connect() as connection:
            row = connection.execute(select(batches).where(batches.c.id == batch)).mappings().one()
            assert row["reserved"] == 1 and row["on_hand"] == int(count)
            assert (
                connection.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one()
                == 1
            )


def test_order_atomic_all_lines_replay_snapshot_and_guest_ownership(order_system: System) -> None:
    s = order_system
    entry, slot, batch = s.setup()
    guest = s.guest()
    key = uuid4()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: s.buy(guest, entry, slot, 2, key), range(2)))
    assert results[0].id == results[1].id
    order = results[0]
    with pytest.raises(InventoryError, match="ключ"):
        s.buy(guest, entry, slot, 3, key)
    with pytest.raises(InventoryError, match="не найден"):
        s.service.cancel(s.guest(), order.id)
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
        assert card
    s.catalog.save_entry(
        s.token,
        uuid4(),
        card.period_id,
        entry,
        1,
        card.item_id,
        "Новое описание",
        "2 шт",
        999,
        True,
    )
    own = s.service.checkouts(guest)
    assert own[0].total_minor == 24690 and own[0].lines[0].portion_label == "1 шт"
    with pytest.raises(InventoryError, match="Цена"):
        s.buy(guest, entry, slot)
    assert s.service.cancel(guest, order.id).status == "cancelled"
    assert s.service.cancel(guest, order.id).version == 2
    with s.engine.connect() as connection:
        assert (
            connection.execute(select(batches.c.reserved).where(batches.c.id == batch)).scalar_one()
            == 0
        )
        assert (
            connection.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one() == 0
        )
    # A later unavailable line rolls back every earlier line and the slot.
    entry, slot, batch = s.setup()
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
        assert card
    item = s.stock.create_item(
        s.token, uuid4(), f"Без остатка {uuid4()}", "purchased", "pcs"
    ).subject_id
    unavailable = s.catalog.save_entry(
        s.token, uuid4(), card.period_id, None, 0, item, "", "1 шт", 12345, True
    ).subject_id
    with pytest.raises(InventoryError):
        s.service.checkout(
            guest, uuid4(), slot, [Choice(entry, 1, 12345), Choice(unavailable, 1, 12345)]
        )
    with s.engine.connect() as connection:
        assert (
            connection.execute(select(batches.c.reserved).where(batches.c.id == batch)).scalar_one()
            == 0
        )
        assert (
            connection.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one() == 0
        )


def test_order_audit_failure_rolls_back_reservations_slot_outbox_and_key(
    order_system: System, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = order_system
    entry, slot, batch = s.setup()
    guest = s.guest()
    key = uuid4()
    original = PostgresOrderRepository.event

    def fail(*args: object) -> None:
        raise RuntimeError("Сбой журнала")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresOrderRepository, "event", fail)
        with pytest.raises(RuntimeError):
            s.buy(guest, entry, slot, key=key)
    assert PostgresOrderRepository.event is original
    with s.engine.connect() as connection:
        assert (
            connection.execute(select(batches.c.reserved).where(batches.c.id == batch)).scalar_one()
            == 0
        )
        assert (
            connection.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one() == 0
        )
        assert (
            connection.execute(
                select(func.count()).select_from(drafts).where(drafts.c.slot_id == slot)
            ).scalar_one()
            == 0
        )
    assert s.buy(guest, entry, slot, key=key).status == "pending_payment"


def test_expiry_cancel_race_stock_writeoff_and_reserved_spoilage(order_system: System) -> None:
    s = order_system
    entry, slot, batch = s.setup("1")
    guest = s.guest()

    def write_off() -> object:
        try:
            return s.stock.change(
                s.token, uuid4(), batch, "write_off", "1", "pcs", "Проверка гонки", 1
            )
        except InventoryError as exc:
            return exc.code

    def buy() -> object:
        try:
            return s.buy(guest, entry, slot)
        except InventoryError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(write_off), pool.submit(buy)]
        results = [f.result() for f in futures]
    with s.engine.connect() as connection:
        row = connection.execute(select(batches).where(batches.c.id == batch)).mappings().one()
        assert row["reserved"] <= row["on_hand"]
    assert sum(isinstance(r, str) for r in results) == 1
    entry, slot, batch = s.setup()
    order = s.buy(guest, entry, slot)
    s.stock.change(s.token, uuid4(), batch, "suspend", None, None, "Порча", 2)
    assert next(o for o in s.service.checkouts(guest) if o.id == order.id).stock_issue
    with pytest.raises(InventoryError, match="Пригодность"):
        s.service.mock_payment(guest, order.id, uuid4(), "success")
    original = s.service.clock
    s.service.clock = lambda: order.expires_at
    try:
        with ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(s.service.expire),
                pool.submit(s.service.cancel, guest, order.id),
            ]
            for future in futures:
                future.result()
        own = s.service.checkouts(guest)
        saved = next(o for o in own if o.id == order.id)
        assert saved.status == "expired" and saved.version == 2
        with s.engine.connect() as connection:
            assert (
                connection.execute(
                    select(batches.c.reserved).where(batches.c.id == batch)
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    select(reservations.c.released_at).where(reservations.c.order_id == order.id)
                ).scalar_one()
                is not None
            )
    finally:
        s.service.clock = original


def test_cutoff_expiry_stock_at_pickup_limits_and_http_privacy(order_system: System) -> None:
    s = order_system
    entry, slot, batch = s.setup()
    guest = s.guest()
    with s.engine.begin() as connection:
        connection.execute(
            batches.update()
            .where(batches.c.id == batch)
            .values(expires_at=s.now + timedelta(hours=1))
        )
    with pytest.raises(InventoryError, match="остатка"):
        s.buy(guest, entry, slot)
    entry, slot, _ = s.setup()
    order = s.buy(guest, entry, slot)
    with TestClient(create_app(s.settings)) as client:
        assert client.get("/api/v1/orders/checkouts").status_code == 401
        assert client.get("/api/v1/orders/staff").status_code == 401
        client.cookies.set(s.settings.guest_cookie, guest)
        result = client.get("/api/v1/orders/checkouts")
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        data = result.json()[0]
        assert not {"guest_id", "token_hash", "item_id"} & data.keys()
        assert "item_id" not in data["lines"][0]
        assert client.post(f"/api/v1/orders/{order.id}/cancel").status_code == 403
        assert (
            client.post(f"/api/v1/orders/{order.id}/cancel", headers=headers(client)).status_code
            == 200
        )
        assert client.post("/api/v1/orders/guest", headers=headers(client)).status_code == 204
    original = s.service.clock
    s.service.clock = lambda: s.now + timedelta(hours=1, minutes=45)
    try:
        with pytest.raises(InventoryError, match="слот"):
            s.buy(s.guest(), entry, slot)
    finally:
        s.service.clock = original
    entry, slot, _ = s.setup()
    guest = s.guest()
    s.buy(guest, entry, slot)
    s.buy(guest, entry, slot)
    with pytest.raises(InventoryError, match="лимит"):
        s.buy(guest, entry, slot)


def test_stale_notifications_are_not_sent_late(order_system: System) -> None:
    s = order_system
    entry, slot, _ = s.setup()
    guest = s.guest()
    checkout = s.buy(guest, entry, slot)
    s.service.mock_payment(guest, checkout.id, uuid4(), "success")
    later = datetime.now(UTC) + timedelta(days=1)
    sent: list[str] = []
    while deliver_one(s.engine, sent.append, later, timedelta(hours=6)):
        pass
    assert sent == []


def test_notification_retry_and_browser_fixture(order_system: System) -> None:
    s = order_system
    entry, slot, _ = s.setup()
    guest = s.guest()
    checkout = s.buy(guest, entry, slot)
    order = s.service.mock_payment(guest, checkout.id, uuid4(), "success")
    now = datetime.now(UTC) + timedelta(days=2)

    def failed(message: str) -> None:
        assert "guest_id" not in message and "token" not in message
        raise DeliveryFailed("Нет связи")

    assert deliver_one(s.engine, failed, now)
    with s.engine.connect() as connection:
        retry = (
            connection.execute(select(outbox).where(outbox.c.error_code == "TELEGRAM_UNAVAILABLE"))
            .mappings()
            .first()
        )
        assert retry
        assert retry["delivered_at"] is None and retry["attempts"] == 1
    sent: list[str] = []
    for _ in range(100):
        if not deliver_one(s.engine, sent.append, now + timedelta(hours=2)):
            break
    assert sent and any("Новый заказ" in text for text in sent)
    paid = next(text for text in sent if f"Новый заказ №{short_number(order.id)}" in text)
    assert "оплата тестовая" in paid and ("В столовой" in paid or "С собой" in paid)
    assert order.pickup_code
    assert all(order.pickup_code not in text and str(order.id) not in text for text in sent)
    with s.engine.connect() as connection:
        assert (
            connection.execute(
                select(outbox.c.delivered_at).where(outbox.c.id == retry["id"])
            ).scalar_one()
            is not None
        )
    # Only the isolated browser test database receives this account/stock fixture.
    s.setup("10", 10, "Обед для заказа из браузера")


def test_payment_creates_order_only_after_success_and_once(order_system: System) -> None:
    s = order_system
    entry, slot, _ = s.setup()
    guest = s.guest()
    checkout = s.buy(guest, entry, slot)
    with s.engine.connect() as connection:
        assert (
            connection.execute(select(orders.c.id).where(orders.c.id == checkout.id)).first()
            is None
        )
        assert (
            connection.execute(
                select(outbox.c.id).where(outbox.c.subject_id == checkout.id)
            ).first()
            is None
        )
    assert s.service.own_orders(guest) == []
    for outcome in ("failed", "timeout"):
        assert (
            s.service.mock_payment(guest, checkout.id, uuid4(), outcome).status == "pending_payment"
        )
        assert s.service.own_orders(guest) == []
    key = uuid4()
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda _: s.service.mock_payment(guest, checkout.id, key, "success"), range(2))
        )
    assert all(order.status == "confirmed" for order in results)
    assert len(s.service.own_orders(guest)) == 1
    with s.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(orders).where(orders.c.id == checkout.id)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(outbox).where(outbox.c.subject_id == checkout.id)
            ).scalar_one()
            == 1
        )
    cancelled = s.service.cancel(guest, checkout.id)
    assert cancelled.status == "cancelled"


def test_payment_races_expiry_without_creating_late_order(order_system: System) -> None:
    s = order_system
    entry, slot, _ = s.setup()
    guest = s.guest()
    checkout = s.buy(guest, entry, slot)
    original = s.service.clock
    s.service.clock = lambda: checkout.expires_at
    try:
        with pytest.raises(InventoryError):
            s.service.mock_payment(guest, checkout.id, uuid4(), "success")
        assert s.service.own_orders(guest) == []
        assert s.service.checkouts(guest)[0].status == "expired"
    finally:
        s.service.clock = original


def test_payment_rollback_and_cancel_race(
    order_system: System, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = order_system
    entry, slot, batch = s.setup()
    guest = s.guest()
    checkout = s.buy(guest, entry, slot)
    key = uuid4()
    original = PostgresOrderRepository.event

    def fail_after_outbox(self: PostgresOrderRepository, *args: object) -> None:
        original(self, *args)
        raise RuntimeError("Сбой после записи уведомления")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresOrderRepository, "event", fail_after_outbox)
        with pytest.raises(RuntimeError):
            s.service.mock_payment(guest, checkout.id, key, "success")
    assert s.service.own_orders(guest) == []
    assert s.service.checkouts(guest)[0].status == "pending_payment"
    with s.engine.connect() as connection:
        assert (
            connection.execute(
                select(outbox.c.id).where(outbox.c.subject_id == checkout.id)
            ).first()
            is None
        )
    with pytest.raises(InventoryError, match="не найден"):
        s.service.mock_payment(s.guest(), checkout.id, key, "success")

    def pay() -> object:
        try:
            return s.service.mock_payment(guest, checkout.id, key, "success")
        except InventoryError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        payment = pool.submit(pay)
        cancellation = pool.submit(s.service.cancel, guest, checkout.id)
        payment.result()
        assert cancellation.result().status == "cancelled"
    with s.engine.connect() as connection:
        assert (
            connection.execute(select(batches.c.reserved).where(batches.c.id == batch)).scalar_one()
            == 0
        )
        assert (
            connection.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one() == 0
        )
    assert all(o.status == "cancelled" for o in s.service.own_orders(guest))


def test_full_five_minute_hold_and_fifteen_minute_payment_cutoff(order_system: System) -> None:
    s = order_system
    entry, slot, _ = s.setup()
    cutoff = s.now + timedelta(hours=1, minutes=45)
    original = s.service.clock
    s.service.clock = lambda: cutoff - timedelta(minutes=5)
    try:
        guest = s.guest()
        checkout = s.buy(guest, entry, slot)
        assert checkout.expires_at == cutoff
        s.service.clock = lambda: cutoff - timedelta(minutes=4)
        with pytest.raises(InventoryError):
            s.buy(s.guest(), entry, slot)
        with s.service.uow() as uow:
            card = uow.catalog.entry(entry)
            assert card
        assert s.service.slots(card.period_id) == []
        s.service.clock = lambda: cutoff
        with pytest.raises(InventoryError):
            s.service.mock_payment(guest, checkout.id, uuid4(), "success")
        assert s.service.own_orders(guest) == []
    finally:
        s.service.clock = original


def test_staff_orders_prioritize_pickup_time_over_creation(order_system: System) -> None:
    s = order_system
    entry, later_slot, _ = s.setup()
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
        assert card
    earlier_slot = s.service.save_slot(
        s.token,
        uuid4(),
        None,
        card.period_id,
        s.now + timedelta(hours=1),
        s.now + timedelta(hours=1, minutes=10),
        s.now + timedelta(minutes=45),
        10,
        True,
        0,
    )
    guest = s.guest()
    later = s.buy(guest, entry, later_slot)
    earlier = s.buy(guest, entry, earlier_slot)
    s.service.mock_payment(guest, later.id, uuid4(), "success")
    s.service.mock_payment(guest, earlier.id, uuid4(), "success")
    ids = [order.id for order in s.service.staff_orders(s.token, limit=100)]
    assert ids.index(earlier.id) < ids.index(later.id)
    s.service.cancel(guest, earlier.id)
    ids = [order.id for order in s.service.staff_orders(s.token, limit=100)]
    assert ids.index(later.id) < ids.index(earlier.id)


@pytest.fixture(scope="module")
def serving_staff(
    system: tuple[Settings, IdentityService, str], operations_admin: str
) -> tuple[str, str]:
    from ashana.modules.identity.domain.models import Role

    _, identity, password = system
    tokens = []
    for login, role in (("serving.cook", Role.KITCHEN), ("serving.cashier", Role.CASHIER)):
        user = identity.create_staff(
            operations_admin, "Сотрудник", login, password, frozenset({role})
        )
        tokens.append(identity.login(user.login, password, login)[1])
    return tokens[0], tokens[1]


def paid_for_serving(s: System) -> tuple[str, Order, UUID]:
    entry, slot, batch = s.setup()
    guest = s.guest()
    draft = s.buy(guest, entry, slot, 2)
    return guest, s.service.mock_payment(guest, draft.id, uuid4(), "success"), batch


def ready_for_serving(s: System, order: Order, cook: str) -> Order:
    order = s.service.transition(cook, order.id, uuid4(), "preparing", order.version)
    return s.service.transition(cook, order.id, uuid4(), "ready", order.version)


def test_serving_two_staff_only_one_consumption_and_replay(
    order_system: System, serving_staff: tuple[str, str]
) -> None:
    from ashana.modules.inventory.infrastructure.database import movements

    s = order_system
    guest, order, batch = paid_for_serving(s)
    cook, cashier = serving_staff
    order = ready_for_serving(s, order, cook)
    keys = [uuid4(), uuid4()]
    tokens = [s.token, cashier]

    def give(index: int) -> Order | str:
        try:
            return s.service.transition(
                tokens[index],
                order.id,
                keys[index],
                "completed",
                order.version,
                order.pickup_code or "",
            )
        except InventoryError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(give, range(2)))
    assert sum(isinstance(r, Order) for r in results) == 1
    winner = next(i for i, r in enumerate(results) if isinstance(r, Order))
    assert (
        s.service.transition(
            tokens[winner],
            order.id,
            keys[winner],
            "completed",
            order.version,
            order.pickup_code or "",
        ).status
        == "completed"
    )
    with s.engine.connect() as connection:
        row = connection.execute(select(batches).where(batches.c.id == batch)).mappings().one()
        assert row["on_hand"] == 8 and row["reserved"] == 0
        entries = (
            connection.execute(
                select(movements).where(
                    movements.c.batch_id == batch, movements.c.action == "mock_fulfil"
                )
            )
            .mappings()
            .all()
        )
        assert len(entries) == 1 and entries[0]["delta"] == -2
        assert (
            connection.execute(
                select(slots.c.occupied).where(slots.c.id == order.slot_id)
            ).scalar_one()
            == 1
        )
    assert s.service.own_orders(guest)[0].status == "completed"
    with pytest.raises(InventoryError):
        s.service.cancel(guest, order.id)


def test_serving_rollback_after_event_keeps_ready_stock_and_retry(
    order_system: System, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = order_system
    guest, order, batch = paid_for_serving(s)
    order = ready_for_serving(s, order, s.token)
    original = PostgresOrderRepository.event
    key = uuid4()

    def broken(self: PostgresOrderRepository, *args: object) -> None:
        original(self, *args)
        raise RuntimeError("Сбой после уведомления")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresOrderRepository, "event", broken)
        with pytest.raises(RuntimeError):
            s.service.transition(
                s.token, order.id, key, "completed", order.version, order.pickup_code or ""
            )
    assert s.service.own_orders(guest)[0].status == "ready"
    with s.engine.connect() as connection:
        row = connection.execute(select(batches).where(batches.c.id == batch)).mappings().one()
        assert row["on_hand"] == 10 and row["reserved"] == 2
    assert (
        s.service.transition(
            s.token, order.id, key, "completed", order.version, order.pickup_code or ""
        ).status
        == "completed"
    )


def test_serving_cancel_vs_begin_is_atomic(order_system: System) -> None:
    s = order_system
    guest, order, batch = paid_for_serving(s)

    def act(cancel: bool) -> Order | str:
        try:
            return (
                s.service.cancel(guest, order.id)
                if cancel
                else s.service.transition(s.token, order.id, uuid4(), "preparing", order.version)
            )
        except InventoryError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(act, (True, False)))
    assert sum(isinstance(r, Order) for r in results) == 1
    state = s.service.own_orders(guest)[0].status
    with s.engine.connect() as connection:
        row = connection.execute(select(batches).where(batches.c.id == batch)).mappings().one()
        assert row["on_hand"] == 10
        assert row["reserved"] == (0 if state == "cancelled" else 2)


def test_serving_permissions_code_csrf_and_no_code_in_staff_dto(
    order_system: System, serving_staff: tuple[str, str]
) -> None:
    from ashana.modules.identity.domain.models import IdentityError

    s = order_system
    guest, order, _ = paid_for_serving(s)
    cook, cashier = serving_staff
    with pytest.raises(IdentityError):
        s.service.transition(cashier, order.id, uuid4(), "preparing", order.version)
    with pytest.raises(InventoryError):
        s.service.transition(cook, order.id, uuid4(), "ready", order.version)
    order = ready_for_serving(s, order, cook)
    key = uuid4()
    with pytest.raises(IdentityError):
        s.service.transition(
            cook, order.id, key, "completed", order.version, order.pickup_code or ""
        )
    with pytest.raises(InventoryError, match="Код"):
        s.service.transition(cashier, order.id, key, "completed", order.version, "WRONG123")
    with TestClient(create_app(s.settings)) as client:
        client.cookies.set(s.settings.session_cookie, cashier)
        response = client.get("/api/v1/orders/staff?limit=100")
        assert response.status_code == 200
        assert all(row["pickup_code"] is None for row in response.json())
        path = f"/api/v1/orders/staff/{order.id}/transition"
        body = {
            "target": "completed",
            "expected_version": order.version,
            "pickup_code": order.pickup_code,
        }
        assert (
            client.post(path, json=body, headers={"Idempotency-Key": str(key)}).status_code == 403
        )
        result = client.post(
            path, json=body, headers={**headers(client), "Idempotency-Key": str(key)}
        )
        assert result.status_code == 200 and result.json()["pickup_code"] is None
    assert s.service.own_orders(guest)[0].status == "completed"


def test_staff_order_lookup_for_qr_scanner_hides_code_and_drafts(
    order_system: System, serving_staff: tuple[str, str]
) -> None:
    from ashana.modules.identity.domain.models import IdentityError

    s = order_system
    guest, order, _ = paid_for_serving(s)
    cook, cashier = serving_staff
    found = s.service.staff_order(cashier, order.id)
    assert found.id == order.id and found.version == order.version
    draft = s.buy(guest, *s.setup()[:2], 1)
    with pytest.raises(InventoryError):
        s.service.staff_order(cashier, draft.id)
    with pytest.raises(InventoryError):
        s.service.staff_order(cook, uuid4())
    with pytest.raises(IdentityError):
        s.service.staff_order(guest, order.id)
    with TestClient(create_app(s.settings)) as client:
        response = client.get(f"/api/v1/orders/staff/{order.id}")
        assert response.status_code == 401
        client.cookies.set(s.settings.session_cookie, cashier)
        response = client.get(f"/api/v1/orders/staff/{order.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(order.id)
        assert response.json()["pickup_code"] is None
        assert client.get(f"/api/v1/orders/staff/{draft.id}").status_code == 404


def test_serving_suspended_and_expired_batches_never_leave_stock(order_system: System) -> None:
    s = order_system
    guest, order, batch = paid_for_serving(s)
    order = ready_for_serving(s, order, s.token)
    s.stock.change(s.token, uuid4(), batch, "suspend", None, None, "Проверка пригодности", 2)
    with pytest.raises(InventoryError, match="Выдача запрещена"):
        s.service.transition(
            s.token, order.id, uuid4(), "completed", order.version, order.pickup_code or ""
        )
    s.stock.change(s.token, uuid4(), batch, "resume", None, None, "Проверка", 3)
    original = s.service.clock
    s.service.clock = lambda: s.now + timedelta(days=1)
    try:
        with pytest.raises(InventoryError, match="Выдача запрещена"):
            s.service.transition(
                s.token, order.id, uuid4(), "completed", order.version, order.pickup_code or ""
            )
    finally:
        s.service.clock = original
    assert s.service.own_orders(guest)[0].status == "ready"


def test_serving_prepared_food_never_cooks_or_consumes_raw_again(
    order_system: System, system: tuple[Settings, IdentityService, str]
) -> None:
    from ashana.bootstrap.production import production_service
    from ashana.modules.inventory.infrastructure.database import movements
    from ashana.modules.production.domain.models import ConsumptionInput, IngredientInput

    s = order_system
    production = production_service(s.engine, system[1])
    raw = s.stock.create_item(s.token, uuid4(), f"Рис {uuid4()}", "raw", "kg").subject_id
    raw_batch = s.stock.receive(
        s.token,
        uuid4(),
        raw,
        "Сырьё",
        "10",
        "kg",
        1000,
        s.now - timedelta(hours=1),
        s.now + timedelta(days=1),
        "Проверка",
    ).subject_id
    food = s.stock.create_item(
        s.token, uuid4(), f"Плов {uuid4()}", "prepared", "portion"
    ).subject_id
    recipe = production.create_recipe(
        s.token,
        uuid4(),
        food,
        0,
        10,
        "250",
        "g",
        "Готовится заранее",
        [IngredientInput(raw, "2", "kg")],
    )
    finished = production.produce(
        s.token,
        uuid4(),
        recipe.subject_id,
        "Готовый плов",
        10,
        s.now + timedelta(days=1),
        True,
        [ConsumptionInput(raw_batch, "2", "kg")],
    )
    existing, slot, _ = s.setup()
    with s.service.uow() as uow:
        card = uow.catalog.entry(existing)
        assert card
    entry = s.catalog.save_entry(
        s.token, uuid4(), card.period_id, None, 0, food, "", "250 г", 12345, True
    ).subject_id
    guest = s.guest()
    draft = s.buy(guest, entry, slot, 2)
    order = s.service.mock_payment(guest, draft.id, uuid4(), "success")
    order = ready_for_serving(s, order, s.token)
    s.service.transition(
        s.token, order.id, uuid4(), "completed", order.version, order.pickup_code or ""
    )
    with s.engine.connect() as connection:
        assert (
            connection.execute(
                select(batches.c.on_hand).where(batches.c.id == raw_batch)
            ).scalar_one()
            == 8
        )
        assert (
            connection.execute(
                select(func.count()).select_from(movements).where(movements.c.batch_id == raw_batch)
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                select(batches.c.on_hand).where(batches.c.id == finished.subject_id)
            ).scalar_one()
            == 8
        )
