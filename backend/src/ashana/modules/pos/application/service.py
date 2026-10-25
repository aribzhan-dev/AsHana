import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ashana.modules.catalog.domain.models import MenuEntry
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.inventory.domain.models import DirectoryEntry, Movement, change_quantity
from ashana.modules.orders.domain.models import Choice, validate_choices
from ashana.modules.pos.application.ports import PosUnitOfWork
from ashana.modules.pos.domain.models import Sale, SaleLine, SaleReturn
from ashana.shared.domain import BusinessError, Result, invalid, text_value


class PosService:
    def __init__(
        self,
        uow: Callable[[], PosUnitOfWork],
        *,
        expire: Callable[[], object],
        enabled: bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.uow, self.expire, self.enabled, self.clock = uow, expire, enabled, clock

    def menu(self, token: str, offset: int = 0, limit: int = 20) -> list[MenuEntry]:
        with self.uow() as uow:
            uow.authorize(token)
        self.expire()
        with self.uow() as uow:
            uow.authorize(token)
            return uow.catalog.menu(self.clock(), offset, limit)

    def history(self, token: str, offset: int = 0, limit: int = 20) -> list[Sale]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.list(offset, limit)

    def sell(
        self,
        token: str,
        key: UUID,
        choices: list[Choice],
        outcome: str,
        payment_method_id: UUID | None = None,
    ) -> Sale:
        if not self.enabled:
            raise IdentityError("FORBIDDEN", "Тестовая касса недоступна в рабочем режиме")
        validate_choices(choices, 100)
        if outcome not in ("success", "failed", "timeout"):
            raise invalid("outcome", "Выберите результат тестовой оплаты")
        parts: list[object] = [
            outcome,
            [asdict(c) for c in sorted(choices, key=lambda c: c.entry_id)],
        ]
        if payment_method_id is not None:
            parts.append(str(payment_method_id))
        payload = hashlib.sha256(
            json.dumps(parts, sort_keys=True, default=str).encode()
        ).hexdigest()
        with self.uow() as uow:
            uow.authorize(token)
        self.expire()
        with self.uow() as uow:
            actor = uow.authorize(token)
            replay = uow.stock.replay(actor, "pos_sale", key, payload)
            if replay:
                saved = uow.repository.get(replay.subject_id)
                assert saved is not None
                return saved
            method = None
            if payment_method_id is not None:
                method = next(
                    (
                        d
                        for d in uow.stock.directories("payment_method")
                        if d.id == payment_method_id
                    ),
                    None,
                )
                if not method:
                    raise invalid("payment_method_id", "Выберите способ оплаты из настроек")
            cards = [uow.catalog.entry(c.entry_id) for c in choices]
            if any(c is None for c in cards):
                raise BusinessError("MENU_UNAVAILABLE", "Позиция больше недоступна")
            # Match checkout's period -> entry -> sorted batch lock order.
            periods = {
                id: uow.catalog.period(id, lock=True)
                for id in sorted({c.period_id for c in cards if c})
            }
            lines: list[SaleLine] = []
            for choice in sorted(choices, key=lambda c: c.entry_id):
                entry = uow.catalog.entry(choice.entry_id, lock=True)
                if not entry or not entry.published or entry.period_id not in periods:
                    raise BusinessError("MENU_UNAVAILABLE", "Позиция больше недоступна")
                if entry.price_minor != choice.expected_price_minor:
                    raise BusinessError("PRICE_CHANGED", "Цена изменилась. Обновите меню и корзину")
                item = uow.stock.item(entry.item_id)
                if not item or item.kind not in ("prepared", "purchased"):
                    raise BusinessError("MENU_UNAVAILABLE", "Выберите готовую продукцию")
                lines.append(
                    SaleLine(
                        entry.id,
                        item.id,
                        item.name,
                        entry.portion_label,
                        item.unit,
                        choice.quantity,
                        entry.price_minor,
                    )
                )
            ids = uow.reservations.candidates([line.item_id for line in lines])
            batches = {id: uow.stock.batch(id, lock=True) for id in sorted(ids)}
            now = self.clock()
            if any(not p or not p.active_at(now) for p in periods.values()):
                raise BusinessError("MENU_UNAVAILABLE", "Период продажи закрыт или ещё не начался")
            sale = Sale(
                uuid4(),
                actor,
                outcome,
                sum(line.quantity * line.price_minor for line in lines),
                now,
                tuple(lines),
                payment_method_id,
                method.name if method else "",
            )
            if outcome == "success":
                for line in lines:
                    remaining = line.quantity
                    eligible = sorted(
                        (
                            b
                            for b in batches.values()
                            if b
                            and b.item_id == line.item_id
                            and b.status == "active"
                            and b.received_at <= now < b.expires_at
                        ),
                        key=lambda b: (b.expires_at, b.id),
                    )
                    for batch in eligible:
                        take = min(remaining, int(batch.available_at(now)))
                        if not take:
                            continue
                        updated = change_quantity(batch, -Decimal(take))
                        uow.stock.save_batch(updated)
                        batches[batch.id] = updated
                        uow.stock.add_movement(
                            Movement(
                                uuid4(),
                                batch.id,
                                "mock_pos_sale",
                                -Decimal(take),
                                batch.on_hand,
                                updated.on_hand,
                                f"Кассовая продажа {sale.id}",
                                actor,
                                now,
                                updated.version,
                                batch.status,
                                updated.status,
                            )
                        )
                        uow.stock.audit(actor, "mock_pos_sale", batch.id, now)
                        remaining -= take
                        if remaining == 0:
                            break
                    if remaining:
                        raise BusinessError(
                            "INSUFFICIENT_STOCK", f"Недостаточно свободного остатка: {line.name}"
                        )
            uow.repository.add(sale)
            uow.stock.audit(actor, "pos_attempt", sale.id, now)
            uow.stock.remember(actor, "pos_sale", key, payload, Result(sale.id, 1), now)
            uow.commit()
            return sale

    def returns(self, token: str, sale_id: UUID) -> list[SaleReturn]:
        with self.uow() as uow:
            uow.authorize(token)
            if not uow.repository.get(sale_id):
                raise BusinessError("NOT_FOUND", "Продажа не найдена")
            return uow.repository.returns(sale_id)

    def return_sale(
        self,
        token: str,
        key: UUID,
        sale_id: UUID,
        quantities: dict[UUID, int],
        reason: str,
        disposition: str,
    ) -> SaleReturn:
        """Refund part of a counter sale; goods go back on sale or are written off."""
        if disposition not in ("restock", "write_off"):
            raise invalid("disposition", "Выберите: вернуть на склад или списать")
        reason = text_value(reason, "reason", 200)
        if not quantities or any(type(q) is not int or q < 0 for q in quantities.values()):
            raise invalid("lines", "Укажите количество для возврата")
        quantities = {k: q for k, q in quantities.items() if q}
        if not quantities:
            raise invalid("lines", "Укажите количество для возврата")
        payload = hashlib.sha256(
            json.dumps(
                [
                    str(sale_id),
                    sorted((str(k), q) for k, q in quantities.items()),
                    reason,
                    disposition,
                ]
            ).encode()
        ).hexdigest()
        with self.uow() as uow:
            actor = uow.authorize(token, "pos.refund")
            replay = uow.stock.replay(actor, "pos_return", key, payload)
            if replay:
                saved = uow.repository.get_return(replay.subject_id)
                assert saved is not None
                return saved
            sale = uow.repository.get(sale_id, lock=True)
            if not sale or sale.outcome != "success":
                raise BusinessError("NOT_FOUND", "Оплаченная продажа не найдена")
            returned: dict[UUID, int] = {}
            for previous in uow.repository.returns(sale_id):
                for line in previous.lines:
                    returned[line.entry_id] = returned.get(line.entry_id, 0) + line.quantity
            sold = {line.entry_id: line for line in sale.lines}
            lines: list[SaleLine] = []
            for entry_id, quantity in sorted(quantities.items(), key=lambda pair: pair[0]):
                sold_line = sold.get(entry_id)
                if not sold_line:
                    raise invalid("lines", "Позиции нет в этой продаже")
                if quantity > sold_line.quantity - returned.get(entry_id, 0):
                    raise BusinessError(
                        "RETURN_LIMIT", f"Нельзя вернуть больше проданного: {sold_line.name}"
                    )
                lines.append(replace(sold_line, quantity=quantity))
            now = self.clock()
            if disposition == "restock":
                # Put goods back into the batches the sale consumed, newest first.
                consumed = uow.repository.sale_batches(sale_id)
                for line in lines:
                    remaining = line.quantity
                    for batch_id, _ in consumed:
                        batch = uow.stock.batch(batch_id, lock=True)
                        if (
                            not batch
                            or batch.item_id != line.item_id
                            or batch.status != "active"
                            or batch.expires_at <= now
                        ):
                            continue
                        updated = change_quantity(batch, Decimal(remaining))
                        uow.stock.save_batch(updated)
                        uow.stock.add_movement(
                            Movement(
                                uuid4(),
                                batch.id,
                                "pos_return",
                                Decimal(remaining),
                                batch.on_hand,
                                updated.on_hand,
                                f"Возврат продажи {sale_id}: {reason}",
                                actor,
                                now,
                                updated.version,
                                batch.status,
                                updated.status,
                            )
                        )
                        uow.stock.audit(actor, "pos_return", batch.id, now)
                        remaining = 0
                        break
                    if remaining:
                        raise BusinessError(
                            "RETURN_BATCH_CLOSED",
                            f"Партия «{line.name}» закрыта или истекла. "
                            "Оформите возврат со списанием",
                        )
            sale_return = SaleReturn(
                uuid4(),
                sale_id,
                actor,
                now,
                reason,
                disposition,
                sum(line.quantity * line.price_minor for line in lines),
                tuple(lines),
            )
            uow.repository.add_return(sale_return)
            uow.stock.audit(actor, "pos_return", sale_return.id, now)
            uow.stock.remember(actor, "pos_return", key, payload, Result(sale_return.id, 1), now)
            uow.commit()
            return sale_return

    def payment_methods(self, token: str) -> list[DirectoryEntry]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.stock.directories("payment_method")
