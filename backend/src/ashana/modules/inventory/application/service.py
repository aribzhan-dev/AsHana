from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ashana.modules.inventory.application.base import InventoryBase, known_category
from ashana.modules.inventory.application.directories import DirectoryOperations
from ashana.modules.inventory.application.ports import InventoryRepository, InventoryUnitOfWork
from ashana.modules.inventory.application.receiving import ReceivingOperations
from ashana.modules.inventory.domain.models import (
    Batch,
    Item,
    Movement,
    change_quantity,
    quantity,
)
from ashana.shared.domain import BusinessError, Result, invalid, text_value


class InventoryService(DirectoryOperations, ReceivingOperations, InventoryBase):
    def __init__(
        self,
        uow: Callable[[], InventoryUnitOfWork],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        *,
        cashier: bool = False,
        photos: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.uow, self.clock, self.cashier = uow, clock, cashier
        # Re-encodes uploads (size, format, metadata); supplied by infrastructure.
        self.photos = photos

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
                raise BusinessError("NOT_FOUND", "Партия не найдена")
            return uow.repository.movements(batch_id, offset, limit)

    def create_item(
        self,
        token: str,
        key: UUID,
        name: str,
        kind: str,
        unit: str,
        barcode: str | None = None,
        category: str = "",
        purchase_price_minor: int = 0,
        sale_price_minor: int = 0,
        always_on_menu: bool = False,
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            item = Item.new(
                name,
                kind,
                unit,
                barcode,
                known_category(repo, category),
                purchase_price_minor,
                sale_price_minor,
                always_on_menu,
            )
            repo.add_item(item)
            return Result(item.id, 1)

        return self._write(
            token,
            "item_created",
            key,
            {
                "name": name,
                "kind": kind,
                "unit": unit,
                "barcode": barcode,
                **(
                    {
                        "category": category,
                        "purchase_price_minor": purchase_price_minor,
                        "sale_price_minor": sale_price_minor,
                    }
                    if category or purchase_price_minor or sale_price_minor
                    else {}
                ),
                **({"always_on_menu": True} if always_on_menu else {}),
            },
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
                raise BusinessError("NOT_FOUND", "Позиция склада не найдена")
            if item.kind == "prepared":
                raise BusinessError(
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
            raise BusinessError("FORBIDDEN", "В кассе разрешено только списание готовой продукции")

        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            batch = repo.batch(batch_id, lock=True)
            if not batch:
                raise BusinessError("NOT_FOUND", "Партия не найдена")
            if self.cashier and (
                operation != "write_off" or batch.item_kind not in ("prepared", "purchased")
            ):
                raise BusinessError("FORBIDDEN", "В кассе можно списать только готовую продукцию")
            if batch.version != expected_version:
                raise BusinessError(
                    "STALE_BATCH", "Остаток изменился. Обновите партию и повторите пересчёт"
                )
            if batch.status == "written_off":
                raise BusinessError("BATCH_CLOSED", "Списанная партия закрыта для изменений")
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
                    raise BusinessError(
                        "BATCH_EXPIRED", "Истёкшую партию нельзя вернуть в реализацию"
                    )
                target = "suspended" if operation == "suspend" else "active"
                if batch.status == target:
                    raise BusinessError(
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

    def edit_item(
        self,
        token: str,
        key: UUID,
        item_id: UUID,
        name: str,
        barcode: str | None,
        category: str,
        purchase_price_minor: int,
        sale_price_minor: int,
        expected_version: int,
        always_on_menu: bool = False,
    ) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            item = repo.item(item_id, lock=True)
            if not item:
                raise BusinessError("NOT_FOUND", "Товар не найден")
            if item.version != expected_version:
                raise BusinessError(
                    "STALE_ITEM", "Товар изменился. Обновите список перед редактированием"
                )
            updated = Item.new(
                name,
                item.kind,
                item.unit,
                barcode,
                known_category(repo, category),
                purchase_price_minor,
                sale_price_minor,
                always_on_menu,
            )

            updated = replace(updated, id=item.id, version=item.version + 1)
            repo.update_item(updated)
            return Result(item.id, updated.version)

        return self._write(
            token,
            "item_updated",
            key,
            dict(
                item_id=item_id,
                name=name,
                barcode=barcode,
                category=category,
                purchase_price_minor=purchase_price_minor,
                sale_price_minor=sale_price_minor,
                expected_version=expected_version,
                **({"always_on_menu": True} if always_on_menu else {}),
            ),
            action,
        )

    def set_image(self, token: str, item_id: UUID, data: bytes) -> str:
        with self.uow() as uow:
            uow.authorize(token)
        if not self.photos:
            raise invalid("image", "Загрузка фото недоступна")
        # CPU-heavy decoding happens before the transaction and only for staff.
        photo = self.photos(data)
        with self.uow() as uow:
            actor = uow.authorize(token)
            item = uow.repository.item(item_id, lock=True)
            if not item or item.kind == "raw":
                raise BusinessError("NOT_FOUND", "Фото добавляется к товарам и блюдам меню")
            now = self.clock()
            digest = uow.repository.save_image(item_id, photo, actor, now)
            uow.repository.audit(actor, "item_image_set", item_id, now)
            uow.commit()
            return digest

    def image(self, token: str, item_id: UUID) -> bytes | None:
        with self.uow() as uow:
            uow.authorize(token)
            found = uow.repository.image(item_id)
            return found[0] if found else None

    def remove_image(self, token: str, item_id: UUID) -> None:
        with self.uow() as uow:
            actor = uow.authorize(token)
            if not uow.repository.item(item_id, lock=True):
                raise BusinessError("NOT_FOUND", "Товар не найден")
            uow.repository.delete_image(item_id)
            uow.repository.audit(actor, "item_image_removed", item_id, self.clock())
            uow.commit()

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
                raise BusinessError("STALE_ITEM", "Штрихкод изменился. Обновите список товаров")
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
