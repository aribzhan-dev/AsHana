from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, computed_field

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.catalog.application.service import CatalogService
from ashana.modules.identity.presentation.http import enforce_csrf, session_token
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.inventory.presentation.http import ItemResponse, OperationResponse

router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["Меню"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 404, 409, 422)},
)


def service_for(request: Request) -> CatalogService:
    return cast(CatalogService, request.app.state.catalog)


Service = Annotated[CatalogService, Depends(service_for)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=100)]


class PeriodInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, strict=True)
    starts_at: datetime
    ends_at: datetime
    published: bool = Field(strict=True)
    expected_version: int = Field(ge=0, le=2147483646, strict=True)


class MenuEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: UUID
    description: str = Field(max_length=1000, strict=True)
    category: str = Field(default="", max_length=60, strict=True)
    portion_label: str = Field(min_length=1, max_length=100, strict=True)
    price_minor: int = Field(ge=0, le=999999999999, strict=True)
    published: bool = Field(strict=True)
    expected_version: int = Field(ge=0, le=2147483646, strict=True)


class PeriodResponse(BaseModel):
    id: UUID
    name: str
    starts_at: datetime
    ends_at: datetime
    published: bool
    version: int
    actor_id: UUID
    created_at: datetime
    updated_at: datetime


class MenuEntryResponse(BaseModel):
    id: UUID
    period_id: UUID
    item_id: UUID
    name: str
    unit: Literal["pcs", "portion"]
    description: str
    category: str = ""
    portion_label: str
    price_minor: int
    published: bool
    version: int
    actor_id: UUID
    created_at: datetime
    updated_at: datetime


class PublicMenuEntry(BaseModel):
    id: UUID
    period_id: UUID
    period_name: str
    starts_at: datetime
    ends_at: datetime
    name: str
    unit: Literal["pcs", "portion"]
    description: str
    category: str = ""
    portion_label: str
    price_minor: int
    available: int
    image: str = Field(default="", exclude=True)

    # Addressed by the public entry id: internal item ids stay private.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_url(self) -> str:
        return f"/api/v1/media/menu/{self.id}?v={self.image[:16]}" if self.image else ""


class PublicMenuResponse(BaseModel):
    generated_at: datetime
    currency: Literal["KZT"] = "KZT"
    entries: list[PublicMenuEntry]


@router.get("/menu", operation_id="getPublicMenu")
def menu(
    service: Service, offset: Offset = 0, limit: Limit = 20, upcoming: bool = False
) -> PublicMenuResponse:
    now, entries = service.menu(offset, limit, upcoming)
    return PublicMenuResponse(
        generated_at=now, entries=[PublicMenuEntry(**asdict(e)) for e in entries]
    )


@router.get("/periods", operation_id="listMealPeriods")
def periods(
    day: date, request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[PeriodResponse]:
    return [
        PeriodResponse(**asdict(p))
        for p in service.periods(session_token(request), day, offset, limit)
    ]


@router.post(
    "/periods",
    operation_id="createMealPeriod",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def create_period(
    data: PeriodInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_period(
                session_token(request),
                key,
                None,
                data.expected_version,
                data.name,
                data.starts_at,
                data.ends_at,
                data.published,
            )
        )
    )


@router.put(
    "/periods/{period_id}", operation_id="updateMealPeriod", dependencies=[Depends(enforce_csrf)]
)
def update_period(
    period_id: UUID, data: PeriodInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_period(
                session_token(request),
                key,
                period_id,
                data.expected_version,
                data.name,
                data.starts_at,
                data.ends_at,
                data.published,
            )
        )
    )


@router.get("/periods/{period_id}/entries", operation_id="listMenuEntries")
def entries(
    period_id: UUID, request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[MenuEntryResponse]:
    return [
        MenuEntryResponse(**asdict(e))
        for e in service.entries(session_token(request), period_id, offset, limit)
    ]


@router.post(
    "/periods/{period_id}/entries",
    operation_id="createMenuEntry",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def create_entry(
    period_id: UUID, data: MenuEntryInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_entry(
                session_token(request),
                key,
                period_id,
                None,
                data.expected_version,
                data.item_id,
                data.description,
                data.portion_label,
                data.price_minor,
                data.published,
                data.category,
            )
        )
    )


@router.put(
    "/periods/{period_id}/entries/{entry_id}",
    operation_id="updateMenuEntry",
    dependencies=[Depends(enforce_csrf)],
)
def update_entry(
    period_id: UUID,
    entry_id: UUID,
    data: MenuEntryInput,
    request: Request,
    service: Service,
    key: Key,
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_entry(
                session_token(request),
                key,
                period_id,
                entry_id,
                data.expected_version,
                data.item_id,
                data.description,
                data.portion_label,
                data.price_minor,
                data.published,
                data.category,
            )
        )
    )


@router.post(
    "/permanent/sync",
    operation_id="syncPermanentGoods",
    dependencies=[Depends(enforce_csrf)],
)
def sync_permanent(request: Request, service: Service, key: Key) -> OperationResponse:
    return OperationResponse(**asdict(service.sync_permanent(session_token(request), key)))


@router.get("/items", operation_id="listCatalogItems")
def items(
    kind: Literal["prepared", "purchased"],
    request: Request,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[ItemResponse]:
    return [
        ItemResponse(**asdict(i))
        for i in service.items(session_token(request), kind, offset, limit)
    ]


media = APIRouter(prefix="/api/v1/media", tags=["Меню"])


@media.get(
    "/menu/{entry_id}",
    operation_id="getMenuPhoto",
    response_class=Response,
    responses={200: {"content": {"image/webp": {}}}, 404: {"model": ErrorResponse}},
)
def menu_photo(entry_id: UUID, request: Request, service: Service) -> Response:
    found = service.image(entry_id)
    if not found:
        raise InventoryError("NOT_FOUND", "Фото не найдено")
    data, digest = found
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            # The URL carries the digest, so a new photo gets a new URL.
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{digest[:32]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
