import hashlib
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from types import TracebackType
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    case,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, Engine, RowMapping

from ashana.modules.catalog.application.ports import CatalogRepository
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.application.reservations import ReservationRepository
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.notifications.application.ports import NotificationWriter
from ashana.modules.orders.application.ports import OrderRepository
from ashana.modules.orders.domain.models import Order, OrderLine, Slot

metadata = MetaData()
Table("catalog_periods", metadata, Column("id", Uuid, primary_key=True))
Table("identity_users", metadata, Column("id", Uuid, primary_key=True))
guests = Table(
    "order_guests",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
slots = Table(
    "order_slots",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("period_id", Uuid, ForeignKey("catalog_periods.id"), nullable=False, index=True),
    Column("starts_at", DateTime(timezone=True), nullable=False),
    Column("ends_at", DateTime(timezone=True), nullable=False),
    Column("cutoff_at", DateTime(timezone=True), nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("occupied", Integer, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    CheckConstraint(
        "capacity BETWEEN 1 AND 1000 AND occupied BETWEEN 0 AND capacity AND version > 0",
        name="ck_order_slot_capacity",
    ),
    CheckConstraint("cutoff_at <= starts_at AND starts_at < ends_at", name="ck_order_slot_window"),
)
drafts = Table(
    "checkout_drafts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("guest_id", Uuid, ForeignKey("order_guests.id"), nullable=False, index=True),
    Column("slot_id", Uuid, ForeignKey("order_slots.id"), nullable=False),
    Column("status", String(30), nullable=False),
    Column("total_minor", BigInteger, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Column("lines", JSONB, nullable=False),
    Column("pickup_code", String(8)),
    CheckConstraint("pickup_code IS NULL OR pickup_code ~ '^[0-9A-F]{8}$'", name="ck_pickup_code"),
    Column("slot_starts_at", DateTime(timezone=True), nullable=False),
    Column("slot_ends_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending_payment','confirmed','preparing','ready','completed',"
        "'cancelled','expired','no_show')",
        name="ck_order_status",
    ),
    CheckConstraint("total_minor >= 0 AND version > 0", name="ck_order_values"),
)
payment_attempts = Table(
    "payment_attempts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("checkout_id", Uuid, ForeignKey("checkout_drafts.id"), nullable=False),
    Column("mode", String(10), nullable=False),
    Column("outcome", String(20), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "mode = 'mock' AND outcome IN ('success','failed','timeout','refunded') "
        "AND amount_minor >= 0",
        name="ck_payment_mock",
    ),
)
orders = Table(
    "orders",
    metadata,
    Column("id", Uuid, ForeignKey("checkout_drafts.id"), primary_key=True),
    Column("payment_id", Uuid, ForeignKey("payment_attempts.id"), nullable=False, unique=True),
    Column("total_minor", BigInteger, nullable=False),
    Column("mode", String(10), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("total_minor >= 0 AND mode = 'mock'", name="ck_order_paid"),
)

requests = Table(
    "order_requests",
    metadata,
    Column("actor_id", Uuid, primary_key=True),
    Column("operation", String(30), primary_key=True),
    Column("key", Uuid, primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("subject_id", Uuid, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
events = Table(
    "order_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("subject_id", Uuid, nullable=False, index=True),
    Column("actor_id", Uuid),
    Column("kind", String(30), nullable=False),
    Column("snapshot", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def order_values(order: Order) -> dict[str, object]:
    values = asdict(order)
    values.pop("stock_issue")
    values["lines"] = [
        dict(asdict(line), entry_id=str(line.entry_id), item_id=str(line.item_id))
        for line in order.lines
    ]
    return values


class PostgresOrderRepository:
    def __init__(self, connection: Connection, notifications: NotificationWriter) -> None:
        self.connection = connection
        self.notifications = notifications

    def guest(self, token_hash: str, now: datetime, *, lock: bool = False) -> UUID | None:
        query = select(guests.c.id).where(
            guests.c.token_hash == token_hash, guests.c.expires_at > now
        )
        return self.connection.execute(
            query.with_for_update() if lock else query
        ).scalar_one_or_none()

    def add_guest(self, id: UUID, token_hash: str, now: datetime, expires: datetime) -> None:
        self.connection.execute(
            guests.insert().values(id=id, token_hash=token_hash, created_at=now, expires_at=expires)
        )

    def slots(self, period_id: UUID, now: datetime, *, staff: bool = False) -> list[Slot]:
        query = select(slots).where(slots.c.period_id == period_id)
        if not staff:
            query = query.where(
                slots.c.enabled.is_(True),
                slots.c.cutoff_at >= now,
                slots.c.occupied < slots.c.capacity,
            )
        return [
            Slot(**row)
            for row in self.connection.execute(
                query.order_by(slots.c.starts_at, slots.c.id).limit(100)
            ).mappings()
        ]

    def slot(self, id: UUID, *, lock: bool = False) -> Slot | None:
        query = select(slots).where(slots.c.id == id)
        row = self.connection.execute(query.with_for_update() if lock else query).mappings().first()
        return Slot(**row) if row else None

    def save_slot(self, slot: Slot, actor: UUID, now: datetime, *, new: bool = False) -> None:
        query = slots.insert() if new else slots.update().where(slots.c.id == slot.id)
        self.connection.execute(query.values(**asdict(slot)))
        self.connection.execute(
            events.insert().values(
                id=uuid4(),
                subject_id=slot.id,
                actor_id=actor,
                kind="slot_saved",
                snapshot={
                    "version": slot.version,
                    "capacity": slot.capacity,
                    "enabled": slot.enabled,
                    "starts_at": slot.starts_at.isoformat(),
                    "ends_at": slot.ends_at.isoformat(),
                    "cutoff_at": slot.cutoff_at.isoformat(),
                },
                created_at=now,
            )
        )

    def occupy(self, slot: Slot, delta: int) -> None:
        self.connection.execute(
            slots.update()
            .where(slots.c.id == slot.id)
            .values(occupied=slot.occupied + delta, version=slot.version + 1)
        )

    def active_count(self, guest: UUID) -> int:
        return int(
            self.connection.execute(
                select(func.count())
                .select_from(drafts)
                .where(
                    drafts.c.guest_id == guest,
                    drafts.c.status.in_(("pending_payment", "confirmed", "preparing", "ready")),
                )
            ).scalar_one()
        )

    def _order(self, row: RowMapping) -> Order:
        values = dict(row)
        lines = values.pop("lines")
        assert isinstance(lines, list)
        parsed = tuple(
            OrderLine(**dict(line, entry_id=UUID(line["entry_id"]), item_id=UUID(line["item_id"])))
            for line in lines
        )
        return Order(**values, lines=parsed)

    def order(self, id: UUID, *, lock: bool = False) -> Order | None:
        query = select(drafts).where(drafts.c.id == id)
        row = self.connection.execute(query.with_for_update() if lock else query).mappings().first()
        return self._order(row) if row else None

    def orders(
        self, guest: UUID | None, offset: int, limit: int, state: str = "all"
    ) -> list[Order]:
        query = select(drafts).join(orders, orders.c.id == drafts.c.id)
        if state == "active":
            query = query.where(drafts.c.status.in_(("confirmed", "preparing", "ready")))
        elif state == "closed":
            query = query.where(drafts.c.status.in_(("completed", "cancelled", "no_show")))
        if guest is not None:
            query = query.where(drafts.c.guest_id == guest)
            query = query.order_by(drafts.c.created_at.desc(), drafts.c.id)
        else:
            query = query.order_by(
                case((drafts.c.status.in_(("confirmed", "preparing", "ready")), 0), else_=1),
                drafts.c.slot_starts_at,
                drafts.c.created_at,
                drafts.c.id,
            )
        return [
            self._order(row)
            for row in self.connection.execute(query.offset(offset).limit(limit)).mappings()
        ]

    def checkouts(self, guest: UUID, offset: int, limit: int) -> list[Order]:
        query = (
            select(drafts)
            .where(
                drafts.c.guest_id == guest,
                drafts.c.status.in_(("pending_payment", "cancelled", "expired")),
                drafts.c.id.not_in(select(orders.c.id)),
            )
            .order_by(drafts.c.created_at.desc(), drafts.c.id)
            .offset(offset)
            .limit(limit)
        )
        return [self._order(row) for row in self.connection.execute(query).mappings()]

    def payment(self, order: Order, outcome: str, now: datetime) -> None:
        payment_id = uuid4()
        self.connection.execute(
            payment_attempts.insert().values(
                id=payment_id,
                checkout_id=order.id,
                mode="mock",
                outcome=outcome,
                amount_minor=order.total_minor,
                created_at=now,
            )
        )
        if outcome == "success":
            self.connection.execute(
                orders.insert().values(
                    id=order.id,
                    payment_id=payment_id,
                    total_minor=order.total_minor,
                    mode="mock",
                    created_at=now,
                )
            )

    def add_order(self, order: Order) -> None:
        self.connection.execute(drafts.insert().values(**order_values(order)))

    def save_order(self, order: Order) -> None:
        self.connection.execute(
            drafts.update()
            .where(drafts.c.id == order.id)
            .values(
                status=order.status,
                updated_at=order.updated_at,
                version=order.version,
                pickup_code=order.pickup_code,
            )
        )

    def due(self, now: datetime, limit: int) -> list[UUID]:
        return list(
            self.connection.execute(
                select(drafts.c.id)
                .where(drafts.c.status == "pending_payment", drafts.c.expires_at <= now)
                .order_by(drafts.c.expires_at)
                .limit(limit)
            ).scalars()
        )

    def replay(self, actor: UUID, operation: str, key: UUID, fingerprint: str) -> UUID | None:
        lock_id = int.from_bytes(
            hashlib.sha256(f"order:{actor}:{operation}:{key}".encode()).digest()[:8], signed=True
        )
        self.connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        row = (
            self.connection.execute(
                select(requests).where(
                    requests.c.actor_id == actor,
                    requests.c.operation == operation,
                    requests.c.key == key,
                )
            )
            .mappings()
            .first()
        )
        if row and row["fingerprint"] != fingerprint:
            raise InventoryError(
                "IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другими данными"
            )
        return row["subject_id"] if row else None

    def remember(
        self, actor: UUID, operation: str, key: UUID, fingerprint: str, subject: UUID, now: datetime
    ) -> None:
        self.connection.execute(
            requests.insert().values(
                actor_id=actor,
                operation=operation,
                key=key,
                fingerprint=fingerprint,
                subject_id=subject,
                created_at=now,
            )
        )

    def event(self, order: Order, actor: UUID | None, kind: str, now: datetime) -> None:
        labels = {
            "confirmed": "Новый заказ — тестовая оплата подтверждена",
            "cancelled": "Заказ отменён",
            "paid_cancelled": "Заказ отменён — тестовый возврат",
            "expired": "Резерв истёк",
            "preparing": "Заказ комплектуется",
            "ready": "Заказ готов к выдаче",
            "completed": "Заказ выдан (ДЕМО)",
        }
        lines = "\n".join(f"{line.name}: {line.quantity} шт/порц." for line in order.lines)
        event_id = uuid4()
        local_time = order.slot_starts_at.astimezone(ZoneInfo("Asia/Almaty")).strftime(
            "%d.%m.%Y %H:%M"
        )
        message = (
            f"AsHana · {labels.get(kind, kind)}\nЗаказ {order.id}\n{lines}\n"
            f"Сумма: {order.total_minor // 100},{order.total_minor % 100:02d} ₸\n"
            f"Выдача: {local_time} (Астана)\nСобытие: {event_id}\n"
            "ДЕМО: реальные деньги не списывались. Не является реальной оплатой еды."
        )
        if kind in ("confirmed", "paid_cancelled", "preparing", "ready", "completed"):
            self.notifications.enqueue(event_id, message, now)
        self.connection.execute(
            events.insert().values(
                id=uuid4(),
                subject_id=order.id,
                actor_id=actor,
                kind=kind,
                snapshot={"status": order.status, "version": order.version},
                created_at=now,
            )
        )


class PostgresOrderUnitOfWork:
    def __init__(
        self,
        engine: Engine,
        authorize: Callable[[Connection, str, str], UUID],
        catalog: Callable[[Connection], CatalogRepository],
        stock: Callable[[Connection], InventoryRepository],
        reservations: Callable[[Connection], ReservationRepository],
        notifications: Callable[[Connection], NotificationWriter],
    ) -> None:
        (
            self.engine,
            self.authorizer,
            self.catalog_factory,
            self.stock_factory,
            self.reservations_factory,
        ) = engine, authorize, catalog, stock, reservations

        self.notifications_factory = notifications

    def __enter__(self) -> "PostgresOrderUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.repository: OrderRepository = PostgresOrderRepository(
            self.connection, self.notifications_factory(self.connection)
        )
        self.catalog = self.catalog_factory(self.connection)
        self.stock = self.stock_factory(self.connection)
        self.reservations = self.reservations_factory(self.connection)
        return self

    def authorize(self, token: str, permission: str) -> UUID:
        self.connection.execute(text("SELECT pg_advisory_xact_lock_shared(71001)"))
        return self.authorizer(self.connection, token, permission)

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
