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
from ashana.modules.inventory.domain.models import Item
from ashana.shared.domain import BusinessError, Result, invalid, text_value


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
                raise BusinessError("NOT_FOUND", "Период питания не найден")
            return uow.repository.entries(period_id, offset, limit)

    def items(self, token: str, kind: str, offset: int = 0, limit: int = 100) -> list[Item]:
        with self.uow() as uow:
            uow.authorize(token)
            if kind not in ("prepared", "purchased"):
                raise invalid("kind", "В меню доступна только готовая продукция")
            return uow.stock.items(offset, limit, kind=kind)

    def image(self, entry_id: UUID) -> tuple[bytes, str] | None:
        """Public photo of a published menu entry; no session needed."""
        with self.uow() as uow:
            entry = uow.repository.entry(entry_id)
            if not entry or not entry.published:
                return None
            return uow.stock.image(entry.item_id)

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
                raise BusinessError("NOT_FOUND", "Период питания не найден")
            if expected_version != (current.version if current else 0):
                raise BusinessError(
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
            if current is None:
                self._add_permanent(uow, actor, now, [period])
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

    def _add_permanent(
        self, uow: CatalogUnitOfWork, actor: UUID, now: datetime, targets: list[Period]
    ) -> int:
        """Put every always-on-menu good into the given periods; stock decides visibility."""
        goods: list[Item] = []
        offset = 0
        while page := uow.stock.items(offset, 100, kind="purchased"):
            goods += [i for i in page if i.always_on_menu and i.sale_price_minor > 0]
            offset += 100
        added = 0
        for period in targets:
            present = uow.repository.period_items(period.id)
            for item in goods:
                if item.id in present:
                    continue
                entry = Entry(
                    uuid4(),
                    period.id,
                    item.id,
                    "",
                    "1 шт.",
                    item.sale_price_minor,
                    True,
                    1,
                    actor,
                    now,
                    now,
                    item.name,
                    item.unit,
                    item.category[:60],
                )
                uow.repository.save_entry(entry, new=True)
                uow.repository.audit(actor, "entry", entry.id, None, asdict(entry), now)
                added += 1
        return added

    def sync_permanent(self, token: str, key: UUID) -> Result:
        """Add always-on-menu goods to current and future periods that still lack them."""

        def action(uow: CatalogUnitOfWork, actor: UUID, now: datetime) -> Result:
            targets = uow.repository.open_periods(now)
            for period in targets:
                uow.repository.period(period.id, lock=True)
            self._add_permanent(uow, actor, now, targets)
            return Result(actor, 1)

        return self._write(token, "catalog_permanent_sync", key, {}, action)

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
                raise BusinessError("NOT_FOUND", "Период питания не найден")
            current = uow.repository.entry(entry_id, lock=True) if entry_id else None
            if entry_id and (not current or current.period_id != period_id):
                raise BusinessError("NOT_FOUND", "Позиция меню не найдена")
            if expected_version != (current.version if current else 0):
                raise BusinessError(
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
