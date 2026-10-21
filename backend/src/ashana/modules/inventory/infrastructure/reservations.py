from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
    or_,
    select,
)
from sqlalchemy.engine import Connection

from ashana.modules.inventory.infrastructure.database import batches, items, metadata

reservations = Table(
    "inventory_reservations",
    metadata,
    Column("order_id", Uuid, primary_key=True),
    Column("batch_id", Uuid, ForeignKey("inventory_batches.id"), primary_key=True),
    Column("quantity", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("released_at", DateTime(timezone=True)),
    CheckConstraint("quantity > 0", name="ck_reservation_quantity"),
)
reservation_events = Table(
    "inventory_reservation_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("order_id", Uuid, nullable=False, index=True),
    Column("batch_id", Uuid, ForeignKey("inventory_batches.id"), nullable=False),
    Column("action", String(20), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("actor_id", Uuid),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "action IN ('reserve','release','consume') AND quantity > 0", name="ck_reservation_event"
    ),
)


class PostgresReservations:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def candidates(self, item_ids: list[UUID]) -> list[UUID]:
        return list(
            self.connection.execute(
                select(batches.c.id)
                .join(items, items.c.id == batches.c.item_id)
                .where(
                    batches.c.item_id.in_(item_ids),
                    items.c.kind.in_(("prepared", "purchased")),
                    batches.c.status == "active",
                    batches.c.on_hand > batches.c.reserved,
                )
            ).scalars()
        )

    def troubled(self, order_ids: list[UUID], now: datetime) -> set[UUID]:
        return set(
            self.connection.execute(
                select(reservations.c.order_id)
                .join(batches, batches.c.id == reservations.c.batch_id)
                .where(
                    reservations.c.order_id.in_(order_ids),
                    reservations.c.released_at.is_(None),
                    or_(batches.c.status != "active", batches.c.expires_at <= now),
                )
            ).scalars()
        )

    def allocations(self, order_id: UUID) -> list[tuple[UUID, int]]:
        return [
            (row.batch_id, row.quantity)
            for row in self.connection.execute(
                select(reservations.c.batch_id, reservations.c.quantity).where(
                    reservations.c.order_id == order_id, reservations.c.released_at.is_(None)
                )
            )
        ]

    def reserve(
        self, order_id: UUID, batch_id: UUID, quantity: int, actor: UUID, now: datetime
    ) -> None:
        self.connection.execute(
            reservations.insert().values(
                order_id=order_id, batch_id=batch_id, quantity=quantity, created_at=now
            )
        )
        self.connection.execute(
            batches.update()
            .where(batches.c.id == batch_id)
            .values(reserved=batches.c.reserved + quantity, version=batches.c.version + 1)
        )
        self.connection.execute(
            reservation_events.insert().values(
                id=uuid4(),
                order_id=order_id,
                batch_id=batch_id,
                action="reserve",
                quantity=quantity,
                actor_id=actor,
                created_at=now,
            )
        )

    def release(
        self, order_id: UUID, batch_id: UUID, quantity: int, actor: UUID | None, now: datetime
    ) -> None:
        self.connection.execute(
            reservations.update()
            .where(
                reservations.c.order_id == order_id,
                reservations.c.batch_id == batch_id,
                reservations.c.released_at.is_(None),
            )
            .values(released_at=now)
        )
        self.connection.execute(
            batches.update()
            .where(batches.c.id == batch_id)
            .values(reserved=batches.c.reserved - quantity, version=batches.c.version + 1)
        )
        self.connection.execute(
            reservation_events.insert().values(
                id=uuid4(),
                order_id=order_id,
                batch_id=batch_id,
                action="release",
                quantity=quantity,
                actor_id=actor,
                created_at=now,
            )
        )

    def consume(
        self, order_id: UUID, batch_id: UUID, quantity: int, actor: UUID, now: datetime
    ) -> None:
        self.connection.execute(
            reservations.update()
            .where(
                reservations.c.order_id == order_id,
                reservations.c.batch_id == batch_id,
                reservations.c.released_at.is_(None),
            )
            .values(released_at=now)
        )
        self.connection.execute(
            batches.update()
            .where(batches.c.id == batch_id)
            .values(
                reserved=batches.c.reserved - quantity,
                on_hand=batches.c.on_hand - quantity,
                version=batches.c.version + 1,
            )
        )
        self.connection.execute(
            reservation_events.insert().values(
                id=uuid4(),
                order_id=order_id,
                batch_id=batch_id,
                action="consume",
                quantity=quantity,
                actor_id=actor,
                created_at=now,
            )
        )
