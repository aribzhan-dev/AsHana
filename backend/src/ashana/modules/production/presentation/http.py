from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ashana.bootstrap.errors import ErrorResponse
from ashana.modules.identity.presentation.http import enforce_csrf, session_token
from ashana.modules.inventory.domain.models import batch_state
from ashana.modules.inventory.presentation.http import ItemResponse, OperationResponse
from ashana.modules.production.application.service import ProductionService
from ashana.modules.production.domain.models import ConsumptionInput, IngredientInput, Recipe

router = APIRouter(
    prefix="/api/v1/production",
    tags=["Производство"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422)},
)


def service_for(request: Request) -> ProductionService:
    return cast(ProductionService, request.app.state.production)


Service = Annotated[ProductionService, Depends(service_for)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Offset = Annotated[int, Query(ge=0, le=1000000)]
Limit = Annotated[int, Query(ge=1, le=100)]
RawUnit = Literal["kg", "g", "l", "ml"]


class IngredientBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: UUID
    quantity: str = Field(min_length=1, max_length=24, strict=True)
    unit: RawUnit


class RecipeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_item_id: UUID
    previous_version: int = Field(ge=0, le=2147483646, strict=True)
    expected_yield: int = Field(ge=1, le=999999999, strict=True)
    portion_quantity: str = Field(min_length=1, max_length=24, strict=True)
    portion_unit: RawUnit
    instructions: str = Field(min_length=1, max_length=2000, strict=True)
    lines: list[IngredientBody] = Field(min_length=1, max_length=30)


class ConsumptionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    quantity: str = Field(min_length=1, max_length=24, strict=True)
    unit: RawUnit


class ProductionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe_id: UUID
    label: str = Field(min_length=1, max_length=100, strict=True)
    actual_yield: int = Field(ge=1, le=999999999, strict=True)
    expires_at: datetime
    suitability_confirmed: bool = Field(strict=True)
    consumption: list[ConsumptionBody] = Field(min_length=1, max_length=100)


class RecipeLineResponse(BaseModel):
    item_id: UUID
    item_name: str
    quantity: str
    unit: str


class RecipeResponse(BaseModel):
    id: UUID
    output_item_id: UUID
    output_name: str
    output_unit: str
    version: int
    expected_yield: int
    portion_quantity: str
    portion_unit: str
    instructions: str
    actor_id: UUID
    created_at: datetime
    lines: list[RecipeLineResponse]

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> "RecipeResponse":
        values = asdict(recipe)
        values["portion_quantity"] = str(recipe.portion_quantity)
        values["lines"] = [dict(asdict(line), quantity=str(line.quantity)) for line in recipe.lines]
        return cls(**values)


class RawBatchResponse(BaseModel):
    id: UUID
    item_id: UUID
    item_name: str
    label: str
    unit: str
    available: str
    status: str
    expires_at: datetime


class ConsumptionResponse(BaseModel):
    batch_id: UUID
    batch_label: str
    item_id: UUID
    item_name: str
    quantity: str
    unit: str
    movement_id: UUID


class ProductionResponse(BaseModel):
    actor_name: str = ""
    id: UUID
    recipe_id: UUID
    recipe_version: int
    output_name: str
    output_unit: str
    actual_yield: int
    label: str
    actor_id: UUID
    created_at: datetime
    expires_at: datetime
    consumption: list[ConsumptionResponse]


@router.get("/items", operation_id="listProductionItems")
def list_items(
    request: Request,
    service: Service,
    kind: Literal["raw", "prepared"],
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[ItemResponse]:
    return [
        ItemResponse(**asdict(item))
        for item in service.items(session_token(request), kind, offset, limit)
    ]


@router.get("/raw-batches", operation_id="listProductionRawBatches")
def list_batches(
    request: Request, service: Service, item_id: UUID, offset: Offset = 0, limit: Limit = 100
) -> list[RawBatchResponse]:
    batches = service.batches(session_token(request), item_id, offset, limit)
    now = datetime.now(UTC)
    return [
        RawBatchResponse(
            id=b.id,
            item_id=b.item_id,
            item_name=b.item_name,
            label=b.label,
            unit=b.unit,
            available=str(b.available_at(now)),
            status=batch_state(b, now),
            expires_at=b.expires_at,
        )
        for b in batches
    ]


@router.get("/recipes", operation_id="listProductionRecipes")
def list_recipes(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[RecipeResponse]:
    return [
        RecipeResponse.from_recipe(r)
        for r in service.recipes(session_token(request), offset, limit)
    ]


@router.post(
    "/recipes",
    operation_id="createProductionRecipe",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def create_recipe(
    data: RecipeInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.create_recipe(
                session_token(request),
                key,
                data.output_item_id,
                data.previous_version,
                data.expected_yield,
                data.portion_quantity,
                data.portion_unit,
                data.instructions,
                [IngredientInput(**line.model_dump()) for line in data.lines],
            )
        )
    )


@router.get("/batches", operation_id="listProductionBatches")
def list_productions(
    request: Request, service: Service, offset: Offset = 0, limit: Limit = 20
) -> list[ProductionResponse]:
    result = []
    for production in service.productions(session_token(request), offset, limit):
        values = asdict(production)
        values["consumption"] = [
            dict(asdict(c), quantity=str(c.quantity)) for c in production.consumption
        ]
        result.append(ProductionResponse(**values))
    return result


@router.post(
    "/batches",
    operation_id="confirmProduction",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def produce(
    data: ProductionInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.produce(
                session_token(request),
                key,
                data.recipe_id,
                data.label,
                data.actual_yield,
                data.expires_at,
                data.suitability_confirmed,
                [ConsumptionInput(**c.model_dump()) for c in data.consumption],
            )
        )
    )


@router.get("/recipes/{recipe_id}", operation_id="getProductionRecipe")
def get_recipe(recipe_id: UUID, request: Request, service: Service) -> RecipeResponse:
    return RecipeResponse.from_recipe(service.recipe(session_token(request), recipe_id))
