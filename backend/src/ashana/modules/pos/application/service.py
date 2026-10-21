import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ashana.modules.catalog.domain.models import MenuEntry
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.inventory.domain.models import (
    DirectoryEntry,
    InventoryError,
    Movement,
    Result,
    change_quantity,
    invalid,
)
from ashana.modules.orders.domain.models import Choice, validate_choices
from ashana.modules.pos.application.ports import PosUnitOfWork
from ashana.modules.pos.domain.models import Sale, SaleLine


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
                raise InventoryError("MENU_UNAVAILABLE", "Позиция больше недоступна")
            # Match checkout's period -> entry -> sorted batch lock order.
            periods = {
                id: uow.catalog.period(id, lock=True)
                for id in sorted({c.period_id for c in cards if c})
            }
            lines: list[SaleLine] = []
            for choice in sorted(choices, key=lambda c: c.entry_id):
                entry = uow.catalog.entry(choice.entry_id, lock=True)
                if not entry or not entry.published or entry.period_id not in periods:
                    raise InventoryError("MENU_UNAVAILABLE", "Позиция больше недоступна")
                if entry.price_minor != choice.expected_price_minor:
                    raise InventoryError(
                        "PRICE_CHANGED", "Цена изменилась. Обновите меню и корзину"
                    )
                item = uow.stock.item(entry.item_id)
                if not item or item.kind not in ("prepared", "purchased"):
                    raise InventoryError("MENU_UNAVAILABLE", "Выберите готовую продукцию")
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
                raise InventoryError("MENU_UNAVAILABLE", "Период продажи закрыт или ещё не начался")
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
                        raise InventoryError(
                            "INSUFFICIENT_STOCK", f"Недостаточно свободного остатка: {line.name}"
                        )
            uow.repository.add(sale)
            uow.stock.audit(actor, "pos_attempt", sale.id, now)
            uow.stock.remember(actor, "pos_sale", key, payload, Result(sale.id, 1), now)
            uow.commit()
            return sale

    def payment_methods(self, token: str) -> list[DirectoryEntry]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.stock.directories("payment_method")
