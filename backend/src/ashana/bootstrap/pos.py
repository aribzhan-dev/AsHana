from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.modules.catalog.infrastructure.database import PostgresCatalogRepository
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.infrastructure.database import PostgresInventoryRepository
from ashana.modules.inventory.infrastructure.reservations import PostgresReservations
from ashana.modules.orders.application.service import OrderService
from ashana.modules.pos.application.service import PosService
from ashana.modules.pos.infrastructure.database import PostgresPosUnitOfWork


def pos_service(
    engine: Engine, identity: IdentityService, orders: OrderService, *, enabled: bool = True
) -> PosService:
    def authorize(connection: Connection, token: str) -> UUID:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        principal.require("pos.sell")
        return principal.user.id

    return PosService(
        lambda: PostgresPosUnitOfWork(
            engine,
            authorize,
            PostgresCatalogRepository,
            PostgresInventoryRepository,
            PostgresReservations,
        ),
        expire=orders.expire,
        enabled=enabled,
    )
