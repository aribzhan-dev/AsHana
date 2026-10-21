import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import false, func, select
from sqlalchemy.exc import DBAPIError
from test_identity_postgres import headers

from ashana.bootstrap.app import create_app
from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.inventory import inventory_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.domain.models import InventoryError, Result
from ashana.modules.inventory.infrastructure.database import audit, batches, movements, requests

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


def test_inventory_atomic_replay_races_and_history(
    system: tuple[Settings, IdentityService, str],
    operations_admin: str,
) -> None:
    settings, identity, password = system
    engine = create_database_engine(settings)
    service = inventory_service(engine, identity)
    token = operations_admin
    now = datetime.now(UTC)
    item = service.create_item(token, uuid4(), "Рис проверочный", "raw", "kg")
    key = uuid4()

    def receive() -> Result:
        return service.receive(
            token,
            key,
            item.subject_id,
            "Тестовая партия",
            "1250",
            "g",
            12500,
            now,
            now + timedelta(days=2),
            "Синтетическая поставка",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: receive(), range(2)))
        assert results[0] == results[1]
        batch_id = results[0].subject_id
        assert service.movements(token, batch_id)[0].delta == Decimal("1.25")
        with pytest.raises(InventoryError) as mismatch:
            service.receive(
                token,
                key,
                item.subject_id,
                "Другой payload",
                "1250",
                "g",
                12500,
                now,
                now + timedelta(days=2),
                "Синтетическая поставка",
            )
        assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"

        def write_off() -> str:
            try:
                service.change(
                    token, uuid4(), batch_id, "write_off", "1", "kg", "Проверка гонки", 1
                )
                return "ok"
            except InventoryError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: write_off(), range(2)))
        assert sorted(outcomes) == ["STALE_BATCH", "ok"]
        with pytest.raises(InventoryError) as insufficient:
            service.change(token, uuid4(), batch_id, "write_off", "1", "kg", "Нехватка", 2)
        assert insufficient.value.code == "INSUFFICIENT_STOCK"
        countkey = uuid4()
        counted = service.change(
            token, countkey, batch_id, "count", "0.500", "kg", "Найдено при пересчёте", 2
        )
        assert counted.version == 3
        assert (
            service.change(
                token, countkey, batch_id, "count", "0.500", "kg", "Найдено при пересчёте", 2
            )
            == counted
        )
        with pytest.raises(InventoryError):
            service.change(token, uuid4(), batch_id, "count", "0", "kg", "Старый пересчёт", 2)
        history = service.movements(token, batch_id)
        assert (
            len(history) == 3
            and history[0].before == Decimal("0.25")
            and history[0].after == Decimal("0.5")
        )
        # Future reservation fixture in the isolated test database.
        with engine.begin() as connection:
            connection.execute(
                batches.update().where(batches.c.id == batch_id).values(reserved=Decimal("0.4"))
            )
        with pytest.raises(InventoryError):
            service.change(
                token, uuid4(), batch_id, "count", "0.2", "kg", "Нельзя затронуть резерв", 3
            )
        with pytest.raises(InventoryError):
            service.change(
                token, uuid4(), batch_id, "write_off", "0.2", "kg", "Нельзя затронуть резерв", 3
            )
        service.change(token, uuid4(), batch_id, "suspend", None, None, "Проверка пригодности", 3)
        service.change(token, uuid4(), batch_id, "resume", None, None, "Проверка завершена", 4)
        assert len(service.movements(token, batch_id)) == 5
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count())
                    .select_from(requests)
                    .where(requests.c.subject_id == batch_id)
                ).scalar_one()
                == 5
            )
        for table in (movements, audit, requests):
            with pytest.raises(DBAPIError), engine.begin() as connection:
                connection.execute(table.delete().where(false()))
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(batches.update().where(batches.c.id == batch_id).values(on_hand=-1))
    finally:
        engine.dispose()


def test_inventory_permissions_validation_and_expired_batches(
    system: tuple[Settings, IdentityService, str],
    operations_admin: str,
) -> None:
    settings, identity, password = system
    engine = create_database_engine(settings)
    service = inventory_service(engine, identity)
    token = operations_admin
    clerk = identity.create_staff(
        token, "Кладовщик", "stock.clerk", password, frozenset({Role.STOREKEEPER})
    )
    _, clerk_token = identity.login(clerk.login, password, "inventory-clerk")
    identity.create_staff(token, "Администратор", "stock.admin", password, frozenset({Role.ADMIN}))
    _, admin_only = identity.login("stock.admin", password, "inventory-admin-only")
    try:
        with pytest.raises(IdentityError):
            service.items(admin_only)
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/inventory/items").status_code == 401
            assert (
                client.post(
                    "/api/v1/auth/login",
                    headers=headers(client),
                    json={"login": clerk.login, "password": password},
                ).status_code
                == 200
            )
            data = {"name": "Вода проверочная", "kind": "purchased", "unit": "pcs"}
            assert client.post("/api/v1/inventory/items", json=data).status_code == 403
            created = client.post(
                "/api/v1/inventory/items",
                headers={**headers(client), "Idempotency-Key": str(uuid4())},
                json=data,
            )
            assert created.status_code == 201, created.text
            assert created.headers["cache-control"] == "no-store"
            assert client.get("/api/v1/inventory/items?limit=101").status_code == 422
            assert client.get(f"/api/v1/inventory/batches/{uuid4()}/movements").status_code == 404
        now = datetime.now(UTC)
        item = service.create_item(clerk_token, uuid4(), "Сок проверочный", "purchased", "pcs")
        for amount in ("1.5", "NaN", "1e2"):
            with pytest.raises(InventoryError):
                service.receive(
                    clerk_token,
                    uuid4(),
                    item.subject_id,
                    "Неверная партия",
                    amount,
                    "pcs",
                    0,
                    now,
                    now + timedelta(days=1),
                    "Тест",
                )
        receipt = service.receive(
            clerk_token,
            uuid4(),
            item.subject_id,
            "Истёкшая партия",
            "2",
            "pcs",
            0,
            now - timedelta(days=2),
            now - timedelta(days=1),
            "Тест",
        )
        with pytest.raises(InventoryError):
            service.change(
                clerk_token, uuid4(), receipt.subject_id, "resume", None, None, "Попытка", 1
            )
        service.change(
            clerk_token, uuid4(), receipt.subject_id, "write_off", "2", "pcs", "Истёк срок", 1
        )
        with pytest.raises(InventoryError):
            service.change(
                clerk_token, uuid4(), receipt.subject_id, "count", "2", "pcs", "Попытка открыть", 2
            )
        own = service.create_item(clerk_token, uuid4(), "Каша проверочная", "prepared", "portion")
        with pytest.raises(InventoryError):
            service.receive(
                clerk_token,
                uuid4(),
                own.subject_id,
                "Без выпуска",
                "2",
                "portion",
                0,
                now,
                now + timedelta(days=1),
                "Тест",
            )
        replaykey = uuid4()
        service.create_item(clerk_token, replaykey, "Отзыв прав", "raw", "l")
        identity.assign_roles(token, clerk.id, frozenset({Role.KITCHEN}))
        with pytest.raises(IdentityError):
            service.create_item(clerk_token, replaykey, "Отзыв прав", "raw", "l")
    finally:
        engine.dispose()


def test_inventory_rollback_on_audit_failure(
    system: tuple[Settings, IdentityService, str],
    operations_admin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ashana.modules.inventory.infrastructure.database import PostgresInventoryRepository

    settings, identity, password = system
    engine = create_database_engine(settings)
    service = inventory_service(engine, identity)
    token = operations_admin
    item = service.create_item(token, uuid4(), "Откат поставки", "raw", "kg")
    now = datetime.now(UTC)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic rollback")

    monkeypatch.setattr(PostgresInventoryRepository, "audit", fail)
    try:
        with pytest.raises(RuntimeError):
            service.receive(
                token,
                uuid4(),
                item.subject_id,
                "Не сохранять",
                "2",
                "kg",
                100,
                now,
                now + timedelta(days=1),
                "Тест",
            )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count())
                    .select_from(batches)
                    .where(batches.c.item_id == item.subject_id)
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_inventory_idempotency_is_scoped_and_database_checks_units(
    system: tuple[Settings, IdentityService, str],
    operations_admin: str,
) -> None:
    settings, identity, password = system
    engine = create_database_engine(settings)
    service = inventory_service(engine, identity)
    token = operations_admin
    other = identity.create_staff(
        token, "Оператор", "stock.other", password, frozenset({Role.STOREKEEPER})
    )
    _, other_token = identity.login(other.login, password, "inventory-other")
    item = service.create_item(token, uuid4(), "Сок для проверки ключей", "purchased", "pcs")
    now = datetime.now(UTC)
    key = uuid4()
    try:
        first = service.receive(
            token,
            key,
            item.subject_id,
            "Поставка",
            "3",
            "pcs",
            100,
            now,
            now + timedelta(days=1),
            "Тест",
        )
        second = service.receive(
            other_token,
            key,
            item.subject_id,
            "Поставка",
            "3",
            "pcs",
            100,
            now,
            now + timedelta(days=1),
            "Тест",
        )
        assert first.subject_id != second.subject_id
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(
                batches.update()
                .where(batches.c.id == first.subject_id)
                .values(on_hand=Decimal("1.5"))
            )
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(
                batches.update().where(batches.c.id == first.subject_id).values(unit="kg")
            )
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(
                movements.update()
                .where(movements.c.batch_id == first.subject_id)
                .values(reason="Недопустимое исправление")
            )
        with pytest.raises(InventoryError) as duplicate:
            service.create_item(token, uuid4(), "СОК ДЛЯ ПРОВЕРКИ КЛЮЧЕЙ", "purchased", "pcs")
        assert duplicate.value.code == "ITEM_EXISTS"
        with pytest.raises(InventoryError):
            service.receive(
                token,
                uuid4(),
                item.subject_id,
                "Без зоны",
                "1",
                "pcs",
                0,
                now.replace(tzinfo=None),
                now + timedelta(days=1),
                "Тест",
            )
    finally:
        engine.dispose()
