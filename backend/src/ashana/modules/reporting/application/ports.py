from types import TracebackType
from typing import Protocol

from ashana.modules.reporting.domain.models import Dashboard, Report, ReportFilter, ReportKind


class ReportRepository(Protocol):
    def dashboard(self, filters: ReportFilter) -> Dashboard: ...
    def read(self, kind: ReportKind, filters: ReportFilter, offset: int, limit: int) -> Report: ...
    def options(self, target: str, offset: int, limit: int) -> list[dict[str, str]]: ...


class ReportUnitOfWork(Protocol):
    repository: ReportRepository

    def __enter__(self) -> "ReportUnitOfWork": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def authorize(self, token: str) -> None: ...
