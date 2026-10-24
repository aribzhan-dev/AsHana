from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.identity.presentation.http import enforce_csrf, session_token
from ashana.modules.inventory.application.service import InventoryService
from ashana.modules.inventory.domain.models import Batch, InventoryError, batch_state
from ashana.modules.inventory.infrastructure.images import MAX_UPLOAD

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
    always_on_menu: bool = False


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
    image: str = ""
    id: UUID
    name: str
    kind: Literal["raw", "purchased", "prepared"]
    unit: Literal["kg", "l", "pcs", "portion"]
    barcode: str | None = Field(default=None, max_length=14)
    category: str = Field(default="", max_length=100)
    purchase_price_minor: int = Field(default=0, ge=0, le=999999999999)
    sale_price_minor: int = Field(default=0, ge=0, le=999999999999)
    always_on_menu: bool = False


class ItemUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    barcode: str | None = Field(default=None, max_length=14)
    category: str = Field(default="", max_length=100)
    purchase_price_minor: int = Field(ge=0, le=999999999999)
    sale_price_minor: int = Field(ge=0, le=999999999999)
    expected_version: int = Field(ge=1)
    always_on_menu: bool = False


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
                data.always_on_menu,
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


PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")

DirectoryKind = Literal["supplier", "warehouse", "payment_method", "category", "expense_category"]


class DirectoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: DirectoryKind
    name: str = Field(min_length=1, max_length=100, strict=True)


class DirectoryResponse(DirectoryInput):
    id: UUID
    commission_bp: int = 0
    system: bool = False


class DirectoryRenameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, strict=True)


class DirectoryDetailsResponse(DirectoryResponse):
    usage: dict[str, int]


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
    # Omitted means paid in full, as before supplier debts existed.
    paid_minor: int | None = Field(default=None, ge=0, le=999999999999, strict=True)


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
    paid_on_receipt_minor: int
    paid_minor: int
    debt_minor: int


class InvoicePaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: int = Field(ge=1, le=999999999999, strict=True)
    payment_method_id: UUID
    paid_at: datetime
    note: str = Field(default="", max_length=200, strict=True)


class InvoicePaymentResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    amount_minor: int
    payment_method_id: UUID
    note: str
    actor_id: UUID
    paid_at: datetime
    created_at: datetime


@router.get("/directories", operation_id="listStockDirectories")
def directories(request: Request, service: Service, kind: DirectoryKind) -> list[DirectoryResponse]:
    return [
        DirectoryResponse(**asdict(d), system=d.system)
        for d in service.directories(session_token(request), kind)
    ]


@router.get("/directories/{id}", operation_id="getStockDirectory")
def directory(id: UUID, request: Request, service: Service) -> DirectoryDetailsResponse:
    entry, usage = service.directory(session_token(request), id)
    return DirectoryDetailsResponse(**asdict(entry), system=entry.system, usage=usage)


@router.put(
    "/directories/{id}", operation_id="renameStockDirectory", dependencies=[Depends(enforce_csrf)]
)
def rename_directory(
    id: UUID, request: Request, data: DirectoryRenameInput, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(service.rename_directory(session_token(request), key, id, data.name))
    )


@router.delete(
    "/directories/{id}", operation_id="deleteStockDirectory", dependencies=[Depends(enforce_csrf)]
)
def delete_directory(id: UUID, request: Request, service: Service, key: Key) -> OperationResponse:
    return OperationResponse(**asdict(service.delete_directory(session_token(request), key, id)))


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
        InvoiceResponse(**asdict(i), debt_minor=i.total_minor - i.paid_minor)
        for i in service.invoices(session_token(request), offset, limit)
    ]


@router.get("/invoices/{invoice_id}/payments", operation_id="listInvoicePayments")
def invoice_payments(
    invoice_id: UUID, request: Request, service: Service
) -> list[InvoicePaymentResponse]:
    return [
        InvoicePaymentResponse(**asdict(p))
        for p in service.invoice_payments(session_token(request), invoice_id)
    ]


@router.post(
    "/invoices/{invoice_id}/payments",
    operation_id="payInvoice",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def pay_invoice(
    invoice_id: UUID, data: InvoicePaymentInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.pay_invoice(
                session_token(request),
                key,
                invoice_id,
                data.amount_minor,
                data.payment_method_id,
                data.paid_at,
                data.note,
            )
        )
    )


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
                data.paid_minor,
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


class ImageResponse(BaseModel):
    image: str


@router.put(
    "/items/{item_id}/image",
    operation_id="setItemImage",
    dependencies=[Depends(enforce_csrf)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {t: {"schema": {"type": "string", "format": "binary"}} for t in PHOTO_TYPES},
        }
    },
)
async def set_image(item_id: UUID, request: Request, service: Service) -> ImageResponse:
    if request.headers.get("content-type", "").split(";")[0] not in PHOTO_TYPES:
        raise InventoryError(
            "VALIDATION_ERROR",
            "Поддерживаются JPEG, PNG и WebP",
            {"image": ["Поддерживаются JPEG, PNG и WebP"]},
        )
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_UPLOAD:
            raise InventoryError("VALIDATION_ERROR", "Фото до 8 МБ", {"image": ["Фото до 8 МБ"]})
    digest = await run_in_threadpool(
        service.set_image, session_token(request), item_id, bytes(data)
    )
    return ImageResponse(image=digest)


@router.delete(
    "/items/{item_id}/image",
    operation_id="removeItemImage",
    status_code=204,
    dependencies=[Depends(enforce_csrf)],
)
def remove_image(item_id: UUID, request: Request, service: Service) -> None:
    service.remove_image(session_token(request), item_id)


@router.get(
    "/items/{item_id}/image",
    operation_id="getItemImage",
    response_class=Response,
    responses={200: {"content": {"image/webp": {}}}},
)
def get_image(item_id: UUID, request: Request, service: Service) -> Response:
    data = service.image(session_token(request), item_id)
    if data is None:
        raise InventoryError("NOT_FOUND", "Фото не найдено")
    return Response(content=data, media_type="image/webp")
