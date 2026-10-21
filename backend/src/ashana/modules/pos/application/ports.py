from types import TracebackType
from typing import Protocol
from uuid import UUID

from ashana.modules.catalog.application.ports import CatalogRepository
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.application.reservations import ReservationRepository
from ashana.modules.pos.domain.models import Sale


class SaleRepository(Protocol):
    def get(self, id: UUID) -> Sale | None: ...
    def list(self, offset: int, limit: int) -> list[Sale]: ...
    def add(self, sale: Sale) -> None: ...


class PosUnitOfWork(Protocol):
    repository: SaleRepository
    catalog: CatalogRepository
    stock: InventoryRepository
    reservations: ReservationRepository

    def __enter__(self) -> "PosUnitOfWork": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def authorize(self, token: str) -> UUID: ...
    def commit(self) -> None: ...
