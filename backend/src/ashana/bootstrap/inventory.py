from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.infrastructure.database import PostgresInventoryUnitOfWork


def inventory_service(
    engine: Engine, identity: IdentityService, *, cashier: bool = False
) -> InventoryService:
    def authorize(connection: Connection, token: str) -> UUID:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        if not cashier or "inventory.manage" not in principal.user.effective_permissions:
            principal.require("inventory.writeoff" if cashier else "inventory.manage")
        return principal.user.id

    return InventoryService(lambda: PostgresInventoryUnitOfWork(engine, authorize), cashier=cashier)
