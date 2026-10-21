import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import false, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from test_identity_postgres import headers

from ashana.bootstrap.app import create_app
from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.inventory import inventory_service
from ashana.bootstrap.production import production_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.domain.models import InventoryError, Result
from ashana.modules.inventory.infrastructure.database import (
    PostgresInventoryRepository,
    batches,
    movements,
)
from ashana.modules.production.application.service import ProductionService
from ashana.modules.production.domain.models import ConsumptionInput, IngredientInput
from ashana.modules.production.infrastructure.database import (
    consumption,
    lines,
    productions,
    recipes,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


@dataclass
class Kitchen:
    settings: Settings
    identity: IdentityService
    engine: Engine
    stock: InventoryService
    service: ProductionService
    admin: str
    token: str
    cook_id: UUID

    def case(self, amount: str = "1") -> tuple[Result, list[Result]]:
        raw = [
            self.stock.create_item(self.admin, uuid4(), f"Сырьё {uuid4()}", "raw", "kg")
            for _ in range(2)
        ]
        output = self.stock.create_item(
            self.admin, uuid4(), f"Блюдо {uuid4()}", "prepared", "portion"
        )
        recipe = self.service.create_recipe(
            self.token,
            uuid4(),
            output.subject_id,
            0,
            12,
            "250",
            "g",
            "Проверочная технология",
            [IngredientInput(r.subject_id, "0.5", "kg") for r in raw],
        )
        now = datetime.now(UTC)
        stock = [
            self.stock.receive(
                self.admin,
                uuid4(),
                r.subject_id,
                "Сырьё для теста",
                amount,
                "kg",
                10000,
                now,
                now + timedelta(days=2),
                "Тестовая поставка",
            )
            for r in raw
        ]
        return recipe, stock

    def produce(
        self, recipe: Result, stock: list[Result], key: UUID | None = None, amount: str = "1"
    ) -> Result:
        return self.service.produce(
            self.token,
            key or uuid4(),
            recipe.subject_id,
            "Тестовый выпуск",
            10,
            EXPIRY,
            True,
            [ConsumptionInput(s.subject_id, amount, "kg") for s in stock],
        )


EXPIRY = datetime.now(UTC) + timedelta(days=1)


@pytest.fixture(scope="module")
def kitchen(
    system: tuple[Settings, IdentityService, str], operations_admin: str
) -> Iterator[Kitchen]:
    settings, identity, password = system
    engine = create_database_engine(settings)
    cook = identity.create_staff(
        operations_admin, "Повар", "cook.tests", password, frozenset({Role.KITCHEN})
    )
    _, token = identity.login(cook.login, password, "production-tests")
    yield Kitchen(
        settings,
        identity,
        engine,
        inventory_service(engine, identity),
        production_service(engine, identity),
        operations_admin,
        token,
        cook.id,
    )
    engine.dispose()


def test_production_versions_are_immutable_and_multiple_batches(kitchen: Kitchen) -> None:
    recipe, stock = kitchen.case("2")
    old = next(r for r in kitchen.service.recipes(kitchen.token) if r.id == recipe.subject_id)
    first = kitchen.produce(recipe, stock)
    second_version = kitchen.service.create_recipe(
        kitchen.token,
        uuid4(),
        old.output_item_id,
        1,
        20,
        "300",
        "g",
        "Новая технология",
        [IngredientInput(line.item_id, "0.75", "kg") for line in old.lines],
    )
    assert second_version.version == 2
    second = kitchen.produce(recipe, stock)
    assert first.subject_id != second.subject_id
    finished = next(b for b in kitchen.stock.batches(kitchen.admin) if b.id == first.subject_id)
    assert finished.item_kind == "prepared"
    history = kitchen.service.productions(kitchen.token)
    assert all(
        p.recipe_version == 1 and p.actual_yield == 10
        for p in history
        if p.id in {first.subject_id, second.subject_id}
    )
    assert next(r for r in kitchen.service.recipes(kitchen.token) if r.id == old.id) == old
    with pytest.raises(InventoryError, match="Рецепт изменился"):
        kitchen.service.create_recipe(
            kitchen.token,
            uuid4(),
            old.output_item_id,
            1,
            20,
            "300",
            "g",
            "Устаревшая форма",
            [IngredientInput(line.item_id, "1", "kg") for line in old.lines],
        )
    with kitchen.engine.connect() as connection:
        assert (
            connection.execute(
                select(batches.c.on_hand).where(batches.c.id == stock[0].subject_id)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(movements)
                .where(movements.c.batch_id == first.subject_id)
            ).scalar_one()
            == 1
        )
    for table in (recipes, lines, productions, consumption):
        with pytest.raises(DBAPIError), kitchen.engine.begin() as connection:
            connection.execute(table.delete().where(false()))
        with pytest.raises(DBAPIError), kitchen.engine.begin() as connection:
            connection.execute(
                table.update().where(false()).values(**{next(iter(table.c)).name: uuid4()})
            )


def test_production_duplicate_and_last_ingredient_races(kitchen: Kitchen) -> None:
    recipe, stock = kitchen.case()
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: kitchen.produce(recipe, stock, key), range(2)))
    assert outcomes[0] == outcomes[1]
    with pytest.raises(InventoryError) as mismatch:
        kitchen.produce(recipe, stock, key, amount="0.5")
    assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    recipe, stock = kitchen.case()

    def produce(reverse: bool) -> str:
        try:
            kitchen.produce(recipe, list(reversed(stock)) if reverse else stock)
            return "ok"
        except InventoryError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(produce, (False, True))) == ["INSUFFICIENT_STOCK", "ok"]
    with kitchen.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(productions)
                .where(productions.c.recipe_id == recipe.subject_id)
            ).scalar_one()
            == 1
        )
        assert list(
            connection.execute(
                select(batches.c.on_hand).where(batches.c.id.in_([s.subject_id for s in stock]))
            ).scalars()
        ) == [Decimal(0), Decimal(0)]


def test_production_unfit_reserved_shortage_and_missing_ingredient_rollback(
    kitchen: Kitchen,
) -> None:
    for cause in ("shortage", "suspended", "expired", "reserved", "missing", "duplicate"):
        recipe, stock = kitchen.case()
        last = sorted(stock, key=lambda s: s.subject_id)[-1]
        with kitchen.engine.begin() as connection:
            values: dict[str, object] = {}
            if cause == "shortage":
                values = {"on_hand": Decimal("0.5")}
            elif cause == "suspended":
                values = {"status": "suspended"}
            elif cause == "expired":
                values = {
                    "received_at": datetime.now(UTC) - timedelta(days=2),
                    "expires_at": datetime.now(UTC) - timedelta(days=1),
                }
            elif cause == "reserved":
                values = {"reserved": Decimal("0.5")}
            if values:
                connection.execute(
                    batches.update().where(batches.c.id == last.subject_id).values(**values)
                )
        requested = (
            stock[:1]
            if cause == "missing"
            else stock + [stock[0]]
            if cause == "duplicate"
            else stock
        )
        with pytest.raises(InventoryError):
            kitchen.produce(recipe, requested)
        with kitchen.engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count())
                    .select_from(productions)
                    .where(productions.c.recipe_id == recipe.subject_id)
                ).scalar_one()
                == 0
            )
            assert all(
                connection.execute(
                    select(batches.c.version).where(batches.c.id == s.subject_id)
                ).scalar_one()
                == 1
                for s in stock
            )


def test_production_audit_failure_rolls_back_all_changes(
    kitchen: Kitchen, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe, stock = kitchen.case()
    key = uuid4()

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Тестовый сбой аудита")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresInventoryRepository, "audit", fail)
        with pytest.raises(RuntimeError):
            kitchen.produce(recipe, stock, key)
    result = kitchen.produce(recipe, stock, key)
    assert kitchen.produce(recipe, stock, key) == result
    with kitchen.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(productions)
                .where(productions.c.recipe_id == recipe.subject_id)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(movements)
                .where(movements.c.batch_id == stock[0].subject_id)
            ).scalar_one()
            == 2
        )


def test_production_http_permissions_csrf_and_revoked_replay(
    kitchen: Kitchen, system: tuple[Settings, IdentityService, str]
) -> None:
    _, _, password = system
    recipe, stock = kitchen.case()
    key = uuid4()
    kitchen.produce(recipe, stock, key)
    with TestClient(create_app(kitchen.settings)) as client:
        assert client.get("/api/v1/production/recipes").status_code == 401
        client.cookies.set(kitchen.settings.session_cookie, kitchen.token)
        assert client.get("/api/v1/production/recipes").status_code == 200
        assert client.get("/api/v1/inventory/items").status_code == 403
        assert client.get("/api/v1/production/recipes").headers["cache-control"] == "no-store"
        assert client.post("/api/v1/production/batches", json={}).status_code == 403
        response = client.post(
            "/api/v1/production/batches",
            headers={**headers(client), "Idempotency-Key": str(uuid4())},
            json={
                "recipe_id": str(recipe.subject_id),
                "label": "Проверка",
                "actual_yield": 1.5,
                "expires_at": EXPIRY.isoformat(),
                "suitability_confirmed": True,
                "consumption": [
                    {"batch_id": str(stock[0].subject_id), "quantity": "1", "unit": "kg"}
                ],
            },
        )
        assert response.status_code == 422
    kitchen.identity.assign_roles(kitchen.admin, kitchen.cook_id, frozenset({Role.CASHIER}))
    kitchen.token = kitchen.identity.login("cook.tests", password, "production-demoted")[1]
    try:
        with pytest.raises(IdentityError) as forbidden:
            kitchen.produce(recipe, stock, key)
        assert forbidden.value.code == "FORBIDDEN"
        with pytest.raises(IdentityError):
            kitchen.service.recipes(kitchen.token)
    finally:
        kitchen.identity.assign_roles(kitchen.admin, kitchen.cook_id, frozenset({Role.KITCHEN}))
        kitchen.token = kitchen.identity.login("cook.tests", password, "production-restored")[1]


def test_production_split_raw_batches_and_browser_fixture(
    kitchen: Kitchen, system: tuple[Settings, IdentityService, str]
) -> None:
    _, identity, password = system
    raw = kitchen.stock.create_item(kitchen.admin, uuid4(), "Рис для кухни", "raw", "kg")
    output = kitchen.stock.create_item(
        kitchen.admin, uuid4(), "Каша для кухни", "prepared", "portion"
    )
    now = datetime.now(UTC)
    # Input has at most three decimals; grams preserve six-place base precision.
    stock = [
        kitchen.stock.receive(
            kitchen.admin,
            uuid4(),
            raw.subject_id,
            f"Рис кухня {n}",
            "1250.125",
            "g",
            500,
            now,
            now + timedelta(days=3),
            "Тестовая поставка",
        )
        for n in (1, 2)
    ]
    recipe = kitchen.service.create_recipe(
        kitchen.token,
        uuid4(),
        output.subject_id,
        0,
        12,
        "250",
        "g",
        "Сварить по технологической карте",
        [IngredientInput(raw.subject_id, "1", "kg")],
    )
    result = kitchen.service.produce(
        kitchen.token,
        uuid4(),
        recipe.subject_id,
        "Разные партии",
        11,
        EXPIRY,
        True,
        [ConsumptionInput(s.subject_id, "250.125", "g") for s in stock],
    )
    production = next(
        p for p in kitchen.service.productions(kitchen.token) if p.id == result.subject_id
    )
    assert len(production.consumption) == 2
    assert all(c.quantity == Decimal("0.250125") for c in production.consumption)
    identity.create_staff(kitchen.admin, "Повар", "cook.ui", password, frozenset({Role.KITCHEN}))


def test_recipe_version_race_and_invalid_recipe_lines(kitchen: Kitchen) -> None:
    recipe, stock = kitchen.case("2")
    old = kitchen.service.recipe(kitchen.token, recipe.subject_id)

    def version() -> str:
        try:
            kitchen.service.create_recipe(
                kitchen.token,
                uuid4(),
                old.output_item_id,
                1,
                10,
                "200",
                "g",
                "Новая норма",
                [IngredientInput(line.item_id, "0.5", "kg") for line in old.lines],
            )
            return "ok"
        except InventoryError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: version(), range(2))) == ["STALE_RECIPE", "ok"]
    invalid_lines = [
        [],
        [IngredientInput(old.lines[0].item_id, "1", "kg")] * 2,
        [IngredientInput(old.output_item_id, "1", "kg")],
        [IngredientInput(old.lines[0].item_id, "1", "l")],
        [IngredientInput(old.lines[0].item_id, "0", "kg")],
    ]
    for ingredients in invalid_lines:
        with pytest.raises(InventoryError):
            kitchen.service.create_recipe(
                kitchen.token,
                uuid4(),
                old.output_item_id,
                2,
                10,
                "200",
                "g",
                "Проверка",
                ingredients,
            )
    for confirmed, expiry in ((False, EXPIRY), (True, datetime.now(UTC) - timedelta(seconds=1))):
        with pytest.raises(InventoryError):
            kitchen.service.produce(
                kitchen.token,
                uuid4(),
                recipe.subject_id,
                "Проверка",
                10,
                expiry,
                confirmed,
                [ConsumptionInput(s.subject_id, "1", "kg") for s in stock],
            )
    with kitchen.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(recipes)
                .where(recipes.c.output_item_id == old.output_item_id)
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(productions)
                .where(productions.c.recipe_id == recipe.subject_id)
            ).scalar_one()
            == 0
        )
    with pytest.raises(DBAPIError), kitchen.engine.begin() as connection:
        connection.execute(
            recipes.insert().values(
                id=uuid4(),
                output_item_id=old.output_item_id,
                version=3,
                expected_yield=0,
                portion_quantity=1,
                portion_unit="kg",
                instructions="Проверка CHECK",
                actor_id=kitchen.cook_id,
                created_at=datetime.now(UTC),
            )
        )


def test_production_competes_with_stock_write_off_and_keys_are_actor_scoped(
    kitchen: Kitchen,
) -> None:
    recipe, stock = kitchen.case()

    def produce() -> str:
        try:
            kitchen.produce(recipe, stock)
            return "ok"
        except InventoryError as error:
            return error.code

    def write_off() -> str:
        try:
            kitchen.stock.change(
                kitchen.admin,
                uuid4(),
                stock[0].subject_id,
                "write_off",
                "1",
                "kg",
                "Конкурентное списание",
                1,
            )
            return "ok"
        except InventoryError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(produce), pool.submit(write_off)]
        outcomes = [future.result() for future in futures]
    assert outcomes.count("ok") == 1
    assert set(outcomes) <= {"ok", "STALE_BATCH", "INSUFFICIENT_STOCK"}
    with kitchen.engine.connect() as connection:
        assert (
            connection.execute(
                select(batches.c.on_hand).where(batches.c.id == stock[0].subject_id)
            ).scalar_one()
            == 0
        )
    recipe, stock = kitchen.case("2")
    key = uuid4()
    cook_result = kitchen.produce(recipe, stock, key)
    manager_result = kitchen.service.produce(
        kitchen.admin,
        key,
        recipe.subject_id,
        "Тестовый выпуск",
        10,
        EXPIRY,
        True,
        [ConsumptionInput(s.subject_id, "1", "kg") for s in stock],
    )
    assert cook_result.subject_id != manager_result.subject_id
