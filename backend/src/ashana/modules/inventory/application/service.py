import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from ashana.modules.inventory.application.ports import InventoryRepository, InventoryUnitOfWork
from ashana.modules.inventory.domain.models import (
    Batch,
    DirectoryEntry,
    InventoryError,
    Invoice,
    InvoiceLine,
    Item,
    Movement,
    Result,
    change_quantity,
    invalid,
    quantity,
    text_value,
)


class InventoryService:
    def __init__(
        self,
        uow: Callable[[], InventoryUnitOfWork],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        *,
        cashier: bool = False,
    ) -> None:
        self.uow, self.clock, self.cashier = uow, clock, cashier

    def items(self, token: str, offset: int = 0, limit: int = 50) -> list[Item]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.items(offset, limit)

    def batches(
        self,
        token: str,
        offset: int = 0,
        limit: int = 50,
        warehouse_id: UUID | None = None,
        query: str = "",
    ) -> list[Batch]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.batches(
                offset, limit, ready_only=self.cashier, warehouse_id=warehouse_id, query=query
            )

    def movements(
        self, token: str, batch_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Movement]:
        with self.uow() as uow:
            uow.authorize(token)
            if not uow.repository.batch(batch_id):
                raise InventoryError("NOT_FOUND", "Партия не найдена")
            return uow.repository.movements(batch_id, offset, limit)

    def _write(
        self,
        token: str,
        operation: str,
        key: UUID,
        payload: dict[str, object],
        action: Callable[[InventoryRepository, UUID, datetime], Result],
    ) -> Result:
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        with self.uow() as uow:
            actor = uow.authorize(token)
            replay = uow.repository.replay(actor, operation, key, fingerprint)
            if replay:
                return replay
            now = self.clock()
            result = action(uow.repository, actor, now)
            uow.repository.audit(actor, operation, result.subject_id, now)
            uow.repository.remember(actor, operation, key, fingerprint, result, now)
            uow.commit()
            return result

    def create_item(
        self, token: str, key: UUID, name: str, kind: str, unit: str, barcode: str | None = None
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            item = Item.new(name, kind, unit, barcode)
            repo.add_item(item)
            return Result(item.id, 1)

        return self._write(
            token,
            "item_created",
            key,
            {"name": name, "kind": kind, "unit": unit, "barcode": barcode},
            action,
        )

    def receive(
        self,
        token: str,
        key: UUID,
        item_id: UUID,
        label: str,
        amount: str,
        unit: str,
        total_cost_minor: int,
        received_at: datetime,
        expires_at: datetime,
        source: str,
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            item = repo.item(item_id)
            if not item:
                raise InventoryError("NOT_FOUND", "Позиция склада не найдена")
            if item.kind == "prepared":
                raise InventoryError(
                    "PRODUCTION_REQUIRED", "Собственная продукция приходуется только через выпуск"
                )
            count = quantity(amount, unit, item.unit)
            if not received_at.tzinfo or received_at > now:
                raise invalid(
                    "received_at", "Укажите время прихода с часовым поясом, не позднее текущего"
                )
            if not expires_at.tzinfo or expires_at <= received_at:
                raise invalid(
                    "expires_at",
                    "Срок пригодности должен быть позже прихода и содержать часовой пояс",
                )
            if type(total_cost_minor) is not int or not 0 <= total_cost_minor <= 999999999999:
                raise invalid("total_cost_minor", "Введите стоимость от 0 до 999999999999 тиынов")
            batch = Batch(
                uuid4(),
                item.id,
                text_value(label, "label", 100),
                count,
                Decimal(0),
                "active",
                1,
                total_cost_minor,
                received_at,
                expires_at,
                text_value(source, "source"),
                actor,
                now,
                item.unit,
            )
            repo.add_batch(batch)
            repo.add_movement(
                Movement(
                    uuid4(),
                    batch.id,
                    "receipt",
                    count,
                    Decimal(0),
                    count,
                    batch.source,
                    actor,
                    now,
                    1,
                    "active",
                    "active",
                )
            )
            return Result(batch.id, 1)

        return self._write(
            token,
            "receipt",
            key,
            {
                "item_id": item_id,
                "label": label,
                "quantity": amount,
                "unit": unit,
                "total_cost_minor": total_cost_minor,
                "received_at": received_at,
                "expires_at": expires_at,
                "source": source,
            },
            action,
        )

    def change(
        self,
        token: str,
        key: UUID,
        batch_id: UUID,
        operation: str,
        amount: str | None,
        unit: str | None,
        reason: str,
        expected_version: int,
    ) -> Result:
        if self.cashier and operation != "write_off":
            raise InventoryError("FORBIDDEN", "В кассе разрешено только списание готовой продукции")

        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            batch = repo.batch(batch_id, lock=True)
            if not batch:
                raise InventoryError("NOT_FOUND", "Партия не найдена")
            if self.cashier and (
                operation != "write_off" or batch.item_kind not in ("prepared", "purchased")
            ):
                raise InventoryError("FORBIDDEN", "В кассе можно списать только готовую продукцию")
            if batch.version != expected_version:
                raise InventoryError(
                    "STALE_BATCH", "Остаток изменился. Обновите партию и повторите пересчёт"
                )
            if batch.status == "written_off":
                raise InventoryError("BATCH_CLOSED", "Списанная партия закрыта для изменений")
            note = text_value(reason, "reason")
            if operation in ("write_off", "count"):
                item = repo.item(batch.item_id)
                assert item
                count = quantity(
                    amount or "", unit or "", item.unit, allow_zero=operation == "count"
                )
                delta = -count if operation == "write_off" else count - batch.on_hand
                updated = change_quantity(batch, delta)
                if operation == "write_off" and updated.on_hand == 0:
                    updated = replace(updated, status="written_off")
            elif operation in ("suspend", "resume"):
                if operation == "resume" and batch.expires_at <= now:
                    raise InventoryError(
                        "BATCH_EXPIRED", "Истёкшую партию нельзя вернуть в реализацию"
                    )
                target = "suspended" if operation == "suspend" else "active"
                if batch.status == target:
                    raise InventoryError(
                        "INVALID_TRANSITION", "Партия уже находится в этом состоянии"
                    )
                updated = replace(batch, status=target, version=batch.version + 1)
                delta = Decimal(0)
            else:
                raise invalid("operation", "Неизвестная складская операция")
            repo.save_batch(updated)
            repo.add_movement(
                Movement(
                    uuid4(),
                    batch.id,
                    operation,
                    delta,
                    batch.on_hand,
                    updated.on_hand,
                    note,
                    actor,
                    now,
                    updated.version,
                    batch.status,
                    updated.status,
                )
            )
            return Result(batch.id, updated.version)

        return self._write(
            token,
            "batch_change",
            key,
            {
                "batch_id": batch_id,
                "operation": operation,
                "quantity": amount,
                "unit": unit,
                "reason": reason,
                "expected_version": expected_version,
            },
            action,
        )

    def directories(self, token: str, kind: str) -> list[DirectoryEntry]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.directories(kind)

    def create_directory(self, token: str, key: UUID, kind: str, name: str) -> Result:
        if kind not in ("supplier", "warehouse", "payment_method"):
            raise invalid("kind", "Неизвестный справочник")

        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            entry = DirectoryEntry(uuid4(), kind, text_value(name, "name", 100))
            repo.add_directory(entry)
            return Result(entry.id, 1)

        return self._write(token, "directory_created", key, {"kind": kind, "name": name}, action)

    def invoices(self, token: str, offset: int = 0, limit: int = 20) -> list[Invoice]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.invoices(offset, limit)

    def receive_invoice(
        self,
        token: str,
        key: UUID,
        number: str,
        supplier_id: UUID,
        warehouse_id: UUID,
        payment_method_id: UUID,
        received_at: datetime,
        expenses_minor: int,
        note: str,
        lines: list[InvoiceLine],
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            label = text_value(number, "number", 100)
            if not 1 <= len(lines) <= 100:
                raise invalid("lines", "Добавьте от 1 до 100 товаров")
            if not received_at.tzinfo or received_at > now:
                raise invalid("received_at", "Время прихода не может быть в будущем")
            if type(expenses_minor) is not int or not 0 <= expenses_minor <= 999999999999:
                raise invalid("expenses_minor", "Укажите неотрицательные расходы")
            names = []
            for kind, id in (
                ("supplier", supplier_id),
                ("warehouse", warehouse_id),
                ("payment_method", payment_method_id),
            ):
                entry = next((d for d in repo.directories(kind) if d.id == id), None)
                if not entry:
                    raise invalid(kind, "Выберите значение из справочника")
                names.append(entry.name)
            invoice_id = uuid4()
            snapshots: list[dict[str, object]] = []
            total = 0
            for line in lines:
                item = repo.item(line.item_id)
                if not item or item.kind == "prepared":
                    raise invalid("item_id", "Выберите сырьё или покупной товар")
                count = quantity(line.quantity, line.unit, item.unit)
                if not line.expires_at.tzinfo or line.expires_at <= received_at:
                    raise invalid("expires_at", "Срок годности должен быть позже прихода")
                if (
                    type(line.unit_cost_minor) is not int
                    or not 0 <= line.unit_cost_minor <= 999999999999
                ):
                    raise invalid("unit_cost_minor", "Укажите неотрицательную цену")
                cost = int(
                    (Decimal(line.quantity) * line.unit_cost_minor).quantize(
                        Decimal(1), rounding=ROUND_HALF_UP
                    )
                )
                if cost > 999999999999:
                    raise invalid("unit_cost_minor", "Превышена максимальная стоимость строки")
                batch = Batch(
                    uuid4(),
                    item.id,
                    label,
                    count,
                    Decimal(0),
                    "active",
                    1,
                    cost,
                    received_at,
                    line.expires_at,
                    names[0],
                    actor,
                    now,
                    item.unit,
                    warehouse_id=warehouse_id,
                )
                repo.add_batch(batch)
                repo.add_movement(
                    Movement(
                        uuid4(),
                        batch.id,
                        "receipt",
                        count,
                        Decimal(0),
                        count,
                        f"Накладная {label}",
                        actor,
                        now,
                        1,
                        "active",
                        "active",
                    )
                )
                repo.audit(actor, "receipt", batch.id, now)
                snapshots.append(
                    dict(
                        item_id=str(item.id),
                        name=item.name,
                        barcode=item.barcode,
                        batch_id=str(batch.id),
                        quantity=line.quantity,
                        unit=line.unit,
                        unit_cost_minor=line.unit_cost_minor,
                        total_cost_minor=cost,
                        expires_at=line.expires_at.isoformat(),
                    )
                )
                total += cost
            if total + expenses_minor > 999999999999:
                raise invalid("lines", "Превышена максимальная сумма накладной")
            repo.add_invoice(
                Invoice(
                    invoice_id,
                    label,
                    supplier_id,
                    warehouse_id,
                    payment_method_id,
                    received_at,
                    total,
                    expenses_minor,
                    total + expenses_minor,
                    text_value(note, "note") if note.strip() else "",
                    actor,
                    now,
                    snapshots,
                    *names,
                )
            )
            return Result(invoice_id, 1)

        return self._write(
            token,
            "invoice_received",
            key,
            dict(
                number=number,
                supplier_id=supplier_id,
                warehouse_id=warehouse_id,
                payment_method_id=payment_method_id,
                received_at=received_at,
                expenses_minor=expenses_minor,
                note=note,
                lines=[asdict(line) for line in lines],
            ),
            action,
        )

    def set_barcode(
        self,
        token: str,
        key: UUID,
        item_id: UUID,
        barcode: str | None,
        expected_barcode: str | None,
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            item = repo.item(item_id, lock=True)
            if not item or item.kind != "purchased":
                raise invalid("item_id", "Выберите покупной товар")
            if item.barcode != expected_barcode:
                raise InventoryError("STALE_ITEM", "Штрихкод изменился. Обновите список товаров")
            validated = Item.new(item.name, item.kind, item.unit, barcode)
            repo.update_barcode(item.id, validated.barcode)
            return Result(item.id, 1)

        return self._write(
            token,
            "barcode_changed",
            key,
            dict(item_id=item_id, barcode=barcode, expected_barcode=expected_barcode),
            action,
        )
