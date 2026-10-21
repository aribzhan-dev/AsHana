from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.infrastructure.database import PostgresInventoryRepository
from ashana.modules.production.application.service import ProductionService
from ashana.modules.production.infrastructure.database import PostgresProductionUnitOfWork


def production_service(engine: Engine, identity: IdentityService) -> ProductionService:
    def authorize(connection: Connection, token: str) -> UUID:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        principal.require("production.manage")
        return principal.user.id

    return ProductionService(
        lambda: PostgresProductionUnitOfWork(engine, authorize, PostgresInventoryRepository)
    )
