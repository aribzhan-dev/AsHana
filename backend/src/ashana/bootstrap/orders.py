import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.bootstrap.settings import Settings
from ashana.modules.catalog.infrastructure.database import PostgresCatalogRepository
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.infrastructure.database import PostgresInventoryRepository
from ashana.modules.inventory.infrastructure.reservations import PostgresReservations
from ashana.modules.notifications.infrastructure.delivery import PostgresNotificationWriter
from ashana.modules.orders.application.service import OrderService
from ashana.modules.orders.domain.models import OrderPolicy
from ashana.modules.orders.infrastructure.database import PostgresOrderUnitOfWork


def order_service(engine: Engine, identity: IdentityService, settings: Settings) -> OrderService:
    def authorize(connection: Connection, token: str, permission: str) -> UUID:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        principal.require(permission)
        return principal.user.id

    def allow_request(key: str, limit: int, seconds: int) -> bool:
        with engine.begin() as connection:
            return PostgresIdentityRepository(connection).consume_rate(
                hashlib.sha256(("orders:" + key).encode()).hexdigest(),
                datetime.now(UTC),
                limit,
                seconds,
            )

    return OrderService(
        lambda: PostgresOrderUnitOfWork(
            engine,
            authorize,
            PostgresCatalogRepository,
            PostgresInventoryRepository,
            PostgresReservations,
            PostgresNotificationWriter,
        ),
        OrderPolicy(
            settings.order_max_active,
            settings.order_max_portions,
            settings.order_reservation_seconds,
            settings.order_cutoff_minutes,
            settings.order_slot_minutes,
            settings.order_slot_capacity,
        ),
        allow_request=allow_request,
    )
