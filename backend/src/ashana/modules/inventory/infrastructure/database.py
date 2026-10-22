import hashlib
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    false,
    func,
    select,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import Select

from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.domain.models import (
    Batch,
    DirectoryEntry,
    InventoryError,
    Invoice,
    InvoicePayment,
    Item,
    Movement,
    Result,
)

metadata = MetaData()
# Reference-only table: the identity migration owns its definition.
staff_names = Table(
    "identity_users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(100)),
    Column("nickname", String(100)),
)
items = Table(
    "inventory_items",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("name_key", String(200), nullable=False, unique=True),
    Column("barcode", String(14), unique=True),
    Column("category", String(100), nullable=False),
    Column("purchase_price_minor", BigInteger, nullable=False),
    Column("sale_price_minor", BigInteger, nullable=False),
    Column("version", Integer, nullable=False),
    Column("always_on_menu", Boolean, nullable=False, server_default=false()),
    Column("kind", String(20), nullable=False),
    Column("unit", String(10), nullable=False),
    CheckConstraint(
        "(kind='raw' AND unit IN ('kg','l')) "
        "OR (kind='purchased' AND unit='pcs') "
        "OR (kind='prepared' AND unit IN ('pcs','portion'))",
        name="ck_inventory_item_unit",
    ),
    CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_inventory_item_name"),
    UniqueConstraint("id", "unit", name="uq_inventory_item_unit"),
)
batches = Table(
    "inventory_batches",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("warehouse_id", Uuid, nullable=False),
    Column("item_id", Uuid, nullable=False),
    Column("unit", String(10), nullable=False),
    Column("label", String(100), nullable=False),
    Column("on_hand", Numeric(18, 6), nullable=False),
    Column("reserved", Numeric(18, 6), nullable=False),
    Column("status", String(20), nullable=False),
    Column("version", Integer, nullable=False),
    Column("total_cost_minor", BigInteger, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("source", String(200), nullable=False),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["item_id", "unit"], ["inventory_items.id", "inventory_items.unit"]),
    CheckConstraint(
        "on_hand >= reserved AND reserved >= 0 AND on_hand <= 999999999", name="ck_inventory_stock"
    ),
    CheckConstraint(
        "unit NOT IN ('pcs','portion') OR (on_hand=trunc(on_hand) AND reserved=trunc(reserved))",
        name="ck_inventory_whole_goods",
    ),
    CheckConstraint(
        "status IN ('active','suspended','written_off') AND (status != 'written_off' OR on_hand=0)",
        name="ck_inventory_state",
    ),
    CheckConstraint(
        "version > 0 AND total_cost_minor BETWEEN 0 AND 999999999999", name="ck_inventory_values"
    ),
    CheckConstraint("expires_at > received_at", name="ck_inventory_expiry"),
)
movements = Table(
    "inventory_movements",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("batch_id", Uuid, ForeignKey("inventory_batches.id"), nullable=False, index=True),
    Column("action", String(20), nullable=False),
    Column("delta", Numeric(18, 6), nullable=False),
    Column("before", Numeric(18, 6), nullable=False),
    Column("after", Numeric(18, 6), nullable=False),
    Column("reason", String(200), nullable=False),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Column("status_before", String(20), nullable=False),
    Column("status_after", String(20), nullable=False),
    UniqueConstraint("batch_id", "version", name="uq_inventory_movement_version"),
    CheckConstraint(
        '"before" + delta = "after" AND "before" >= 0 AND "after" >= 0',
        name="ck_inventory_movement_balance",
    ),
    CheckConstraint(
        "action IN ('receipt','write_off','count','suspend','resume',"
        "'production_consume','production_output','mock_fulfil','mock_pos_sale','pos_return')",
        name="ck_inventory_movement_action",
    ),
)
audit = Table(
    "inventory_audit",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("action", String(30), nullable=False),
    Column("subject_id", Uuid, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
requests = Table(
    "inventory_requests",
    metadata,
    Column("actor_id", Uuid, ForeignKey("identity_users.id"), primary_key=True),
    Column("operation", String(30), primary_key=True),
    Column("key", Uuid, primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("subject_id", Uuid, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


directories = Table(
    "inventory_directories",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("kind", String(20), nullable=False),
    Column("name", String(100), nullable=False),
    Column("name_key", String(200), nullable=False),
    Column("commission_bp", Integer, nullable=False, server_default="0"),
)
images = Table(
    "inventory_item_images",
    metadata,
    Column("item_id", Uuid, primary_key=True),
    Column("content_type", String(20), nullable=False),
    Column("data", LargeBinary, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("actor_id", Uuid, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
invoices = Table(
    "inventory_invoices",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("number", String(100), nullable=False),
    Column("supplier_id", Uuid, nullable=False),
    Column("warehouse_id", Uuid, nullable=False),
    Column("payment_method_id", Uuid, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("goods_minor", BigInteger, nullable=False),
    Column("expenses_minor", BigInteger, nullable=False),
    Column("total_minor", BigInteger, nullable=False),
    Column("note", String(200), nullable=False),
    Column("actor_id", Uuid, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("lines", JSONB, nullable=False),
    Column("supplier_name", String(100), nullable=False),
    Column("warehouse_name", String(100), nullable=False),
    Column("payment_method_name", String(100), nullable=False),
    Column("paid_on_receipt_minor", BigInteger, nullable=False),
)
invoice_payments = Table(
    "inventory_invoice_payments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("invoice_id", Uuid, nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("payment_method_id", Uuid, nullable=False),
    Column("note", String(200), nullable=False),
    Column("actor_id", Uuid, nullable=False),
    Column("paid_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class PostgresInventoryRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def directories(self, kind: str) -> list[DirectoryEntry]:
        return [
            DirectoryEntry(row.id, row.kind, row.name, row.commission_bp)
            for row in self.connection.execute(
                select(directories)
                .where(directories.c.kind == kind)
                .order_by(directories.c.name, directories.c.id)
            )
        ]

    def add_directory(self, entry: DirectoryEntry) -> None:
        try:
            self.connection.execute(
                directories.insert().values(**asdict(entry), name_key=entry.name.casefold())
            )
        except IntegrityError:
            raise InventoryError("DIRECTORY_EXISTS", "Такое название уже существует") from None

    def _invoice_query(self) -> Select[Any]:
        later = (
            select(func.coalesce(func.sum(invoice_payments.c.amount_minor), 0))
            .where(invoice_payments.c.invoice_id == invoices.c.id)
            .scalar_subquery()
        )
        return select(invoices, (invoices.c.paid_on_receipt_minor + later).label("paid_minor"))

    def invoices(self, offset: int, limit: int) -> list[Invoice]:
        return [
            Invoice(**dict(row, paid_minor=int(row["paid_minor"])))
            for row in self.connection.execute(
                self._invoice_query()
                .order_by(invoices.c.created_at.desc(), invoices.c.id)
                .offset(offset)
                .limit(limit)
            ).mappings()
        ]

    def invoice(self, id: UUID, *, lock: bool = False) -> Invoice | None:
        if lock:
            # Invoices are insert-only for the runtime role; lock payments per invoice.
            self.connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"invoice:{id}"},
            )
        row = (
            self.connection.execute(self._invoice_query().where(invoices.c.id == id))
            .mappings()
            .first()
        )
        return Invoice(**dict(row, paid_minor=int(row["paid_minor"]))) if row else None

    def add_invoice_payment(self, payment: InvoicePayment) -> None:
        self.connection.execute(invoice_payments.insert().values(**asdict(payment)))

    def invoice_payments(self, invoice_id: UUID) -> list[InvoicePayment]:
        return [
            InvoicePayment(**row)
            for row in self.connection.execute(
                select(invoice_payments)
                .where(invoice_payments.c.invoice_id == invoice_id)
                .order_by(invoice_payments.c.paid_at, invoice_payments.c.id)
            ).mappings()
        ]

    def add_invoice(self, invoice: Invoice) -> None:
        values = asdict(invoice)
        values.pop("paid_minor")
        try:
            self.connection.execute(invoices.insert().values(**values))
        except IntegrityError:
            raise InventoryError(
                "INVOICE_EXISTS", "Накладная этого поставщика с таким номером уже проведена"
            ) from None

    def _item_query(self) -> Select[Any]:
        return select(
            *[c for c in items.c if c.name != "name_key"],
            func.coalesce(images.c.digest, "").label("image"),
        ).outerjoin(images, images.c.item_id == items.c.id)

    def items(self, offset: int, limit: int, *, kind: str | None = None) -> list[Item]:
        rows = self.connection.execute(
            self._item_query()
            .where(items.c.kind == kind if kind else true())
            .order_by(items.c.name, items.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [Item(**row) for row in rows]

    def item(self, item_id: UUID, *, lock: bool = False) -> Item | None:
        query = self._item_query().where(items.c.id == item_id)
        row = (
            self.connection.execute(query.with_for_update(of=items) if lock else query)
            .mappings()
            .first()
        )
        return Item(**row) if row else None

    def save_image(self, item_id: UUID, data: bytes, actor: UUID, now: datetime) -> str:
        digest = hashlib.sha256(data).hexdigest()
        values = {
            "content_type": "image/webp",
            "data": data,
            "digest": digest,
            "actor_id": actor,
            "updated_at": now,
        }
        updated = self.connection.execute(
            images.update().where(images.c.item_id == item_id).values(**values)
        )
        if not updated.rowcount:
            self.connection.execute(images.insert().values(item_id=item_id, **values))
        return digest

    def delete_image(self, item_id: UUID) -> None:
        self.connection.execute(images.delete().where(images.c.item_id == item_id))

    def image(self, item_id: UUID) -> tuple[bytes, str] | None:
        row = self.connection.execute(
            select(images.c.data, images.c.digest).where(images.c.item_id == item_id)
        ).first()
        return (bytes(row.data), str(row.digest)) if row else None

    def update_barcode(self, item_id: UUID, barcode: str | None) -> None:
        try:
            self.connection.execute(
                items.update()
                .where(items.c.id == item_id)
                .values(barcode=barcode, version=items.c.version + 1)
            )
        except IntegrityError:
            raise InventoryError(
                "ITEM_EXISTS", "Штрихкод уже используется другим товаром"
            ) from None

    def update_item(self, item: Item) -> None:
        values = asdict(item)
        for field in ("id", "kind", "unit", "image"):
            values.pop(field)
        try:
            self.connection.execute(
                items.update()
                .where(items.c.id == item.id)
                .values(**values, name_key=item.name.casefold())
            )
        except IntegrityError:
            raise InventoryError("ITEM_EXISTS", "Название или штрихкод уже используются") from None

    def add_item(self, item: Item) -> None:
        try:
            self.connection.execute(
                items.insert().values(
                    **{k: v for k, v in asdict(item).items() if k != "image"},
                    name_key=item.name.casefold(),
                )
            )
        except IntegrityError:
            raise InventoryError(
                "ITEM_EXISTS",
                "Название или штрихкод уже используются",
                {"name": ["Название уже используется"]},
            ) from None

    def batches(
        self,
        offset: int,
        limit: int,
        *,
        item_id: UUID | None = None,
        ready_only: bool = False,
        warehouse_id: UUID | None = None,
        query: str = "",
    ) -> list[Batch]:
        rows = self.connection.execute(
            select(batches, items.c.name.label("item_name"), items.c.kind.label("item_kind"))
            .join(items)
            .where(batches.c.item_id == item_id if item_id else true())
            .where(items.c.kind.in_(("prepared", "purchased")) if ready_only else true())
            .where(batches.c.warehouse_id == warehouse_id if warehouse_id else true())
            .where(
                items.c.name.ilike("%" + query.replace("%", "\\%").replace("_", "\\_") + "%")
                if query
                else true()
            )
            .order_by(batches.c.created_at.desc(), batches.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [Batch(**row) for row in rows]

    def batch(self, batch_id: UUID, *, lock: bool = False) -> Batch | None:
        query = (
            select(batches, items.c.name.label("item_name"), items.c.kind.label("item_kind"))
            .join(items)
            .where(batches.c.id == batch_id)
        )
        row = (
            self.connection.execute(query.with_for_update(of=batches) if lock else query)
            .mappings()
            .first()
        )
        return Batch(**row) if row else None

    def add_batch(self, batch: Batch) -> None:
        values = asdict(batch)
        values.pop("item_name")
        values.pop("item_kind")
        self.connection.execute(batches.insert().values(**values))

    def save_batch(self, batch: Batch) -> None:
        self.connection.execute(
            batches.update()
            .where(batches.c.id == batch.id)
            .values(on_hand=batch.on_hand, status=batch.status, version=batch.version)
        )

    def add_movement(self, movement: Movement) -> None:
        values = asdict(movement)
        values.pop("actor_name")
        self.connection.execute(movements.insert().values(**values))

    def movements(self, batch_id: UUID, offset: int, limit: int) -> list[Movement]:
        rows = self.connection.execute(
            select(
                movements,
                func.coalesce(func.nullif(staff_names.c.nickname, ""), staff_names.c.name).label(
                    "actor_name"
                ),
            )
            .join(staff_names, movements.c.actor_id == staff_names.c.id)
            .where(movements.c.batch_id == batch_id)
            .order_by(movements.c.version.desc())
            .offset(offset)
            .limit(limit)
        ).mappings()
        return [Movement(**row) for row in rows]

    def replay(self, actor: UUID, operation: str, key: UUID, fingerprint: str) -> Result | None:
        # Lock only this actor/operation/key, before taking the target batch lock.
        lock_id = int.from_bytes(
            hashlib.sha256(f"{actor}:{operation}:{key}".encode()).digest()[:8], signed=True
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
        if not row:
            return None
        if row["fingerprint"] != fingerprint:
            raise InventoryError(
                "IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другими данными"
            )
        return Result(row["subject_id"], row["version"])

    def remember(
        self,
        actor: UUID,
        operation: str,
        key: UUID,
        fingerprint: str,
        result: Result,
        now: datetime,
    ) -> None:
        self.connection.execute(
            requests.insert().values(
                actor_id=actor,
                operation=operation,
                key=key,
                fingerprint=fingerprint,
                subject_id=result.subject_id,
                version=result.version,
                created_at=now,
            )
        )

    def audit(self, actor: UUID, action: str, subject: UUID, now: datetime) -> None:
        self.connection.execute(
            audit.insert().values(
                id=uuid4(), actor_id=actor, action=action, subject_id=subject, created_at=now
            )
        )


class PostgresInventoryUnitOfWork:
    def __init__(self, engine: Engine, authorize: Callable[[Connection, str], UUID]) -> None:
        self.engine, self.authorizer = engine, authorize

    def __enter__(self) -> "PostgresInventoryUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.repository: InventoryRepository = PostgresInventoryRepository(self.connection)
        return self

    def authorize(self, token: str) -> UUID:
        # Share the identity role-change lock so revoked roles cannot commit stock changes.
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
