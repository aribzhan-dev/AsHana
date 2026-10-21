import hashlib
from collections.abc import Callable
from dataclasses import asdict
from types import TracebackType
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine

from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.infrastructure.database import staff_names
from ashana.modules.production.application.ports import ProductionRepository
from ashana.modules.production.domain.models import Consumption, Production, Recipe, RecipeLine

metadata = MetaData()
# Reference-only tables, owned and migrated by identity/inventory.
Table("identity_users", metadata, Column("id", Uuid, primary_key=True))
items = Table(
    "inventory_items",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String),
    Column("unit", String),
)
batches = Table(
    "inventory_batches",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("item_id", Uuid),
    Column("label", String),
    Column("expires_at", DateTime(timezone=True)),
)
Table("inventory_movements", metadata, Column("id", Uuid, primary_key=True))
recipes = Table(
    "production_recipes",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("output_item_id", Uuid, ForeignKey("inventory_items.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("expected_yield", Integer, nullable=False),
    Column("portion_quantity", Numeric(18, 6), nullable=False),
    Column("portion_unit", String(10), nullable=False),
    Column("instructions", String(2000), nullable=False),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("output_item_id", "version", name="uq_production_recipe_version"),
    CheckConstraint(
        "version > 0 AND expected_yield BETWEEN 1 AND 999999999", name="ck_production_yield"
    ),
    CheckConstraint(
        "portion_quantity > 0 AND portion_quantity <= 999999999 AND portion_unit IN ('kg','l')",
        name="ck_production_portion",
    ),
)
lines = Table(
    "production_recipe_lines",
    metadata,
    Column("recipe_id", Uuid, ForeignKey("production_recipes.id"), primary_key=True),
    Column("item_id", Uuid, primary_key=True),
    Column("quantity", Numeric(18, 6), nullable=False),
    Column("unit", String(10), nullable=False),
    ForeignKeyConstraint(["item_id", "unit"], ["inventory_items.id", "inventory_items.unit"]),
    CheckConstraint(
        "quantity > 0 AND quantity <= 999999999 AND unit IN ('kg','l')", name="ck_production_line"
    ),
)
productions = Table(
    "production_batches",
    metadata,
    Column("id", Uuid, ForeignKey("inventory_batches.id"), primary_key=True),
    Column("recipe_id", Uuid, ForeignKey("production_recipes.id"), nullable=False, index=True),
    Column("actual_yield", Integer, nullable=False),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("actual_yield BETWEEN 1 AND 999999999", name="ck_production_actual_yield"),
)
consumption = Table(
    "production_consumption",
    metadata,
    Column("production_id", Uuid, ForeignKey("production_batches.id"), primary_key=True),
    Column("batch_id", Uuid, ForeignKey("inventory_batches.id"), primary_key=True),
    Column("quantity", Numeric(18, 6), nullable=False),
    Column("unit", String(10), nullable=False),
    Column("item_id", Uuid, nullable=False),
    Column("movement_id", Uuid, ForeignKey("inventory_movements.id"), nullable=False, unique=True),
    ForeignKeyConstraint(["item_id", "unit"], ["inventory_items.id", "inventory_items.unit"]),
    CheckConstraint(
        "quantity > 0 AND quantity <= 999999999 AND unit IN ('kg','l')",
        name="ck_production_consumption",
    ),
)


class PostgresProductionRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def lock_recipe(self, output_item_id: UUID) -> int:
        lock_id = int.from_bytes(
            hashlib.sha256(f"recipe:{output_item_id}".encode()).digest()[:8], signed=True
        )
        self.connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        return int(
            self.connection.execute(
                select(func.coalesce(func.max(recipes.c.version), 0)).where(
                    recipes.c.output_item_id == output_item_id
                )
            ).scalar_one()
        )

    def add_recipe(self, recipe: Recipe) -> None:
        values = asdict(recipe)
        for key in ("lines", "output_name", "output_unit"):
            values.pop(key)
        self.connection.execute(recipes.insert().values(**values))
        self.connection.execute(
            lines.insert(),
            [
                {
                    "recipe_id": recipe.id,
                    "item_id": line.item_id,
                    "quantity": line.quantity,
                    "unit": line.unit,
                }
                for line in recipe.lines
            ],
        )

    def recipe(self, recipe_id: UUID) -> Recipe | None:
        row = (
            self.connection.execute(
                select(
                    recipes, items.c.name.label("output_name"), items.c.unit.label("output_unit")
                )
                .join(items, recipes.c.output_item_id == items.c.id)
                .where(recipes.c.id == recipe_id)
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        ingredients = self.connection.execute(
            select(lines.c.item_id, lines.c.quantity, lines.c.unit, items.c.name.label("item_name"))
            .join(items, lines.c.item_id == items.c.id)
            .where(lines.c.recipe_id == recipe_id)
            .order_by(items.c.name, items.c.id)
        ).mappings()
        return Recipe(**row, lines=tuple(RecipeLine(**line) for line in ingredients))

    def recipes(self, offset: int, limit: int) -> list[Recipe]:
        ids = (
            self.connection.execute(
                select(recipes.c.id)
                .order_by(recipes.c.created_at.desc(), recipes.c.id)
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [recipe for id in ids if (recipe := self.recipe(id)) is not None]

    def add_production(self, production: Production) -> None:
        self.connection.execute(
            productions.insert().values(
                id=production.id,
                recipe_id=production.recipe_id,
                actual_yield=production.actual_yield,
                actor_id=production.actor_id,
                created_at=production.created_at,
            )
        )
        self.connection.execute(
            consumption.insert(),
            [
                {
                    "production_id": production.id,
                    "batch_id": c.batch_id,
                    "quantity": c.quantity,
                    "unit": c.unit,
                    "movement_id": c.movement_id,
                    "item_id": c.item_id,
                }
                for c in production.consumption
            ],
        )

    def productions(self, offset: int, limit: int) -> list[Production]:
        rows = (
            self.connection.execute(
                select(
                    productions,
                    func.coalesce(
                        func.nullif(staff_names.c.nickname, ""), staff_names.c.name
                    ).label("actor_name"),
                    batches.c.label,
                    batches.c.expires_at,
                    items.c.name.label("output_name"),
                    items.c.unit.label("output_unit"),
                    recipes.c.version.label("recipe_version"),
                )
                .join(staff_names, productions.c.actor_id == staff_names.c.id)
                .join(batches, productions.c.id == batches.c.id)
                .join(recipes, productions.c.recipe_id == recipes.c.id)
                .join(items, recipes.c.output_item_id == items.c.id)
                .order_by(productions.c.created_at.desc(), productions.c.id)
                .offset(offset)
                .limit(limit)
            )
            .mappings()
            .all()
        )
        result = []
        for row in rows:
            ingredients = self.connection.execute(
                select(
                    consumption.c.batch_id,
                    consumption.c.quantity,
                    consumption.c.unit,
                    consumption.c.movement_id,
                    consumption.c.item_id,
                    items.c.name.label("item_name"),
                    batches.c.label.label("batch_label"),
                )
                .join(batches, consumption.c.batch_id == batches.c.id)
                .join(items, consumption.c.item_id == items.c.id)
                .where(consumption.c.production_id == row["id"])
                .order_by(items.c.name, batches.c.id)
            ).mappings()
            result.append(
                Production(**row, consumption=tuple(Consumption(**c) for c in ingredients))
            )
        return result


class PostgresProductionUnitOfWork:
    def __init__(
        self,
        engine: Engine,
        authorize: Callable[[Connection, str], UUID],
        stock: Callable[[Connection], InventoryRepository],
    ) -> None:
        self.engine, self.authorizer, self.stock_factory = engine, authorize, stock

    def __enter__(self) -> "PostgresProductionUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.stock = self.stock_factory(self.connection)
        self.repository: ProductionRepository = PostgresProductionRepository(self.connection)
        return self

    def authorize(self, token: str) -> UUID:
        self.connection.execute(text("SELECT pg_advisory_xact_lock_shared(71001)"))
        return self.authorizer(self.connection, token)

    def commit(self) -> None:
        self.transaction.commit()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self.transaction.is_active:
                self.transaction.rollback()
        finally:
            self.connection.close()
