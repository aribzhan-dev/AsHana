from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.identity.presentation.http import session_token
from ashana.modules.reporting.application.service import ReportingService
from ashana.modules.reporting.domain.models import ReportFilter, ReportKind

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Отчёты"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 422)},
)


def service_for(request: Request) -> ReportingService:
    return cast(ReportingService, request.app.state.reporting)


Service = Annotated[ReportingService, Depends(service_for)]
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=100)]


class ReportColumn(BaseModel):
    key: str
    label: str
    format: Literal["text", "quantity", "money"]


class ReportResponse(BaseModel):
    kind: ReportKind
    generated_at: datetime
    columns: list[ReportColumn]
    rows: list[dict[str, str]]
    totals: dict[str, str]
    unit_totals: dict[str, dict[str, str]]
    total_rows: int
    offset: int
    limit: int
    note: str


class ReportOption(BaseModel):
    id: UUID
    name: str


@router.get("/options/{target}", operation_id="getReportOptions")
def options(
    target: Literal["items", "periods"],
    request: Request,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[ReportOption]:
    return [
        ReportOption(id=UUID(r["id"]), name=r["name"])
        for r in service.options(session_token(request), target, offset, limit)
    ]


class DashboardResponse(BaseModel):
    generated_at: datetime
    totals: dict[str, str]
    top: list[dict[str, str]]
    low: list[dict[str, str]]
    hours: list[dict[str, str]]


@router.get("/dashboard", operation_id="getDashboard")
def dashboard(start: date, end: date, request: Request, service: Service) -> DashboardResponse:
    return DashboardResponse(
        **asdict(service.dashboard(session_token(request), ReportFilter(start, end)))
    )


@router.get("/{kind}", operation_id="getReport")
def report(
    kind: ReportKind,
    start: date,
    end: date,
    request: Request,
    service: Service,
    item_id: UUID | None = None,
    period_id: UUID | None = None,
    channel: Literal["all", "online", "cashier"] = "all",
    mode: Literal["mock", "real"] = "mock",
    offset: Offset = 0,
    limit: Limit = 20,
) -> ReportResponse:
    return ReportResponse(
        **asdict(
            service.read(
                session_token(request),
                kind,
                ReportFilter(start, end, item_id, period_id, channel, mode),
                offset,
                limit,
            )
        )
    )
