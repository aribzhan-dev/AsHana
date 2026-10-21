from collections.abc import Callable

from ashana.modules.reporting.application.ports import ReportUnitOfWork
from ashana.modules.reporting.domain.models import Dashboard, Report, ReportFilter, ReportKind


class ReportingService:
    def __init__(self, uow: Callable[[], ReportUnitOfWork]) -> None:
        self.uow = uow

    def read(
        self, token: str, kind: ReportKind, filters: ReportFilter, offset: int = 0, limit: int = 20
    ) -> Report:
        filters.bounds()
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.read(kind, filters, offset, limit)

    def options(
        self, token: str, target: str, offset: int = 0, limit: int = 100
    ) -> list[dict[str, str]]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.options(target, offset, limit)

    def dashboard(self, token: str, filters: ReportFilter) -> Dashboard:
        filters.bounds()
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.dashboard(filters)
