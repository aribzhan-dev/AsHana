from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.catalog.presentation.http import PublicMenuEntry
from ashana.modules.identity.presentation.http import enforce_csrf, session_token
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.presentation.http import (
    BatchResponse,
    ChangeInput,
    DirectoryResponse,
    OperationResponse,
)
from ashana.modules.orders.domain.models import Choice
from ashana.modules.orders.presentation.http import OrderChoice, OrderLineResponse
from ashana.modules.pos.application.service import PosService

router = APIRouter(
    prefix="/api/v1/pos",
    tags=["Касса"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 409, 422)},
)


def service_for(request: Request) -> PosService:
    return cast(PosService, request.app.state.pos)


Service = Annotated[PosService, Depends(service_for)]
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=100)]


class PosInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[OrderChoice] = Field(min_length=1, max_length=100)
    payment_method_id: UUID | None = None
    outcome: Literal["success", "failed", "timeout"]


class PosResponse(BaseModel):
    id: UUID
    actor_id: UUID
    payment_method_id: UUID | None = None
    outcome: Literal["success", "failed", "timeout"]
    payment_method_name: str = ""
    mode: Literal["mock"] = "mock"
    currency: Literal["KZT"] = "KZT"
    total_minor: int
    created_at: datetime
    lines: list[OrderLineResponse]


@router.get("/menu", operation_id="getPosMenu")
def menu(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[PublicMenuEntry]:
    return [
        PublicMenuEntry(**asdict(e)) for e in service.menu(session_token(request), offset, limit)
    ]


@router.get("/sales", operation_id="listPosSales")
def history(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[PosResponse]:
    return [
        PosResponse(**asdict(s)) for s in service.history(session_token(request), offset, limit)
    ]


@router.post(
    "/sales", operation_id="createPosSale", status_code=201, dependencies=[Depends(enforce_csrf)]
)
def sell(
    data: PosInput,
    request: Request,
    service: Service,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> PosResponse:
    return PosResponse(
        **asdict(
            service.sell(
                session_token(request),
                key,
                [Choice(**c.model_dump()) for c in data.lines],
                data.outcome,
                data.payment_method_id,
            )
        )
    )


@router.get("/payment-methods", operation_id="listPosPaymentMethods")
def payment_methods(request: Request, service: Service) -> list[DirectoryResponse]:
    return [DirectoryResponse(**asdict(d)) for d in service.payment_methods(session_token(request))]


@router.get("/stock", operation_id="listCashierStock")
def stock(request: Request, offset: Offset = 0, limit: Limit = 20) -> list[BatchResponse]:
    service = cast(InventoryService, request.app.state.cash_stock)
    return [
        BatchResponse.from_batch(b) for b in service.batches(session_token(request), offset, limit)
    ]


@router.post(
    "/stock/{batch_id}/write-off",
    operation_id="writeOffCashierStock",
    dependencies=[Depends(enforce_csrf)],
)
def write_off(
    batch_id: UUID,
    data: ChangeInput,
    request: Request,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> OperationResponse:
    service = cast(InventoryService, request.app.state.cash_stock)
    return OperationResponse(
        **asdict(
            service.change(
                session_token(request),
                key,
                batch_id,
                data.operation,
                data.quantity,
                data.unit,
                data.reason,
                data.expected_version,
            )
        )
    )
