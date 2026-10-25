from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from ashana.bootstrap.errors import ErrorResponse
from ashana.bootstrap.http import OperationResponse, enforce_csrf, session_token
from ashana.modules.finance.application.service import FinanceService
from ashana.modules.finance.domain.models import Accrual, ProfitAndLoss
from ashana.modules.finance.infrastructure.database import hours

router = APIRouter(
    prefix="/api/v1/finance",
    tags=["Финансы"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 409, 422)},
)


def service_for(request: Request) -> FinanceService:
    return cast(FinanceService, request.app.state.finance)


Service = Annotated[FinanceService, Depends(service_for)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Money = Field(ge=-999999999999, le=999999999999, strict=True)
Positive = Field(ge=1, le=999999999999, strict=True)
Text200 = Field(default="", max_length=200, strict=True)


class PnlResponse(BaseModel):
    month: date
    revenue: int
    returns: int
    net_revenue: int
    cost_of_goods: int
    gross_profit: int
    writeoffs: int
    invoice_expenses: int
    expenses: dict[str, int]
    operating_expenses: int
    simple_profit: int
    commission: int
    payroll: int
    full_profit: int
    profit_shares: int
    net_profit: int
    sales_by_method: list[dict[str, Any]]

    @classmethod
    def build(cls, p: ProfitAndLoss) -> "PnlResponse":
        names = [
            "month",
            "revenue",
            "returns",
            "net_revenue",
            "cost_of_goods",
            "gross_profit",
            "writeoffs",
            "invoice_expenses",
            "expenses",
            "operating_expenses",
            "simple_profit",
            "commission",
            "payroll",
            "full_profit",
            "profit_shares",
            "net_profit",
            "sales_by_method",
        ]
        return cls(**{n: getattr(p, n) for n in names})


class WorkerResponse(BaseModel):
    id: UUID
    name: str
    position: str
    user_id: UUID | None
    user_name: str
    active: bool
    monthly_minor: int
    daily_minor: int
    hourly_minor: int
    sales_bp: int
    sales_base: Literal["all", "personal"]
    profit_bp: int
    profit_base: Literal["simple", "full"]
    version: int


class AccrualResponse(BaseModel):
    worker: WorkerResponse
    days: int
    hours: str
    monthly: int
    daily: int
    hourly: int
    sales_base_minor: int
    sales: int
    profit_base_minor: int
    profit: int
    total: int
    paid: int
    balance: int

    @classmethod
    def build(cls, a: Accrual) -> "AccrualResponse":
        values = asdict(a)
        values["worker"] = WorkerResponse(**asdict(a.worker))
        values["hours"] = hours(a.hours)
        return cls(**values, total=a.total, balance=a.balance)


class MonthResponse(BaseModel):
    pnl: PnlResponse
    payroll: list[AccrualResponse]


class MoneyResponse(BaseModel):
    id: UUID
    subject_id: UUID
    subject_name: str
    amount_minor: int
    payment_method_id: UUID
    method_name: str
    at: datetime
    note: str
    month: date | None
    kind: str


class ShiftResponse(BaseModel):
    id: UUID
    worker_id: UUID
    starts_at: datetime
    ends_at: datetime | None
    source: str
    note: str
    voided: bool
    hours: str


class OwnerResponse(BaseModel):
    id: UUID
    name: str
    share_bp: int
    active: bool
    version: int


class PlanResponse(BaseModel):
    month: date
    category: str
    target_minor: int
    version: int


class DetailsResponse(BaseModel):
    expenses: list[MoneyResponse]
    payments: list[MoneyResponse]
    dividends: list[MoneyResponse]
    shifts: list[ShiftResponse]
    owners: list[OwnerResponse]
    plans: list[PlanResponse]
    categories: dict[str, int]
    daily: dict[int, int]
    staff: list[dict[str, str]]


@router.get("/month", operation_id="getFinanceMonth")
def month(month: date, request: Request, service: Service) -> MonthResponse:
    pnl, accruals = service.month(session_token(request), month)
    return MonthResponse(
        pnl=PnlResponse.build(pnl), payroll=[AccrualResponse.build(a) for a in accruals]
    )


@router.get("/details", operation_id="getFinanceDetails")
def details(month: date, request: Request, service: Service) -> DetailsResponse:
    d = service.details(session_token(request), month)
    shifts = cast(list[Any], d["shifts"])
    return DetailsResponse(
        expenses=[MoneyResponse(**asdict(m)) for m in cast(list[Any], d["expenses"])],
        payments=[MoneyResponse(**asdict(m)) for m in cast(list[Any], d["payments"])],
        dividends=[MoneyResponse(**asdict(m)) for m in cast(list[Any], d["dividends"])],
        shifts=[ShiftResponse(**asdict(s), hours=hours(s.hours)) for s in shifts],
        owners=[OwnerResponse(**asdict(o)) for o in cast(list[Any], d["owners"])],
        plans=[PlanResponse(**asdict(p)) for p in cast(list[Any], d["plans"])],
        categories=cast(dict[str, int], d["categories"]),
        daily=cast(dict[int, int], d["daily"]),
        staff=cast(list[dict[str, str]], d["staff"]),
    )


class CommissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commission_bp: int = Field(ge=0, le=10000, strict=True)


@router.put(
    "/payment-methods/{method_id}/commission",
    operation_id="setPaymentCommission",
    dependencies=[Depends(enforce_csrf)],
)
def commission(
    method_id: UUID, data: CommissionInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(service.set_commission(session_token(request), key, method_id, data.commission_bp))
    )


class ExpenseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: UUID
    amount_minor: int = Money
    payment_method_id: UUID
    spent_at: datetime
    note: str = Text200


@router.post(
    "/expenses", operation_id="addExpense", status_code=201, dependencies=[Depends(enforce_csrf)]
)
def add_expense(
    data: ExpenseInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.add_expense(
                session_token(request),
                key,
                data.category_id,
                data.amount_minor,
                data.payment_method_id,
                data.spent_at,
                data.note,
            )
        )
    )


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: date
    category: str = Field(default="", max_length=60, strict=True)
    target_minor: int = Field(ge=0, le=999999999999, strict=True)
    expected_version: int = Field(ge=0, strict=True)


@router.put("/plans", operation_id="saveSalesPlan", dependencies=[Depends(enforce_csrf)])
def save_plan(data: PlanInput, request: Request, service: Service, key: Key) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_plan(
                session_token(request),
                key,
                data.month,
                data.category,
                data.target_minor,
                data.expected_version,
            )
        )
    )


class OwnerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, strict=True)
    share_bp: int = Field(ge=1, le=10000, strict=True)
    active: bool = True
    expected_version: int = Field(ge=0, strict=True)


@router.post(
    "/owners", operation_id="createOwner", status_code=201, dependencies=[Depends(enforce_csrf)]
)
def create_owner(
    data: OwnerInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_owner(
                session_token(request), key, None, data.name, data.share_bp, data.active, 0
            )
        )
    )


@router.put("/owners/{owner_id}", operation_id="updateOwner", dependencies=[Depends(enforce_csrf)])
def update_owner(
    owner_id: UUID, data: OwnerInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_owner(
                session_token(request),
                key,
                owner_id,
                data.name,
                data.share_bp,
                data.active,
                data.expected_version,
            )
        )
    )


class PayoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: date
    amount_minor: int = Positive
    payment_method_id: UUID
    paid_at: datetime
    note: str = Text200


@router.post(
    "/owners/{owner_id}/dividends",
    operation_id="payDividend",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def pay_dividend(
    owner_id: UUID, data: PayoutInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.pay_dividend(
                session_token(request),
                key,
                owner_id,
                data.month,
                data.amount_minor,
                data.payment_method_id,
                data.paid_at,
                data.note,
            )
        )
    )


class WorkerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, strict=True)
    position: str = Field(default="", max_length=100, strict=True)
    user_id: UUID | None = None
    active: bool = True
    monthly_minor: int = Field(default=0, ge=0, le=999999999999, strict=True)
    daily_minor: int = Field(default=0, ge=0, le=999999999999, strict=True)
    hourly_minor: int = Field(default=0, ge=0, le=999999999999, strict=True)
    sales_bp: int = Field(default=0, ge=0, le=10000, strict=True)
    sales_base: Literal["all", "personal"] = "all"
    profit_bp: int = Field(default=0, ge=0, le=10000, strict=True)
    profit_base: Literal["simple", "full"] = "full"
    expected_version: int = Field(default=0, ge=0, strict=True)


def save_worker(
    service: FinanceService, token: str, key: UUID, worker_id: UUID | None, data: WorkerInput
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.save_worker(
                token,
                key,
                worker_id,
                data.expected_version,
                data.name,
                data.position,
                data.user_id,
                data.active,
                data.monthly_minor,
                data.daily_minor,
                data.hourly_minor,
                data.sales_bp,
                data.sales_base,
                data.profit_bp,
                data.profit_base,
            )
        )
    )


@router.post(
    "/workers", operation_id="createWorker", status_code=201, dependencies=[Depends(enforce_csrf)]
)
def create_worker(
    data: WorkerInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return save_worker(service, session_token(request), key, None, data)


@router.put(
    "/workers/{worker_id}", operation_id="updateWorker", dependencies=[Depends(enforce_csrf)]
)
def update_worker(
    worker_id: UUID, data: WorkerInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return save_worker(service, session_token(request), key, worker_id, data)


class SalaryInput(PayoutInput):
    kind: Literal["advance", "salary", "bonus"]


@router.post(
    "/workers/{worker_id}/payments",
    operation_id="paySalary",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def pay_salary(
    worker_id: UUID, data: SalaryInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.pay_salary(
                session_token(request),
                key,
                worker_id,
                data.month,
                data.kind,
                data.amount_minor,
                data.payment_method_id,
                data.paid_at,
                data.note,
            )
        )
    )


class ShiftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    note: str = Text200


@router.post(
    "/workers/{worker_id}/shifts",
    operation_id="addShift",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def add_shift(
    worker_id: UUID, data: ShiftInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(
            service.add_shift(
                session_token(request), key, worker_id, data.starts_at, data.ends_at, data.note
            )
        )
    )


class VoidInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=200, strict=True)


@router.post(
    "/shifts/{shift_id}/void", operation_id="voidShift", dependencies=[Depends(enforce_csrf)]
)
def void_shift(
    shift_id: UUID, data: VoidInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(service.void_shift(session_token(request), key, shift_id, data.note))
    )


class MyShiftResponse(BaseModel):
    linked: bool
    worker_name: str
    started_at: datetime | None


@router.get("/my-shift", operation_id="getMyShift")
def my_shift(request: Request, service: Service) -> MyShiftResponse:
    worker, shift = service.my_shift(session_token(request))
    return MyShiftResponse(
        linked=worker is not None,
        worker_name=worker.name if worker else "",
        started_at=shift.starts_at if shift else None,
    )


class ToggleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: bool


@router.post("/my-shift", operation_id="toggleMyShift", dependencies=[Depends(enforce_csrf)])
def toggle_shift(
    data: ToggleInput, request: Request, service: Service, key: Key
) -> OperationResponse:
    return OperationResponse(
        **asdict(service.toggle_shift(session_token(request), key, data.start))
    )
