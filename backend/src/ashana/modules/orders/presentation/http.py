from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.identity.presentation.http import enforce_csrf, session_token, settings_for
from ashana.modules.orders.application.service import OrderService
from ashana.modules.orders.domain.models import Choice, Order

router = APIRouter(
    prefix="/api/v1/orders",
    tags=["Заказы"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 404, 409, 422)},
)


def service_for(request: Request) -> OrderService:
    return cast(OrderService, request.app.state.orders)


Service = Annotated[OrderService, Depends(service_for)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=100)]


def guest_token(request: Request) -> str:
    return request.cookies.get(settings_for(request).guest_cookie, "")


class SlotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_id: UUID
    starts_at: datetime
    ends_at: datetime
    cutoff_at: datetime
    capacity: int = Field(strict=True, ge=1, le=1000)
    enabled: bool = Field(strict=True)
    expected_version: int = Field(strict=True, ge=0, le=2147483646)


class SlotResponse(BaseModel):
    id: UUID
    period_id: UUID
    starts_at: datetime
    ends_at: datetime
    cutoff_at: datetime
    capacity: int
    occupied: int
    enabled: bool
    version: int


class OrderChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: UUID
    quantity: int = Field(strict=True, ge=1, le=100)
    expected_price_minor: int = Field(strict=True, ge=0, le=999999999999)


class CheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: UUID
    lines: list[OrderChoice] = Field(min_length=1, max_length=100)


class OrderLineResponse(BaseModel):
    entry_id: UUID
    name: str
    portion_label: str
    unit: Literal["pcs", "portion"]
    quantity: int
    price_minor: int


class OrderResponse(BaseModel):
    id: UUID
    slot_id: UUID
    status: Literal[
        "pending_payment",
        "confirmed",
        "preparing",
        "ready",
        "completed",
        "cancelled",
        "expired",
        "no_show",
    ]
    total_minor: int
    currency: Literal["KZT"] = "KZT"
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int
    lines: list[OrderLineResponse]
    slot_starts_at: datetime
    slot_ends_at: datetime
    stock_issue: bool
    pickup_code: str | None = None

    @classmethod
    def from_order(cls, order: Order, *, staff: bool = False) -> "OrderResponse":
        values = asdict(order)
        if staff:
            values["pickup_code"] = None
        return cls(**values)


class OrderConfiguration(BaseModel):
    max_active: int
    max_portions: int
    reservation_seconds: int
    cutoff_minutes: int
    slot_minutes: int
    slot_capacity: int
    payment_mode: Literal["pending_mock"] = "pending_mock"


@router.get("/configuration", operation_id="getOrderConfiguration")
def configuration(service: Service) -> OrderConfiguration:
    return OrderConfiguration(**asdict(service.policy))


@router.post(
    "/guest",
    operation_id="ensureGuestAccess",
    status_code=204,
    dependencies=[Depends(enforce_csrf)],
)
def guest(request: Request, response: Response, service: Service) -> None:
    token = service.start_guest(
        guest_token(request), request.client.host if request.client else "unknown"
    )
    if token:
        settings = settings_for(request)
        response.set_cookie(
            settings.guest_cookie,
            token,
            max_age=30 * 86400,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )


@router.get("/slots", operation_id="getAvailableSlots")
def slots(period_id: UUID, service: Service) -> list[SlotResponse]:
    return [SlotResponse(**asdict(s)) for s in service.slots(period_id)]


@router.get("/staff/slots", operation_id="getManagedSlots")
def staff_slots(period_id: UUID, request: Request, service: Service) -> list[SlotResponse]:
    return [SlotResponse(**asdict(s)) for s in service.slots(period_id, session_token(request))]


class SlotSaved(BaseModel):
    id: UUID


@router.post(
    "/staff/slots",
    operation_id="createPickupSlot",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def create_slot(data: SlotInput, request: Request, service: Service, key: Key) -> SlotSaved:
    return SlotSaved(id=service.save_slot(session_token(request), key, None, **data.model_dump()))


@router.put(
    "/staff/slots/{id}", operation_id="updatePickupSlot", dependencies=[Depends(enforce_csrf)]
)
def update_slot(
    id: UUID, data: SlotInput, request: Request, service: Service, key: Key
) -> SlotSaved:
    return SlotSaved(id=service.save_slot(session_token(request), key, id, **data.model_dump()))


@router.post(
    "/checkout",
    operation_id="createGuestCheckout",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def checkout(data: CheckoutInput, request: Request, service: Service, key: Key) -> OrderResponse:
    return OrderResponse.from_order(
        service.checkout(
            guest_token(request), key, data.slot_id, [Choice(**c.model_dump()) for c in data.lines]
        )
    )


@router.get("", operation_id="listGuestOrders")
def own(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[OrderResponse]:
    return [
        OrderResponse.from_order(o) for o in service.own_orders(guest_token(request), offset, limit)
    ]


@router.get("/staff", operation_id="listStaffOrders")
def staff(
    request: Request,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 20,
    state: Literal["all", "active", "closed"] = "all",
) -> list[OrderResponse]:
    return [
        OrderResponse.from_order(o, staff=True)
        for o in service.staff_orders(session_token(request), offset, limit, state)
    ]


@router.post("/{id}/cancel", operation_id="cancelGuestOrder", dependencies=[Depends(enforce_csrf)])
def cancel(id: UUID, request: Request, service: Service) -> OrderResponse:
    return OrderResponse.from_order(service.cancel(guest_token(request), id))


@router.get("/checkouts", operation_id="listGuestCheckouts")
def checkouts(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[OrderResponse]:
    return [
        OrderResponse.from_order(o) for o in service.checkouts(guest_token(request), offset, limit)
    ]


class MockPaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["success", "failed", "timeout"]


@router.post(
    "/checkout/{id}/mock-payment",
    operation_id="payCheckoutMock",
    dependencies=[Depends(enforce_csrf)],
)
def mock_payment(
    id: UUID, data: MockPaymentInput, request: Request, service: Service, key: Key
) -> OrderResponse:
    from ashana.modules.identity.domain.models import IdentityError

    if settings_for(request).environment == "production":
        raise IdentityError("FORBIDDEN", "Тестовая оплата недоступна в рабочем режиме")
    return OrderResponse.from_order(
        service.mock_payment(guest_token(request), id, key, data.outcome)
    )


class KitchenTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["preparing", "ready", "completed"]
    expected_version: int = Field(strict=True, ge=1, le=2147483646)
    pickup_code: str = Field(default="", pattern=r"^(?:[0-9A-F]{8})?$")


@router.post(
    "/staff/{id}/transition",
    operation_id="transitionKitchenOrder",
    dependencies=[Depends(enforce_csrf)],
)
def transition(
    id: UUID, data: KitchenTransition, request: Request, service: Service, key: Key
) -> OrderResponse:
    return OrderResponse.from_order(
        service.transition(session_token(request), id, key, **data.model_dump()), staff=True
    )
