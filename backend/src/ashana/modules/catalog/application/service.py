import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from ashana.modules.catalog.application.ports import CatalogUnitOfWork
from ashana.modules.catalog.domain.models import (
    Entry,
    MenuEntry,
    Period,
    price_minor,
    validate_period,
)
from ashana.modules.inventory.domain.models import InventoryError, Item, Result, invalid, text_value


class CatalogService:
    def __init__(
        self,
        uow: Callable[[], CatalogUnitOfWork],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.uow, self.clock = uow, clock

    def periods(self, token: str, day: date, offset: int = 0, limit: int = 20) -> list[Period]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.periods(day, offset, limit)

    def entries(self, token: str, period_id: UUID, offset: int = 0, limit: int = 20) -> list[Entry]:
        with self.uow() as uow:
            uow.authorize(token)
            if not uow.repository.period(period_id):
                raise InventoryError("NOT_FOUND", "Период питания не найден")
            return uow.repository.entries(period_id, offset, limit)

    def items(self, token: str, kind: str, offset: int = 0, limit: int = 100) -> list[Item]:
        with self.uow() as uow:
            uow.authorize(token)
            if kind not in ("prepared", "purchased"):
                raise invalid("kind", "В меню доступна только готовая продукция")
            return uow.stock.items(offset, limit, kind=kind)

    def menu(
        self, offset: int = 0, limit: int = 20, upcoming: bool = False
    ) -> tuple[datetime, list[MenuEntry]]:
        with self.uow() as uow:
            now = self.clock()
            return now, uow.repository.menu(now, offset, limit, upcoming)

    def _write(
        self,
        token: str,
        operation: str,
        key: UUID,
        payload: dict[str, object],
        action: Callable[[CatalogUnitOfWork, UUID, datetime], Result],
    ) -> Result:
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        with self.uow() as uow:
            actor = uow.authorize(token)
            replay = uow.stock.replay(actor, operation, key, fingerprint)
            if replay:
                return replay
            now = self.clock()
            result = action(uow, actor, now)
            uow.stock.remember(actor, operation, key, fingerprint, result, now)
            uow.commit()
            return result

    def save_period(
        self,
        token: str,
        key: UUID,
        period_id: UUID | None,
        expected_version: int,
        name: str,
        starts_at: datetime,
        ends_at: datetime,
        published: bool,
    ) -> Result:
        def action(uow: CatalogUnitOfWork, actor: UUID, now: datetime) -> Result:
            current = uow.repository.period(period_id, lock=True) if period_id else None
            if period_id and not current:
                raise InventoryError("NOT_FOUND", "Период питания не найден")
            if expected_version != (current.version if current else 0):
                raise InventoryError(
                    "STALE_CATALOG", "Меню изменилось. Обновите данные и откройте форму заново"
                )
            validate_period(starts_at, ends_at)
            period = Period(
                period_id or uuid4(),
                text_value(name, "name", 100),
                starts_at,
                ends_at,
                published,
                expected_version + 1,
                actor,
                current.created_at if current else now,
                now,
            )
            uow.repository.save_period(period, new=current is None)
            uow.repository.audit(
                actor,
                "period",
                period.id,
                asdict(current) if current else None,
                asdict(period),
                now,
            )
            return Result(period.id, period.version)

        return self._write(
            token,
            "catalog_period_saved",
            key,
            {
                "period_id": period_id,
                "expected_version": expected_version,
                "name": name,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "published": published,
            },
            action,
        )

    def save_entry(
        self,
        token: str,
        key: UUID,
        period_id: UUID,
        entry_id: UUID | None,
        expected_version: int,
        item_id: UUID,
        description: str,
        portion_label: str,
        price: int,
        published: bool,
        category: str = "",
    ) -> Result:
        def action(uow: CatalogUnitOfWork, actor: UUID, now: datetime) -> Result:
            if not uow.repository.period(period_id, lock=True):
                raise InventoryError("NOT_FOUND", "Период питания не найден")
            current = uow.repository.entry(entry_id, lock=True) if entry_id else None
            if entry_id and (not current or current.period_id != period_id):
                raise InventoryError("NOT_FOUND", "Позиция меню не найдена")
            if expected_version != (current.version if current else 0):
                raise InventoryError(
                    "STALE_CATALOG", "Меню изменилось. Обновите данные и откройте форму заново"
                )
            if current and item_id != current.item_id:
                raise invalid("item_id", "Для другого товара создайте отдельную позицию меню")
            item = uow.stock.item(item_id)
            if not item or item.kind not in ("prepared", "purchased"):
                raise invalid("item_id", "Сырьё нельзя публиковать: выберите готовую продукцию")
            entry = Entry(
                entry_id or uuid4(),
                period_id,
                item_id,
                text_value(description, "description", 1000) if description.strip() else "",
                text_value(portion_label, "portion_label", 100),
                price_minor(price),
                published,
                expected_version + 1,
                actor,
                current.created_at if current else now,
                now,
                item.name,
                item.unit,
                text_value(category, "category", 60) if category.strip() else "",
            )
            uow.repository.save_entry(entry, new=current is None)
            uow.repository.audit(
                actor, "entry", entry.id, asdict(current) if current else None, asdict(entry), now
            )
            return Result(entry.id, entry.version)

        return self._write(
            token,
            "catalog_entry_saved",
            key,
            {
                "period_id": period_id,
                "entry_id": entry_id,
                "expected_version": expected_version,
                "item_id": item_id,
                "description": description,
                "category": category,
                "portion_label": portion_label,
                "price_minor": price,
                "published": published,
            },
            action,
        )
