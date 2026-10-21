from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.identity.presentation.http import enforce_csrf, session_token
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.domain.models import Batch, batch_state

router = APIRouter(
    prefix="/api/v1/inventory",
    tags=["Склад"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422)},
)


def service_for(request: Request) -> InventoryService:
    return cast(InventoryService, request.app.state.inventory)


Service = Annotated[InventoryService, Depends(service_for)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=100)]


class ItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["raw", "purchased", "prepared"]
    unit: Literal["kg", "l", "pcs", "portion"]
    barcode: str | None = Field(default=None, max_length=14)
    category: str = Field(default="", max_length=100)
    purchase_price_minor: int = Field(default=0, ge=0, le=999999999999)
    sale_price_minor: int = Field(default=0, ge=0, le=999999999999)


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: UUID
    label: str = Field(min_length=1, max_length=100, strict=True)
    quantity: str = Field(min_length=1, max_length=24, strict=True)
    unit: Literal["kg", "g", "l", "ml", "pcs", "portion"]
    total_cost_minor: int = Field(ge=0, le=999999999999, strict=True)
    received_at: datetime
    expires_at: datetime
    source: str = Field(min_length=1, max_length=200, strict=True)


class ChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["write_off", "count", "suspend", "resume"]
    quantity: str | None = Field(default=None, max_length=24, strict=True)
    unit: Literal["kg", "g", "l", "ml", "pcs", "portion"] | None = None
    reason: str = Field(min_length=1, max_length=200, strict=True)
    expected_version: int = Field(ge=1, strict=True)


class ItemResponse(BaseModel):
    version: int = 1
    id: UUID
    name: str
    kind: Literal["raw", "purchased", "prepared"]
    unit: Literal["kg", "l", "pcs", "portion"]
    barcode: str | None = Field(default=None, max_length=14)
    category: str = Field(default="", max_length=100)
    purchase_price_minor: int = Field(default=0, ge=0, le=999999999999)
    sale_price_minor: int = Field(default=0, ge=0, le=999999999999)


class ItemUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    barcode: str | None = Field(default=None, max_length=14)
    category: str = Field(default="", max_length=100)
    purchase_price_minor: int = Field(ge=0, le=999999999999)
    sale_price_minor: int = Field(ge=0, le=999999999999)
    expected_version: int = Field(ge=1)


class OperationResponse(BaseModel):
    subject_id: UUID
    version: int


class BatchResponse(BaseModel):
    warehouse_id: UUID
    item_kind: Literal["raw", "purchased", "prepared"]
    id: UUID
    item_id: UUID
    item_name: str
    unit: str
    label: str
    on_hand: str
    reserved: str
    free: str
    available: str
    status: str
    version: int
    total_cost_minor: int
    received_at: datetime
    expires_at: datetime
    source: str
    actor_id: UUID
    created_at: datetime

    @classmethod
    def from_batch(cls, batch: Batch) -> "BatchResponse":
        values = asdict(batch)
        now = datetime.now(UTC)
        state = batch_state(batch, now)
        values.update(
            on_hand=str(batch.on_hand),
            reserved=str(batch.reserved),
            free=str(batch.free),
            available=str(batch.available_at(now)),
            status=state,
        )
        return cls(**values)


class MovementResponse(BaseModel):
    actor_name: str = ""
    id: UUID
    batch_id: UUID
    action: str
    delta: str
    before: str
    after: str
    reason: str
    actor_id: UUID
    created_at: datetime
    version: int
    status_before: str
    status_after: str


@router.get("/items", operation_id="listStockItems")
def list_items(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 50
) -> list[ItemResponse]:
    return [
        ItemResponse(**asdict(item))
        for item in service.items(session_token(request), offset, limit)
    ]


@router.post(
    "/items", operation_id="createStockItem", status_code=201, dependencies=[Depends(enforce_csrf)]
)
def create_item(data: ItemInput, request: Request, service: Service, key: Key) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.create_item(
                session_token(request),
                key,
                data.name,
                data.kind,
                data.unit,
                data.barcode,
                data.category,
                data.purchase_price_minor,
                data.sale_price_minor,
            )
        )
    )


@router.get("/batches", operation_id="listStockBatches")
def list_batches(
    request: Request,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 50,
    warehouse_id: UUID | None = None,
    query: str = Query(default="", max_length=100),
) -> list[BatchResponse]:
    return [
        BatchResponse.from_batch(batch)
        for batch in service.batches(session_token(request), offset, limit, warehouse_id, query)
    ]


@router.post(
    "/receipts", operation_id="receiveStock", status_code=201, dependencies=[Depends(enforce_csrf)]
)
def receive(data: ReceiptInput, request: Request, service: Service, key: Key) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.receive(
                session_token(request),
                key,
                data.item_id,
                data.label,
                data.quantity,
                data.unit,
                data.total_cost_minor,
                data.received_at,
                data.expires_at,
                data.source,
            )
        )
    )


@router.post(
    "/batches/{batch_id}/changes",
    operation_id="changeStockBatch",
    dependencies=[Depends(enforce_csrf)],
)
def change(
    batch_id: UUID, data: ChangeInput, request: Request, service: Service, key: Key
) -> OperationResponse:
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


@router.get("/batches/{batch_id}/movements", operation_id="listStockMovements")
def list_movements(
    batch_id: UUID, request: Request, service: Service, offset: Offset = 0, limit: Limit = 50
) -> list[MovementResponse]:
    result = []
    for movement in service.movements(session_token(request), batch_id, offset, limit):
        values = asdict(movement)
        for field in ("delta", "before", "after"):
            values[field] = str(values[field])
        result.append(MovementResponse(**values))
    return result


class DirectoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["supplier", "warehouse", "payment_method"]
    name: str = Field(min_length=1, max_length=100, strict=True)


class DirectoryResponse(DirectoryInput):
    id: UUID


class InvoiceLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: UUID
    quantity: str = Field(min_length=1, max_length=24, strict=True)
    unit: Literal["kg", "g", "l", "ml", "pcs"]
    unit_cost_minor: int = Field(ge=0, le=999999999999, strict=True)
    expires_at: datetime


class InvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: str = Field(min_length=1, max_length=100, strict=True)
    supplier_id: UUID
    warehouse_id: UUID
    payment_method_id: UUID
    received_at: datetime
    expenses_minor: int = Field(ge=0, le=999999999999, strict=True)
    note: str = Field(default="", max_length=200, strict=True)
    lines: list[InvoiceLineInput] = Field(min_length=1, max_length=100)


class InvoiceResponse(BaseModel):
    id: UUID
    number: str
    supplier_id: UUID
    warehouse_id: UUID
    payment_method_id: UUID
    received_at: datetime
    goods_minor: int
    expenses_minor: int
    total_minor: int
    note: str
    actor_id: UUID
    created_at: datetime
    lines: list[dict[str, object]]
    supplier_name: str
    warehouse_name: str
    payment_method_name: str


@router.get("/directories", operation_id="listStockDirectories")
def directories(
    request: Request, service: Service, kind: Literal["supplier", "warehouse", "payment_method"]
) -> list[DirectoryResponse]:
    return [
        DirectoryResponse(**asdict(d)) for d in service.directories(session_token(request), kind)
    ]


@router.post(
    "/directories",
    operation_id="createStockDirectory",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def create_directory(
    request: Request, data: DirectoryInput, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(service.create_directory(session_token(request), key, data.kind, data.name))
    )


@router.get("/invoices", operation_id="listStockInvoices")
def invoices(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[InvoiceResponse]:
    return [
        InvoiceResponse(**asdict(i))
        for i in service.invoices(session_token(request), offset, limit)
    ]


@router.post(
    "/invoices",
    operation_id="receiveInvoice",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def receive_invoice(
    request: Request, data: InvoiceInput, service: Service, key: Key
) -> OperationResponse:
    from ashana.modules.inventory.domain.models import InvoiceLine

    return OperationResponse(
        **asdict(
            service.receive_invoice(
                session_token(request),
                key,
                data.number,
                data.supplier_id,
                data.warehouse_id,
                data.payment_method_id,
                data.received_at,
                data.expenses_minor,
                data.note,
                [InvoiceLine(**line.model_dump()) for line in data.lines],
            )
        )
    )


class BarcodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    barcode: str | None = Field(max_length=14)
    expected_barcode: str | None = Field(max_length=14)


@router.put(
    "/items/{item_id}/barcode", operation_id="setItemBarcode", dependencies=[Depends(enforce_csrf)]
)
def set_barcode(
    item_id: UUID, data: BarcodeInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.set_barcode(
                session_token(request), key, item_id, data.barcode, data.expected_barcode
            )
        )
    )


@router.put(
    "/items/{item_id}", operation_id="updateStockItem", dependencies=[Depends(enforce_csrf)]
)
def update_item(
    item_id: UUID, data: ItemUpdateInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(service.edit_item(session_token(request), key, item_id, **data.model_dump()))
    )
