from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.infrastructure.database import PostgresInventoryUnitOfWork


def inventory_service(engine: Engine, identity: IdentityService) -> InventoryService:
    def authorize(connection: Connection, token: str) -> UUID:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        principal.require("inventory.manage")
        return principal.user.id

    return InventoryService(lambda: PostgresInventoryUnitOfWork(engine, authorize))
