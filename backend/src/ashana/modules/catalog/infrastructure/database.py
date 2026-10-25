import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from types import TracebackType
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from ashana.modules.catalog.application.ports import CatalogRepository
from ashana.modules.catalog.domain.models import ALMATY, Entry, MenuEntry, Period
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.shared.domain import BusinessError

metadata = MetaData()
Table("identity_users", metadata, Column("id", Uuid, primary_key=True))
# Read-only stock projection; identity/inventory own and migrate these reference tables.
items = Table(
    "inventory_items",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String),
    Column("kind", String),
    Column("unit", String),
)
images = Table(
    "inventory_item_images",
    metadata,
    Column("item_id", Uuid, primary_key=True),
    Column("digest", String),
)
batches = Table(
    "inventory_batches",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("item_id", Uuid),
    Column("status", String),
    Column("on_hand", Numeric),
    Column("reserved", Numeric),
    Column("received_at", DateTime(timezone=True)),
    Column("expires_at", DateTime(timezone=True)),
)
periods = Table(
    "catalog_periods",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("starts_at", DateTime(timezone=True), nullable=False, index=True),
    Column("ends_at", DateTime(timezone=True), nullable=False),
    Column("published", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "ends_at > starts_at AND ends_at <= starts_at + interval '24 hours'",
        name="ck_catalog_period_window",
    ),
    CheckConstraint(
        "version > 0 AND char_length(name) BETWEEN 1 AND 100", name="ck_catalog_period_values"
    ),
)
entries = Table(
    "catalog_entries",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("period_id", Uuid, ForeignKey("catalog_periods.id"), nullable=False),
    Column("item_id", Uuid, ForeignKey("inventory_items.id"), nullable=False),
    Column("description", String(1000), nullable=False),
    Column("category", String(60), nullable=False),
    Column("portion_label", String(100), nullable=False),
    Column("price_minor", BigInteger, nullable=False),
    Column("published", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("period_id", "item_id", name="uq_catalog_period_item"),
    CheckConstraint(
        "price_minor BETWEEN 0 AND 999999999999 AND version > 0", name="ck_catalog_entry_values"
    ),
    CheckConstraint("char_length(portion_label) BETWEEN 1 AND 100", name="ck_catalog_portion"),
)
audit = Table(
    "catalog_audit",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("entity", String(20), nullable=False),
    Column("subject_id", Uuid, nullable=False, index=True),
    Column("before", JSONB, nullable=True),
    Column("after", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("entity IN ('period','entry')", name="ck_catalog_audit_entity"),
)


class PostgresCatalogRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def periods(self, day: date, offset: int, limit: int) -> list[Period]:
        start = datetime.combine(day, time.min, ALMATY)
        bounds = [periods.c.starts_at >= start]
        if day < date.max:
            bounds.append(periods.c.starts_at < start + timedelta(days=1))
        rows = self.connection.execute(
            select(periods)
            .where(*bounds)
            .order_by(periods.c.starts_at, periods.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [Period(**row) for row in rows]

    def period(self, id: UUID, *, lock: bool = False) -> Period | None:
        query = select(periods).where(periods.c.id == id)
        row = self.connection.execute(query.with_for_update() if lock else query).mappings().first()
        return Period(**row) if row else None

    def save_period(self, period: Period, *, new: bool) -> None:
        query = periods.insert() if new else periods.update().where(periods.c.id == period.id)
        self.connection.execute(query.values(**asdict(period)))

    def open_periods(self, now: datetime) -> list[Period]:
        rows = self.connection.execute(
            select(periods)
            .where(periods.c.ends_at > now)
            .order_by(periods.c.starts_at, periods.c.id)
        ).mappings()
        return [Period(**row) for row in rows]

    def period_items(self, period_id: UUID) -> set[UUID]:
        return set(
            self.connection.execute(
                select(entries.c.item_id).where(entries.c.period_id == period_id)
            ).scalars()
        )

    def entries(self, period_id: UUID, offset: int, limit: int) -> list[Entry]:
        rows = self.connection.execute(
            select(entries, items.c.name, items.c.unit)
            .join(items, entries.c.item_id == items.c.id)
            .where(entries.c.period_id == period_id)
            .order_by(items.c.name, entries.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [Entry(**row) for row in rows]

    def entry(self, id: UUID, *, lock: bool = False) -> Entry | None:
        query = (
            select(entries, items.c.name, items.c.unit)
            .join(items, entries.c.item_id == items.c.id)
            .where(entries.c.id == id)
        )
        row = (
            self.connection.execute(query.with_for_update(of=entries) if lock else query)
            .mappings()
            .first()
        )
        return Entry(**row) if row else None

    def save_entry(self, entry: Entry, *, new: bool) -> None:
        values = asdict(entry)
        values.pop("name")
        values.pop("unit")
        query = entries.insert() if new else entries.update().where(entries.c.id == entry.id)
        try:
            self.connection.execute(query.values(**values))
        except IntegrityError:
            raise BusinessError(
                "MENU_ITEM_EXISTS", "Эта позиция уже добавлена в период. Откройте её для изменения"
            ) from None

    def menu(
        self, now: datetime, offset: int, limit: int, upcoming: bool = False
    ) -> list[MenuEntry]:
        # One statement filters publication/time/stock before pagination, from one MVCC snapshot.
        available = (
            select(
                batches.c.item_id,
                func.sum(batches.c.on_hand - batches.c.reserved).label("available"),
            )
            .where(
                batches.c.status == "active",
                batches.c.expires_at > now,
                batches.c.received_at <= now,
                batches.c.on_hand > batches.c.reserved,
            )
            .group_by(batches.c.item_id)
            .subquery()
        )
        rows = self.connection.execute(
            select(
                entries.c.id,
                entries.c.period_id,
                periods.c.name.label("period_name"),
                periods.c.starts_at,
                periods.c.ends_at,
                items.c.name,
                items.c.unit,
                entries.c.description,
                entries.c.category,
                entries.c.portion_label,
                entries.c.price_minor,
                available.c.available,
                func.coalesce(images.c.digest, "").label("image"),
            )
            .select_from(entries)
            .join(periods, entries.c.period_id == periods.c.id)
            .join(items, entries.c.item_id == items.c.id)
            .join(available, entries.c.item_id == available.c.item_id)
            .outerjoin(images, images.c.item_id == entries.c.item_id)
            .where(
                entries.c.published.is_(True),
                periods.c.published.is_(True),
                periods.c.starts_at <= (now + timedelta(days=1) if upcoming else now),
                periods.c.ends_at > now,
                items.c.kind.in_(("prepared", "purchased")),
            )
            .order_by(periods.c.starts_at, periods.c.id, items.c.name, entries.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [MenuEntry(**dict(row, available=int(row["available"]))) for row in rows]

    def audit(
        self,
        actor: UUID,
        entity: str,
        subject: UUID,
        before: dict[str, object] | None,
        after: dict[str, object],
        now: datetime,
    ) -> None:
        self.connection.execute(
            audit.insert().values(
                id=uuid4(),
                actor_id=actor,
                entity=entity,
                subject_id=subject,
                before=json.loads(json.dumps(before, default=str)),
                after=json.loads(json.dumps(after, default=str)),
                created_at=now,
            )
        )


class PostgresCatalogUnitOfWork:
    def __init__(
        self,
        engine: Engine,
        authorize: Callable[[Connection, str], UUID],
        stock: Callable[[Connection], InventoryRepository],
    ) -> None:
        self.engine, self.authorizer, self.stock_factory = engine, authorize, stock

    def __enter__(self) -> "PostgresCatalogUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.stock = self.stock_factory(self.connection)
        self.repository: CatalogRepository = PostgresCatalogRepository(self.connection)
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
