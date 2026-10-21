from sqlalchemy.engine import Connection, Engine

from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository
from ashana.modules.reporting.application.service import ReportingService
from ashana.modules.reporting.infrastructure.database import PostgresReportUnitOfWork


def reporting_service(engine: Engine, identity: IdentityService) -> ReportingService:
    def authorize(connection: Connection, token: str) -> None:
        identity.principal(PostgresIdentityRepository(connection), token).require("reporting.read")

    return ReportingService(lambda: PostgresReportUnitOfWork(engine, authorize))
