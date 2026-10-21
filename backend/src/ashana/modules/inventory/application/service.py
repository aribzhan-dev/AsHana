import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ashana.modules.inventory.application.ports import InventoryRepository, InventoryUnitOfWork
from ashana.modules.inventory.domain.models import (
    Batch,
    InventoryError,
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
    ) -> None:
        self.uow, self.clock = uow, clock

    def items(self, token: str, offset: int = 0, limit: int = 50) -> list[Item]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.items(offset, limit)

    def batches(self, token: str, offset: int = 0, limit: int = 50) -> list[Batch]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.batches(offset, limit)

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

    def create_item(self, token: str, key: UUID, name: str, kind: str, unit: str) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            item = Item.new(name, kind, unit)
            repo.add_item(item)
            return Result(item.id, 1)

        return self._write(
            token, "item_created", key, {"name": name, "kind": kind, "unit": unit}, action
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
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            batch = repo.batch(batch_id, lock=True)
            if not batch:
                raise InventoryError("NOT_FOUND", "Партия не найдена")
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
