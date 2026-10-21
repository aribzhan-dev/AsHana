import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.inventory.domain.models import InventoryError, Movement, invalid
from ashana.modules.orders.application.ports import OrderUnitOfWork
from ashana.modules.orders.domain.models import (
    Choice,
    Order,
    OrderLine,
    OrderPolicy,
    Slot,
    validate_choices,
)


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def guest_hash(token: str) -> str:
    return hashlib.sha256(f"ashana-guest:{token}".encode()).hexdigest()


class OrderService:
    def __init__(
        self,
        uow: Callable[[], OrderUnitOfWork],
        policy: OrderPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        allow_request: Callable[[str, int, int], bool] | None = None,
    ) -> None:
        self.uow, self.policy, self.clock = uow, policy or OrderPolicy(), clock
        self.allow_request = allow_request

    def _guest(self, uow: OrderUnitOfWork, token: str, *, lock: bool = False) -> UUID:
        guest = (
            uow.repository.guest(guest_hash(token), self.clock(), lock=lock)
            if token and len(token) <= 128
            else None
        )
        if not guest:
            raise IdentityError("UNAUTHENTICATED", "Доступ гостя истёк. Откройте меню заново")
        return guest

    def start_guest(self, token: str, address: str = "local") -> str | None:
        with self.uow() as uow:
            now = self.clock()
            if token and len(token) <= 128 and uow.repository.guest(guest_hash(token), now):
                return None
            if self.allow_request and not self.allow_request(
                "guest:" + fingerprint(address), 600, 3600
            ):
                raise IdentityError("RATE_LIMITED", "Слишком много запросов. Попробуйте позже")
            fresh = secrets.token_urlsafe(32)
            uow.repository.add_guest(uuid4(), guest_hash(fresh), now, now + timedelta(days=30))
            uow.commit()
            return fresh

    def slots(self, period: UUID, token: str | None = None) -> list[Slot]:
        self.expire()
        with self.uow() as uow:
            if token is not None:
                uow.authorize(token, "catalog.manage")
            deadline = self.clock()
            if token is None:
                deadline += timedelta(seconds=self.policy.reservation_seconds)
            return uow.repository.slots(period, deadline, staff=token is not None)

    def save_slot(
        self,
        token: str,
        key: UUID,
        id: UUID | None,
        period_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        cutoff_at: datetime,
        capacity: int,
        enabled: bool,
        expected_version: int,
    ) -> UUID:
        payload = fingerprint(
            [id, period_id, starts_at, ends_at, cutoff_at, capacity, enabled, expected_version]
        )
        with self.uow() as uow:
            actor = uow.authorize(token, "catalog.manage")
            replay = uow.repository.replay(actor, "slot", key, payload)
            if replay:
                return replay
            current = uow.repository.slot(id, lock=True) if id else None
            if id and not current:
                raise InventoryError("NOT_FOUND", "Слот не найден")
            if expected_version != (current.version if current else 0):
                raise InventoryError("STALE_ORDER", "Слот изменился. Обновите список")
            period = uow.catalog.period(period_id, lock=True)
            if not period or any(not t.tzinfo for t in (starts_at, ends_at, cutoff_at)):
                raise invalid("starts_at", "Выберите период и время с часовым поясом")
            if (
                not period.starts_at <= starts_at < ends_at <= period.ends_at
                or cutoff_at > starts_at - timedelta(minutes=self.policy.cutoff_minutes)
            ):
                raise invalid(
                    "ends_at",
                    "Слот должен быть внутри периода; приём закрывается минимум "
                    f"за {self.policy.cutoff_minutes} минут",
                )
            if not 1 <= capacity <= 1000:
                raise invalid("capacity", "Вместимость должна быть от 1 до 1000 заказов")
            if current and (
                current.period_id != period_id
                or current.occupied
                and (current.starts_at, current.ends_at, current.cutoff_at)
                != (starts_at, ends_at, cutoff_at)
            ):
                raise invalid("starts_at", "Нельзя менять время занятого слота или его период")
            if capacity < (current.occupied if current else 0):
                raise invalid("capacity", "Вместимость меньше числа занятых мест")
            slot = Slot(
                id or uuid4(),
                period_id,
                starts_at,
                ends_at,
                cutoff_at,
                capacity,
                current.occupied if current else 0,
                enabled,
                expected_version + 1,
            )
            uow.repository.save_slot(slot, actor, self.clock(), new=current is None)
            uow.repository.remember(actor, "slot", key, payload, slot.id, self.clock())
            uow.commit()
            return slot.id

    def checkout(self, token: str, key: UUID, slot_id: UUID, choices: list[Choice]) -> Order:
        validate_choices(choices, self.policy.max_portions)
        payload = fingerprint(
            [slot_id, sorted((asdict(c) for c in choices), key=lambda c: str(c["entry_id"]))]
        )
        self.expire()
        with self.uow() as uow:
            guest = self._guest(uow, token, lock=True)
            if self.allow_request and not self.allow_request(f"checkout:{guest}", 30, 60):
                raise IdentityError("RATE_LIMITED", "Слишком много запросов. Попробуйте позже")
            replay = uow.repository.replay(guest, "checkout", key, payload)
            if replay:
                order = uow.repository.order(replay)
                assert order is not None
                return order
            if uow.repository.active_count(guest) >= self.policy.max_active:
                raise InventoryError("ORDER_LIMIT", "Достигнут лимит активных заказов")
            slot = uow.repository.slot(slot_id, lock=True)
            if not slot:
                raise InventoryError("NOT_FOUND", "Слот не найден")
            period = uow.catalog.period(slot.period_id, lock=True)
            lines: list[OrderLine] = []
            for choice in sorted(choices, key=lambda c: c.entry_id):
                entry = uow.catalog.entry(choice.entry_id, lock=True)
                if not entry or entry.period_id != slot.period_id or not entry.published:
                    raise InventoryError(
                        "MENU_UNAVAILABLE", "Позиция больше недоступна в выбранном периоде"
                    )
                if entry.price_minor != choice.expected_price_minor:
                    raise InventoryError(
                        "PRICE_CHANGED", "Цена изменилась. Обновите меню и проверьте корзину"
                    )
                item = uow.stock.item(entry.item_id)
                if not item or item.kind not in ("prepared", "purchased"):
                    raise InventoryError("MENU_UNAVAILABLE", "Выберите готовую продукцию")
                lines.append(
                    OrderLine(
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
            batches = [uow.stock.batch(id, lock=True) for id in sorted(ids)]
            now = self.clock()
            if (
                not period
                or not period.published
                or not now < period.ends_at
                or period.starts_at > now + timedelta(days=1)
                or not slot.enabled
                or now + timedelta(seconds=self.policy.reservation_seconds) > slot.cutoff_at
                or slot.occupied >= slot.capacity
            ):
                raise InventoryError(
                    "SLOT_UNAVAILABLE", "Приём в этот слот закрыт или мест больше нет"
                )
            allocations: list[tuple[UUID, int]] = []
            for line in lines:
                remaining = line.quantity
                eligible = sorted(
                    (
                        b
                        for b in batches
                        if b
                        and b.item_id == line.item_id
                        and b.status == "active"
                        and b.received_at <= now
                        and b.expires_at > slot.ends_at
                    ),
                    key=lambda b: (b.expires_at, b.id),
                )
                for batch in eligible:
                    take = min(remaining, int(batch.available_at(now)))
                    if take:
                        allocations.append((batch.id, take))
                        remaining -= take
                    if remaining == 0:
                        break
                if remaining:
                    raise InventoryError(
                        "INSUFFICIENT_STOCK",
                        f"Недостаточно пригодного остатка к выдаче: {line.name}",
                    )
            order = Order(
                uuid4(),
                guest,
                slot.id,
                "pending_payment",
                sum(line.price_minor * line.quantity for line in lines),
                now + timedelta(seconds=self.policy.reservation_seconds),
                now,
                now,
                1,
                tuple(lines),
                slot.starts_at,
                slot.ends_at,
            )
            uow.repository.add_order(order)
            for batch_id, amount in allocations:
                uow.reservations.reserve(order.id, batch_id, amount, guest, now)
            uow.repository.occupy(slot, 1)
            uow.repository.event(order, guest, "created", now)
            uow.repository.remember(guest, "checkout", key, payload, order.id, now)
            uow.commit()
            return order

    def checkouts(self, token: str, offset: int = 0, limit: int = 20) -> list[Order]:
        self.expire()
        with self.uow() as uow:
            return self._issues(
                uow, uow.repository.checkouts(self._guest(uow, token), offset, limit)
            )

    def mock_payment(self, token: str, id: UUID, key: UUID, outcome: str) -> Order:
        if outcome not in ("success", "failed", "timeout"):
            raise invalid("outcome", "Выберите результат тестовой оплаты")
        self.expire()
        with self.uow() as uow:
            guest = self._guest(uow, token)
            payload = fingerprint([id, outcome])
            replay = uow.repository.replay(guest, "mock_payment", key, payload)
            order = uow.repository.order(id, lock=True)
            if not order or order.guest_id != guest:
                raise InventoryError("NOT_FOUND", "Оформление не найдено")
            if replay:
                return order
            if order.status != "pending_payment":
                raise InventoryError("CHECKOUT_CLOSED", "Оформление уже завершено. Обновите список")
            slot = uow.repository.slot(order.slot_id, lock=True)
            assert slot is not None
            allocations = sorted(uow.reservations.allocations(id))
            batches = [uow.stock.batch(batch_id, lock=True) for batch_id, _ in allocations]
            now = self.clock()
            if order.expires_at <= now:
                updated = self._release(uow, order, "expired", None, now)
                uow.commit()
                return updated
            if any(
                not batch or batch.status != "active" or batch.expires_at <= slot.ends_at
                for batch in batches
            ):
                raise InventoryError(
                    "STOCK_UNAVAILABLE",
                    "Пригодность товара изменилась. Отмените оформление и обратитесь к сотруднику",
                )
            updated = (
                replace(
                    order,
                    status="confirmed",
                    updated_at=now,
                    version=order.version + 1,
                    pickup_code=secrets.token_hex(4).upper(),
                )
                if outcome == "success"
                else order
            )
            uow.repository.payment(updated, outcome, now)
            if outcome == "success":
                uow.repository.save_order(updated)
                uow.repository.event(updated, guest, "confirmed", now)
            uow.repository.remember(guest, "mock_payment", key, payload, id, now)
            uow.commit()
            return updated

    def transition(
        self,
        token: str,
        id: UUID,
        key: UUID,
        target: str,
        expected_version: int,
        pickup_code: str = "",
    ) -> Order:
        required = {"preparing": "confirmed", "ready": "preparing", "completed": "ready"}
        if target not in required:
            raise invalid("target", "Выберите допустимое действие")
        payload = fingerprint([id, target, expected_version, pickup_code])
        with self.uow() as uow:
            actor = uow.authorize(
                token, "orders.fulfil" if target == "completed" else "kitchen.manage"
            )
            if (
                target == "completed"
                and self.allow_request
                and not self.allow_request(f"fulfil:{actor}", 30, 60)
            ):
                raise IdentityError(
                    "RATE_LIMITED", "Слишком много попыток выдачи. Попробуйте позже"
                )
            replay = uow.repository.replay(actor, "kitchen", key, payload)
            order = uow.repository.order(id, lock=True)
            if not order or order.status == "pending_payment":
                raise InventoryError("NOT_FOUND", "Оплаченный заказ не найден")
            if replay:
                return order
            if order.status != required[target]:
                raise InventoryError(
                    "ORDER_STATE",
                    "Действие недоступно: заказ уже изменился или выдан. Обновите список",
                )
            if order.version != expected_version:
                raise InventoryError("STALE_ORDER", "Заказ изменился. Обновите список")
            if target == "completed" and (
                not order.pickup_code
                or not pickup_code.isascii()
                or not secrets.compare_digest(order.pickup_code, pickup_code)
            ):
                raise invalid("pickup_code", "Код получения не совпадает")
            allocations = sorted(uow.reservations.allocations(id))
            batches = [uow.stock.batch(batch_id, lock=True) for batch_id, _ in allocations]
            now = self.clock()
            if not allocations or sum(q for _, q in allocations) != sum(
                line.quantity for line in order.lines
            ):
                raise InventoryError(
                    "STOCK_UNAVAILABLE", "Резерв неполный. Обратитесь к управляющему"
                )
            for batch, (_, quantity) in zip(batches, allocations, strict=True):
                if (
                    not batch
                    or batch.status != "active"
                    or batch.expires_at <= now
                    or batch.received_at > now
                    or batch.reserved < quantity
                    or batch.on_hand < quantity
                ):
                    raise InventoryError(
                        "STOCK_UNAVAILABLE",
                        "Партия приостановлена или непригодна. Выдача запрещена",
                    )
            if target == "completed":
                for batch, (batch_id, quantity) in zip(batches, allocations, strict=True):
                    assert batch is not None
                    uow.reservations.consume(id, batch_id, quantity, actor, now)
                    uow.stock.add_movement(
                        Movement(
                            uuid4(),
                            batch_id,
                            "mock_fulfil",
                            -Decimal(quantity),
                            batch.on_hand,
                            batch.on_hand - quantity,
                            f"Тестовая выдача заказа {id}",
                            actor,
                            now,
                            batch.version + 1,
                            batch.status,
                            batch.status,
                        )
                    )
                    uow.stock.audit(actor, "mock_fulfil", batch_id, now)
            updated = replace(order, status=target, version=order.version + 1, updated_at=now)
            uow.repository.save_order(updated)
            uow.repository.event(updated, actor, target, now)
            uow.repository.remember(actor, "kitchen", key, payload, id, now)
            uow.commit()
            return updated

    def own_orders(self, token: str, offset: int = 0, limit: int = 20) -> list[Order]:
        self.expire()
        with self.uow() as uow:
            return self._issues(uow, uow.repository.orders(self._guest(uow, token), offset, limit))

    def staff_orders(self, token: str, offset: int = 0, limit: int = 20) -> list[Order]:
        self.expire()
        with self.uow() as uow:
            uow.authorize(token, "kitchen.read")
            return self._issues(uow, uow.repository.orders(None, offset, limit))

    def _issues(self, uow: OrderUnitOfWork, orders: list[Order]) -> list[Order]:
        affected = uow.reservations.troubled([order.id for order in orders], self.clock())
        return [replace(order, stock_issue=order.id in affected) for order in orders]

    def cancel(self, token: str, id: UUID) -> Order:
        with self.uow() as uow:
            guest = self._guest(uow, token)
            order = uow.repository.order(id, lock=True)
            if not order or order.guest_id != guest:
                raise InventoryError("NOT_FOUND", "Заказ не найден")
            if order.status in ("cancelled", "expired"):
                return order
            if order.status not in ("pending_payment", "confirmed"):
                raise InventoryError(
                    "ORDER_STATE", "Заказ уже передан в работу. Обратитесь к сотруднику"
                )
            now = self.clock()
            updated = self._release(
                uow,
                order,
                "expired"
                if order.status == "pending_payment" and order.expires_at <= now
                else "cancelled",
                guest,
                now,
            )
            if order.status == "confirmed":
                uow.repository.payment(updated, "refunded", now)
                uow.repository.event(updated, guest, "paid_cancelled", now)
            uow.commit()
            return updated

    def _release(
        self, uow: OrderUnitOfWork, order: Order, status: str, actor: UUID | None, now: datetime
    ) -> Order:
        slot = uow.repository.slot(order.slot_id, lock=True)
        assert slot is not None
        allocations = sorted(uow.reservations.allocations(order.id))
        for batch_id, _amount in allocations:
            uow.stock.batch(batch_id, lock=True)
        for batch_id, amount in allocations:
            uow.reservations.release(order.id, batch_id, amount, actor, now)
        uow.repository.occupy(slot, -1)
        updated = replace(order, status=status, updated_at=now, version=order.version + 1)
        uow.repository.save_order(updated)
        uow.repository.event(updated, actor, status, now)
        return updated

    def expire(self) -> None:
        with self.uow() as uow:
            ids = uow.repository.due(self.clock(), 100)
        for id in ids:
            with self.uow() as uow:
                order = uow.repository.order(id, lock=True)
                now = self.clock()
                if order and order.status == "pending_payment" and order.expires_at <= now:
                    self._release(uow, order, "expired", None, now)
                    uow.commit()
