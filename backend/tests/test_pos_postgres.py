import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from test_identity_postgres import headers
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.app import create_app
from ashana.bootstrap.pos import pos_service
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.inventory.infrastructure.database import batches, movements
from ashana.modules.orders.domain.models import Choice, Order
from ashana.modules.orders.infrastructure.database import slots
from ashana.modules.pos.domain.models import Sale
from ashana.modules.pos.infrastructure.database import PostgresSaleRepository, sales

pos_system = _order_system

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


@pytest.fixture(scope="module")
def pos(pos_system, system):
    s = pos_system
    return pos_service(s.engine, system[1], s.service)


def test_pos_online_and_two_cashiers_last_portion(pos_system: System, pos) -> None:
    s = pos_system
    for online in (True, False):
        entry, slot, batch = s.setup("1")
        guest = s.guest()

        def attempt(counter: bool, entry=entry, guest=guest, slot=slot):
            try:
                if counter:
                    return pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
                return s.buy(guest, entry, slot)
            except InventoryError as e:
                return e.code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(attempt, [True, not online]))
        assert sum(isinstance(v, (Sale, Order)) for v in results) == 1
        assert "INSUFFICIENT_STOCK" in results
        with s.engine.connect() as c:
            row = c.execute(select(batches).where(batches.c.id == batch)).mappings().one()
            assert row["on_hand"] - row["reserved"] == 0
            assert row["on_hand"] in (0, 1)


def test_pos_preserves_online_reserve_expiry_and_slot(pos_system: System, pos) -> None:
    s = pos_system
    entry, slot, batch = s.setup("3")
    guest = s.guest()
    draft = s.buy(guest, entry, slot, 2)
    pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
    with pytest.raises(InventoryError, match="остатка"):
        pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
    with s.engine.connect() as c:
        row = c.execute(select(batches).where(batches.c.id == batch)).mappings().one()
        assert row["on_hand"] == row["reserved"] == 2
        assert c.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one() == 1
    original = s.service.clock
    s.service.clock = lambda: draft.expires_at
    try:
        pos.sell(s.token, uuid4(), [Choice(entry, 2, 12345)], "success")
    finally:
        s.service.clock = original
    with s.engine.connect() as c:
        row = c.execute(select(batches).where(batches.c.id == batch)).mappings().one()
        assert row["on_hand"] == row["reserved"] == 0
        assert c.execute(select(slots.c.occupied).where(slots.c.id == slot)).scalar_one() == 0


def test_pos_replay_snapshot_and_failed_timeout_no_stock(pos_system: System, pos) -> None:
    s = pos_system
    entry, _, batch = s.setup("3")
    choices = [Choice(entry, 1, 12345)]
    for outcome in ("failed", "timeout"):
        key = uuid4()
        attempt = pos.sell(s.token, key, choices, outcome)
        assert attempt.outcome == outcome
        assert pos.sell(s.token, key, choices, outcome) == attempt
    with s.engine.connect() as c:
        assert c.execute(select(batches.c.on_hand).where(batches.c.id == batch)).scalar_one() == 3
    key = uuid4()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: pos.sell(s.token, key, choices, "success"), range(2)))
    assert results[0] == results[1]
    with pytest.raises(InventoryError, match="ключ"):
        pos.sell(s.token, key, [Choice(entry, 2, 12345)], "success")
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
    s.catalog.save_entry(
        s.token,
        uuid4(),
        card.period_id,
        entry,
        1,
        card.item_id,
        "Новое описание",
        "Новая порция",
        999,
        True,
    )
    assert pos.sell(s.token, key, choices, "success").total_minor == 12345
    with pytest.raises(InventoryError, match="Цена"):
        pos.sell(s.token, uuid4(), choices, "success")
    with s.engine.connect() as c:
        assert c.execute(select(batches.c.on_hand).where(batches.c.id == batch)).scalar_one() == 2
        assert (
            c.execute(
                select(func.count())
                .select_from(movements)
                .where(movements.c.batch_id == batch, movements.c.action == "mock_pos_sale")
            ).scalar_one()
            == 1
        )


def test_pos_rollback_all_lines_and_after_record(pos_system: System, pos, monkeypatch) -> None:
    s = pos_system
    entry, _, batch = s.setup("2")
    other, _, unavailable = s.setup("1")
    key = uuid4()
    choices = [Choice(entry, 1, 12345), Choice(other, 2, 12345)]
    with pytest.raises(InventoryError):
        pos.sell(s.token, key, choices, "success")
    original = PostgresSaleRepository.add

    def fail(self, sale):
        original(self, sale)
        raise RuntimeError("Сбой после записи чека")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresSaleRepository, "add", fail)
        with pytest.raises(RuntimeError):
            pos.sell(s.token, key, [Choice(entry, 1, 12345)], "success")
    with s.engine.connect() as c:
        assert c.execute(select(batches.c.on_hand).where(batches.c.id == batch)).scalar_one() == 2
        assert (
            c.execute(select(batches.c.on_hand).where(batches.c.id == unavailable)).scalar_one()
            == 1
        )
    assert pos.sell(s.token, key, [Choice(entry, 1, 12345)], "success").outcome == "success"


def test_pos_unfit_batches_and_closed_period(pos_system: System, pos) -> None:
    s = pos_system
    for status in ("suspended", "expired", "future"):
        entry, _, batch = s.setup("1")
        with s.engine.begin() as c:
            values = (
                {"status": "suspended"}
                if status == "suspended"
                else (
                    {"expires_at": s.now - timedelta(minutes=1)}
                    if status == "expired"
                    else {"received_at": s.now + timedelta(hours=1)}
                )
            )
            c.execute(batches.update().where(batches.c.id == batch).values(**values))
        with pytest.raises(InventoryError, match="остатка"):
            pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
    entry, _, _ = s.setup()
    original = pos.clock
    pos.clock = lambda: s.now + timedelta(hours=5)
    try:
        with pytest.raises(InventoryError, match="Период"):
            pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
    finally:
        pos.clock = original


def test_pos_permissions_csrf_production_immutable_history(pos_system: System, pos, system) -> None:
    s = pos_system
    settings, identity, password = system
    entry, _, _ = s.setup()
    cashier = identity.create_staff(
        s.token, "Кассир", "pos.cashier", password, frozenset({Role.CASHIER})
    )
    token = identity.login(cashier.login, password, "pos-tests")[1]
    key = uuid4()
    choices = [Choice(entry, 1, 12345)]
    result = pos.sell(token, key, choices, "success")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/pos/sales").status_code == 401
        client.cookies.set(settings.session_cookie, token)
        assert client.get("/api/v1/pos/sales").headers["cache-control"] == "no-store"
        assert client.post("/api/v1/pos/sales", json={}).status_code == 403
        data = {
            "outcome": "success",
            "lines": [{"entry_id": str(entry), "quantity": 1, "expected_price_minor": 12345}],
        }
        response = client.post(
            "/api/v1/pos/sales", json=data, headers={**headers(client), "Idempotency-Key": str(key)}
        )
        assert response.status_code == 201 and response.json()["id"] == str(result.id)
        assert response.json()["mode"] == "mock"
        assert "item_id" not in response.json()["lines"][0]
        bad = {**data, "total_minor": 1}
        assert (
            client.post(
                "/api/v1/pos/sales",
                json=bad,
                headers={**headers(client), "Idempotency-Key": str(uuid4())},
            ).status_code
            == 422
        )
    disabled = pos_service(s.engine, identity, s.service, enabled=False)
    with pytest.raises(IdentityError, match="рабочем"):
        disabled.sell(token, uuid4(), choices, "success")
    identity.assign_roles(s.token, cashier.id, frozenset({Role.KITCHEN}))
    with pytest.raises(IdentityError):
        pos.sell(token, key, choices, "success")
    cook = identity.login(cashier.login, password, "pos-cook")[1]
    with pytest.raises(IdentityError, match="Недостаточно прав"):
        pos.history(cook)
    with s.engine.begin() as c, pytest.raises(DBAPIError):
        c.execute(sales.update().where(sales.c.id == result.id).values(total_minor=0))
    # A dedicated fixture avoids competition with online browser scenarios.
    s.setup("10", name="Кассовый обед из браузера")


def test_pos_distinct_periods_cashiers_fefo_and_same_item_lines(
    pos_system: System, pos, system
) -> None:
    s = pos_system
    identity, password = system[1:]
    staff = identity.create_staff(
        s.token, "Кассир", "pos.second", password, frozenset({Role.CASHIER})
    )
    second = identity.login(staff.login, password, "pos-second")[1]
    entry, _, batch = s.setup("1")
    other, _, _ = s.setup()
    with s.service.uow() as uow:
        first = uow.catalog.entry(entry)
        other_card = uow.catalog.entry(other)
    alternative = s.catalog.save_entry(
        s.token, uuid4(), other_card.period_id, None, 0, first.item_id, "", "1 шт", 12345, True
    ).subject_id

    def attempt(pair):
        token, id = pair
        try:
            return pos.sell(token, uuid4(), [Choice(id, 1, 12345)], "success")
        except InventoryError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, [(s.token, entry), (second, alternative)]))
    assert sum(isinstance(v, Sale) for v in results) == 1
    assert "INSUFFICIENT_STOCK" in results
    early = s.stock.receive(
        s.token,
        uuid4(),
        first.item_id,
        "Ранняя партия",
        "2",
        "pcs",
        100,
        s.now - timedelta(hours=1),
        s.now + timedelta(hours=1),
        "Тест",
    ).subject_id
    late = s.stock.receive(
        s.token,
        uuid4(),
        first.item_id,
        "Поздняя партия",
        "3",
        "pcs",
        100,
        s.now - timedelta(hours=1),
        s.now + timedelta(days=1),
        "Тест",
    ).subject_id
    # Two menu cards share one stock pool, even within the same cart.
    pos.sell(s.token, uuid4(), [Choice(entry, 2, 12345), Choice(alternative, 2, 12345)], "success")
    with s.engine.connect() as c:
        assert c.execute(select(batches.c.on_hand).where(batches.c.id == early)).scalar_one() == 0
        assert c.execute(select(batches.c.on_hand).where(batches.c.id == late)).scalar_one() == 1
        assert c.execute(select(batches.c.on_hand).where(batches.c.id == batch)).scalar_one() == 0


def test_pos_prepared_food_does_not_consume_raw_twice(pos_system: System, pos, system) -> None:
    from ashana.bootstrap.production import production_service
    from ashana.modules.production.domain.models import ConsumptionInput, IngredientInput

    s = pos_system
    production = production_service(s.engine, system[1])
    raw = s.stock.create_item(s.token, uuid4(), f"Рис кассы {uuid4()}", "raw", "kg").subject_id
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
        "Тест",
    ).subject_id
    food = s.stock.create_item(
        s.token, uuid4(), f"Плов кассы {uuid4()}", "prepared", "portion"
    ).subject_id
    recipe = production.create_recipe(
        s.token, uuid4(), food, 0, 10, "250", "g", "Заранее", [IngredientInput(raw, "2", "kg")]
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
    existing, _, _ = s.setup()
    with s.service.uow() as uow:
        card = uow.catalog.entry(existing)
    entry = s.catalog.save_entry(
        s.token, uuid4(), card.period_id, None, 0, food, "", "250 г", 12345, True
    ).subject_id
    pos.sell(s.token, uuid4(), [Choice(entry, 2, 12345)], "success")
    with s.engine.connect() as c:
        assert (
            c.execute(select(batches.c.on_hand).where(batches.c.id == raw_batch)).scalar_one() == 8
        )
        assert (
            c.execute(
                select(func.count()).select_from(movements).where(movements.c.batch_id == raw_batch)
            ).scalar_one()
            == 2
        )
        assert (
            c.execute(
                select(batches.c.on_hand).where(batches.c.id == finished.subject_id)
            ).scalar_one()
            == 8
        )


def test_payment_method_snapshot_and_writeoff_reserve(pos_system: System, pos, system) -> None:
    from uuid import UUID

    from ashana.bootstrap.inventory import inventory_service

    s = pos_system
    inventory = inventory_service(s.engine, system[1])
    cash = inventory_service(s.engine, system[1], cashier=True)
    method = inventory.create_directory(s.token, uuid4(), "payment_method", "Терминал проверки")
    entry, slot, batch = s.setup("3")
    draft = s.buy(s.guest(), entry, slot, 2)
    with s.engine.connect() as c:
        version = c.execute(select(batches.c.version).where(batches.c.id == batch)).scalar_one()
    with pytest.raises(InventoryError, match="резерв"):
        cash.change(s.token, uuid4(), batch, "write_off", "2", "pcs", "Не продано", version)
    choices = [Choice(entry, 1, 12345)]
    with pytest.raises(InventoryError):
        pos.sell(s.token, uuid4(), choices, "success", uuid4())
    key = uuid4()
    sale = pos.sell(s.token, key, choices, "success", method.subject_id)
    assert sale.payment_method_name == "Терминал проверки"
    assert pos.sell(s.token, key, choices, "success", method.subject_id) == sale
    with pytest.raises(InventoryError, match="ключ"):
        pos.sell(s.token, key, choices, "success", UUID("00000000-0000-0000-0000-000000000002"))
    assert draft.id
