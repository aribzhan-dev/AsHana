import json
from collections.abc import Callable
from dataclasses import asdict
from types import TracebackType
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Uuid,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, Engine, RowMapping

from ashana.modules.catalog.application.ports import CatalogRepository
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.application.reservations import ReservationRepository
from ashana.modules.pos.application.ports import SaleRepository
from ashana.modules.pos.domain.models import Sale, SaleLine

metadata = MetaData()
Table("identity_users", metadata, Column("id", Uuid, primary_key=True))
sales = Table(
    "pos_attempts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("payment_method_id", Uuid),
    Column("payment_method_name", String(100), nullable=False),
    Column("outcome", String(10), nullable=False),
    Column("mode", String(10), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("total_minor", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("lines", JSONB, nullable=False),
    CheckConstraint(
        "outcome IN ('success','failed','timeout') AND mode = 'mock' AND currency = 'KZT'",
        name="ck_pos_mode",
    ),
    CheckConstraint("total_minor BETWEEN 0 AND 99999999999900", name="ck_pos_total"),
    CheckConstraint(
        "jsonb_typeof(lines) = 'array' AND jsonb_array_length(lines) BETWEEN 1 AND 100",
        name="ck_pos_lines",
    ),
)


def from_row(row: RowMapping) -> Sale:
    values = dict(row)
    values.pop("mode")
    values.pop("currency")
    values["lines"] = tuple(
        SaleLine(**dict(line, entry_id=UUID(line["entry_id"]), item_id=UUID(line["item_id"])))
        for line in values["lines"]
    )
    return Sale(**values)


class PostgresSaleRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def get(self, id: UUID) -> Sale | None:
        row = self.connection.execute(select(sales).where(sales.c.id == id)).mappings().first()
        return from_row(row) if row else None

    def list(self, offset: int, limit: int) -> list[Sale]:
        return [
            from_row(row)
            for row in self.connection.execute(
                select(sales)
                .order_by(sales.c.created_at.desc(), sales.c.id)
                .offset(offset)
                .limit(limit)
            ).mappings()
        ]

    def add(self, sale: Sale) -> None:
        values = asdict(sale)
        values["lines"] = json.loads(json.dumps(values["lines"], default=str))
        self.connection.execute(sales.insert().values(**values, mode="mock", currency="KZT"))


class PostgresPosUnitOfWork:
    def __init__(
        self,
        engine: Engine,
        authorize: Callable[[Connection, str], UUID],
        catalog: Callable[[Connection], CatalogRepository],
        stock: Callable[[Connection], InventoryRepository],
        reservations: Callable[[Connection], ReservationRepository],
    ) -> None:
        self.engine, self.authorizer = engine, authorize
        self.catalog_factory, self.stock_factory, self.reservations_factory = (
            catalog,
            stock,
            reservations,
        )

    def __enter__(self) -> "PostgresPosUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.repository: SaleRepository = PostgresSaleRepository(self.connection)
        self.catalog = self.catalog_factory(self.connection)
        self.stock = self.stock_factory(self.connection)
        self.reservations = self.reservations_factory(self.connection)
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
