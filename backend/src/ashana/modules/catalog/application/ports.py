from datetime import date, datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from ashana.modules.catalog.domain.models import Entry, MenuEntry, Period
from ashana.modules.inventory.application.ports import InventoryRepository


class CatalogRepository(Protocol):
    def periods(self, day: date, offset: int, limit: int) -> list[Period]: ...
    def period(self, id: UUID, *, lock: bool = False) -> Period | None: ...
    def save_period(self, period: Period, *, new: bool) -> None: ...
    def entries(self, period_id: UUID, offset: int, limit: int) -> list[Entry]: ...
    def entry(self, id: UUID, *, lock: bool = False) -> Entry | None: ...
    def save_entry(self, entry: Entry, *, new: bool) -> None: ...
    def menu(
        self, now: datetime, offset: int, limit: int, upcoming: bool = False
    ) -> list[MenuEntry]: ...
    def audit(
        self,
        actor: UUID,
        entity: str,
        subject: UUID,
        before: dict[str, object] | None,
        after: dict[str, object],
        now: datetime,
    ) -> None: ...


class CatalogUnitOfWork(Protocol):
    repository: CatalogRepository
    stock: InventoryRepository

    def __enter__(self) -> "CatalogUnitOfWork": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def authorize(self, token: str) -> UUID: ...
    def commit(self) -> None: ...
