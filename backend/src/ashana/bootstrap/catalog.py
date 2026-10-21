from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.modules.catalog.application.service import CatalogService
from ashana.modules.catalog.infrastructure.database import PostgresCatalogUnitOfWork
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.infrastructure.database import PostgresInventoryRepository


def catalog_service(engine: Engine, identity: IdentityService) -> CatalogService:
    def authorize(connection: Connection, token: str) -> UUID:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        principal.require("catalog.manage")
        return principal.user.id

    return CatalogService(
        lambda: PostgresCatalogUnitOfWork(engine, authorize, PostgresInventoryRepository)
    )
