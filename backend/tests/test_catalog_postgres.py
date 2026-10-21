import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import false, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from test_identity_postgres import headers

from ashana.bootstrap.app import create_app
from ashana.bootstrap.catalog import catalog_service
from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.inventory import inventory_service
from ashana.bootstrap.production import production_service
from ashana.bootstrap.settings import Settings
from ashana.modules.catalog.application.service import CatalogService
from ashana.modules.catalog.domain.models import meal_date
from ashana.modules.catalog.infrastructure.database import (
    PostgresCatalogRepository,
    audit,
    entries,
    periods,
)
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.domain.models import InventoryError, Result
from ashana.modules.inventory.infrastructure.database import batches, requests
from ashana.modules.production.domain.models import ConsumptionInput, IngredientInput

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


@dataclass
class Catalog:
    settings: Settings
    identity: IdentityService
    engine: Engine
    service: CatalogService
    stock: InventoryService
    token: str
    admin: str
    now: datetime
    manager_id: UUID
    password: str

    def period(self, *, published: bool = True) -> Result:
        return self.service.save_period(
            self.token,
            uuid4(),
            None,
            0,
            f"Обед {uuid4()}",
            self.now - timedelta(hours=1),
            self.now + timedelta(hours=1),
            published,
        )

    def goods(self, kind: str = "purchased") -> Result:
        return self.stock.create_item(
            self.token, uuid4(), f"Товар {uuid4()}", kind, "kg" if kind == "raw" else "pcs"
        )

    def receive(self, item: Result, count: str = "10") -> Result:
        return self.stock.receive(
            self.token,
            uuid4(),
            item.subject_id,
            "Поставка для меню",
            count,
            "pcs",
            500,
            self.now - timedelta(hours=2),
            self.now + timedelta(hours=3),
            "Тестовая поставка",
        )

    def entry(self, period: Result, item: Result, *, published: bool = True) -> Result:
        return self.service.save_entry(
            self.token,
            uuid4(),
            period.subject_id,
            None,
            0,
            item.subject_id,
            "Описание",
            "1 шт",
            12345,
            published,
        )


@pytest.fixture(scope="module")
def catalog(system: tuple[Settings, IdentityService, str]) -> Iterator[Catalog]:
    settings, identity, password = system
    _, admin = identity.login("user01", password, "catalog-bootstrap")
    manager = identity.create_staff(
        admin, "Управляющий", "catalog.manager", password, frozenset({Role.MANAGER})
    )
    _, token = identity.login(manager.login, password, "catalog-manager")
    engine = create_database_engine(settings)
    service = catalog_service(engine, identity)
    now = datetime.now(UTC)
    service.clock = lambda: now
    yield Catalog(
        settings,
        identity,
        engine,
        service,
        inventory_service(engine, identity),
        token,
        admin,
        now,
        manager.id,
        password,
    )
    engine.dispose()


def test_catalog_filters_finished_stock_and_sums_only_free_fit_batches(catalog: Catalog) -> None:
    period = catalog.period()
    item = catalog.goods()
    entry = catalog.entry(period, item)
    assert entry.subject_id not in {e.id for e in catalog.service.menu()[1]}
    stock = [catalog.receive(item) for _ in range(5)]
    with catalog.engine.begin() as connection:
        connection.execute(
            batches.update().where(batches.c.id == stock[0].subject_id).values(reserved=3)
        )
        connection.execute(
            batches.update().where(batches.c.id == stock[1].subject_id).values(status="suspended")
        )
        connection.execute(
            batches.update()
            .where(batches.c.id == stock[2].subject_id)
            .values(expires_at=catalog.now - timedelta(seconds=1))
        )
        connection.execute(
            batches.update()
            .where(batches.c.id == stock[3].subject_id)
            .values(on_hand=0, status="written_off")
        )
        connection.execute(
            batches.update().where(batches.c.id == stock[4].subject_id).values(reserved=10)
        )
    menu = next(e for e in catalog.service.menu()[1] if e.id == entry.subject_id)
    assert menu.available == 7 and menu.price_minor == 12345
    catalog.stock.change(
        catalog.token, uuid4(), stock[0].subject_id, "suspend", None, None, "Проверка меню", 1
    )
    assert entry.subject_id not in {e.id for e in catalog.service.menu()[1]}
    with pytest.raises(InventoryError):
        catalog.entry(period, catalog.goods("raw"))
    prepared = catalog.goods("prepared")
    prepared_entry = catalog.entry(period, prepared)
    assert prepared_entry.subject_id not in {e.id for e in catalog.service.menu()[1]}
    raw = catalog.goods("raw")
    raw_batch = catalog.stock.receive(
        catalog.token,
        uuid4(),
        raw.subject_id,
        "Сырьё",
        "1",
        "kg",
        100,
        catalog.now - timedelta(hours=1),
        catalog.now + timedelta(days=1),
        "Тест",
    )
    production = production_service(catalog.engine, catalog.identity)
    recipe = production.create_recipe(
        catalog.token,
        uuid4(),
        prepared.subject_id,
        0,
        5,
        "200",
        "g",
        "Приготовить",
        [IngredientInput(raw.subject_id, "1", "kg")],
    )
    production.produce(
        catalog.token,
        uuid4(),
        recipe.subject_id,
        "Готовый выпуск",
        4,
        catalog.now + timedelta(hours=2),
        True,
        [ConsumptionInput(raw_batch.subject_id, "1", "kg")],
    )
    # The actual production timestamp is later than the fixed test clock.
    catalog.service.clock = lambda: datetime.now(UTC)
    try:
        assert (
            next(
                e for e in catalog.service.menu()[1] if e.id == prepared_entry.subject_id
            ).available
            == 4
        )
    finally:
        catalog.service.clock = lambda: catalog.now


def test_catalog_publication_time_boundaries_and_almaty_date(catalog: Catalog) -> None:
    assert catalog.service.periods(catalog.token, date.max) == []
    period = catalog.period(published=False)
    item = catalog.goods()
    catalog.receive(item)
    entry = catalog.entry(period, item)
    assert entry.subject_id not in {e.id for e in catalog.service.menu()[1]}
    start = catalog.now + timedelta(hours=2)
    end = start + timedelta(minutes=30)
    catalog.service.save_period(
        catalog.token, uuid4(), period.subject_id, 1, "Будущий завтрак", start, end, True
    )
    for instant, visible in (
        (start - timedelta(microseconds=1), False),
        (start, True),
        (end, False),
    ):

        def fixed_clock(value: datetime = instant) -> datetime:
            return value

        catalog.service.clock = fixed_clock
        assert (entry.subject_id in {e.id for e in catalog.service.menu()[1]}) is visible
    catalog.service.clock = lambda: catalog.now
    found = catalog.service.periods(catalog.token, meal_date(start), 0, 100)
    assert period.subject_id in {p.id for p in found}
    active = catalog.period()
    unpublished = catalog.entry(active, item, published=False)
    assert unpublished.subject_id not in {e.id for e in catalog.service.menu()[1]}
    catalog.service.save_entry(
        catalog.token,
        uuid4(),
        active.subject_id,
        unpublished.subject_id,
        1,
        item.subject_id,
        "",
        "1 штука",
        0,
        True,
    )
    assert (
        next(e for e in catalog.service.menu()[1] if e.id == unpublished.subject_id).price_minor
        == 0
    )


def test_catalog_replay_stale_edits_and_audit_rollback(
    catalog: Catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = uuid4()

    def create() -> Result:
        return catalog.service.save_period(
            catalog.token,
            key,
            None,
            0,
            "Повтор",
            catalog.now,
            catalog.now + timedelta(hours=1),
            True,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: create(), range(2)))
    assert outcomes[0] == outcomes[1]
    period = outcomes[0]

    def edit(name: str) -> str:
        try:
            catalog.service.save_period(
                catalog.token,
                uuid4(),
                period.subject_id,
                1,
                name,
                catalog.now,
                catalog.now + timedelta(hours=1),
                False,
            )
            return "ok"
        except InventoryError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, ("Первая правка", "Вторая правка"))) == ["STALE_CATALOG", "ok"]
    with pytest.raises(InventoryError) as mismatch:
        catalog.service.save_period(
            catalog.token,
            key,
            None,
            0,
            "Другие данные",
            catalog.now,
            catalog.now + timedelta(hours=1),
            True,
        )
    assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    with catalog.engine.connect() as connection:
        events = (
            connection.execute(
                select(audit)
                .where(audit.c.subject_id == period.subject_id)
                .order_by(audit.c.created_at, audit.c.id)
            )
            .mappings()
            .all()
        )
        assert len(events) == 2
        changed = next(e for e in events if e["before"] is not None)
        assert changed["before"]["version"] == 1 and changed["after"]["version"] == 2
    item = catalog.goods()
    badkey = uuid4()

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Тестовый сбой аудита")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresCatalogRepository, "audit", fail)
        with pytest.raises(RuntimeError):
            catalog.service.save_entry(
                catalog.token,
                badkey,
                period.subject_id,
                None,
                0,
                item.subject_id,
                "",
                "1 шт",
                100,
                True,
            )
    with catalog.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(entries)
                .where(entries.c.period_id == period.subject_id)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                select(func.count()).select_from(requests).where(requests.c.key == badkey)
            ).scalar_one()
            == 0
        )
    catalog.service.save_entry(
        catalog.token, badkey, period.subject_id, None, 0, item.subject_id, "", "1 шт", 100, True
    )
    with pytest.raises(InventoryError) as duplicate:
        catalog.entry(period, item)
    assert duplicate.value.code == "MENU_ITEM_EXISTS"


def test_catalog_http_roles_csrf_public_privacy_and_revoked_replay(catalog: Catalog) -> None:
    period = catalog.period()
    item = catalog.goods()
    catalog.receive(item)
    key = uuid4()
    result = catalog.service.save_entry(
        catalog.token, key, period.subject_id, None, 0, item.subject_id, "", "1 шт", 100, True
    )
    with TestClient(create_app(catalog.settings)) as client:
        response = client.get("/api/v1/catalog/menu")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        row = next(e for e in response.json()["entries"] if e["id"] == str(result.subject_id))
        assert (
            not {"actor_id", "item_id", "reserved", "total_cost_minor", "source", "batch_id"}
            & row.keys()
        )
        assert (
            client.get(f"/api/v1/catalog/periods?day={meal_date(catalog.now)}").status_code == 401
        )
        client.cookies.set(catalog.settings.session_cookie, catalog.token)
        assert client.post("/api/v1/catalog/periods", json={}).status_code == 403
        assert (
            client.post(
                "/api/v1/catalog/periods",
                headers={**headers(client), "Idempotency-Key": str(uuid4())},
                json={
                    "name": "Тест",
                    "starts_at": catalog.now.isoformat(),
                    "ends_at": (catalog.now + timedelta(hours=1)).isoformat(),
                    "published": "true",
                    "expected_version": 0,
                },
            ).status_code
            == 422
        )
    catalog.identity.assign_roles(catalog.admin, catalog.manager_id, frozenset({Role.KITCHEN}))
    catalog.token = catalog.identity.login("catalog.manager", catalog.password, "catalog-demoted")[
        1
    ]
    try:
        with pytest.raises(IdentityError) as forbidden:
            catalog.service.save_entry(
                catalog.token,
                key,
                period.subject_id,
                None,
                0,
                item.subject_id,
                "",
                "1 шт",
                100,
                True,
            )
        assert forbidden.value.code == "FORBIDDEN"
    finally:
        catalog.identity.assign_roles(catalog.admin, catalog.manager_id, frozenset({Role.MANAGER}))
        catalog.token = catalog.identity.login(
            "catalog.manager", catalog.password, "catalog-restored"
        )[1]


def test_catalog_pagination_filters_before_limit_and_database_constraints(catalog: Catalog) -> None:
    period = catalog.period()
    for _ in range(3):
        catalog.entry(period, catalog.goods())
    item = catalog.goods()
    catalog.receive(item)
    entry = catalog.entry(period, item)
    all_entries = catalog.service.menu(0, 100)[1]
    pages = [catalog.service.menu(i, 1)[1][0].id for i in range(len(all_entries))]
    assert pages == [e.id for e in all_entries] and entry.subject_id in pages
    with pytest.raises(DBAPIError), catalog.engine.begin() as connection:
        connection.execute(audit.delete().where(false()))
    with pytest.raises(DBAPIError), catalog.engine.begin() as connection:
        connection.execute(audit.update().where(false()).values(entity="entry"))
    with pytest.raises(DBAPIError), catalog.engine.begin() as connection:
        connection.execute(
            entries.update().where(entries.c.id == entry.subject_id).values(price_minor=-1)
        )
    with pytest.raises(DBAPIError), catalog.engine.begin() as connection:
        connection.execute(
            periods.update()
            .where(periods.c.id == period.subject_id)
            .values(ends_at=catalog.now - timedelta(hours=2))
        )
    # Dedicated, unlisted stock fixture for the browser's creation/publication workflow.
    browser_item = catalog.stock.create_item(
        catalog.token, uuid4(), "Сок для меню браузера", "purchased", "pcs"
    )
    catalog.receive(browser_item, "8")


def test_category_saved_published_and_replayed(catalog: Catalog) -> None:
    c = catalog
    period = c.period()
    item = c.stock.create_item(c.token, uuid4(), "Категорийный напиток", "purchased", "pcs")
    key = uuid4()
    result = c.service.save_entry(
        c.token,
        key,
        period.subject_id,
        None,
        0,
        item.subject_id,
        "",
        "500 мл",
        25000,
        True,
        "Напитки",
    )
    repeated = c.service.save_entry(
        c.token,
        key,
        period.subject_id,
        None,
        0,
        item.subject_id,
        "",
        "500 мл",
        25000,
        True,
        "Напитки",
    )
    assert result == repeated
    entries = c.service.entries(c.token, period.subject_id)
    assert entries[0].category == "Напитки"
