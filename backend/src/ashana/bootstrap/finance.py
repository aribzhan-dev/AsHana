from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from ashana.modules.finance.application.service import FinanceService
from ashana.modules.finance.infrastructure.database import PostgresFinanceUnitOfWork
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.inventory.infrastructure.database import PostgresInventoryRepository


def finance_service(engine: Engine, identity: IdentityService) -> FinanceService:
    def authorize(
        connection: Connection, token: str, permission: str | None
    ) -> tuple[UUID, frozenset[str]]:
        principal = identity.principal(PostgresIdentityRepository(connection), token)
        # permission=None: any signed-in staff member (own shift check-in/out).
        if permission:
            principal.require(permission)
        return principal.user.id, principal.user.effective_permissions

    return FinanceService(
        lambda: PostgresFinanceUnitOfWork(engine, authorize, PostgresInventoryRepository)
    )
