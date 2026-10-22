from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from ashana.modules.inventory.domain.models import invalid

ALMATY = ZoneInfo("Asia/Almaty")


def month_bounds(month: date) -> tuple[datetime, datetime]:
    """A calendar month in Astana time, as [start, end)."""
    if month.day != 1:
        raise invalid("month", "Укажите месяц")
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return datetime.combine(month, time.min, ALMATY), datetime.combine(following, time.min, ALMATY)


def share(amount: int, basis_points: int) -> int:
    """amount × bp / 10000 in tiyn, half-up: no money appears or disappears in rounding."""
    if amount <= 0 or basis_points <= 0:
        return 0
    return int((Decimal(amount) * basis_points / 10000).quantize(Decimal(1), ROUND_HALF_UP))


@dataclass(frozen=True)
class Worker:
    id: UUID
    name: str
    position: str
    user_id: UUID | None
    active: bool
    monthly_minor: int
    daily_minor: int
    hourly_minor: int
    sales_bp: int
    sales_base: str
    profit_bp: int
    profit_base: str
    version: int
    created_at: datetime
    updated_at: datetime
    user_name: str = ""

    def validate(self) -> None:
        for name in ("monthly_minor", "daily_minor", "hourly_minor"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 999999999999:
                raise invalid(name, "Сумма должна быть от 0 до 9999999999,99 ₸")
        for name in ("sales_bp", "profit_bp"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 10000:
                raise invalid(name, "Процент должен быть от 0 до 100")
        if self.sales_base not in ("all", "personal"):
            raise invalid("sales_base", "Выберите, от каких продаж процент")
        if self.profit_base not in ("simple", "full"):
            raise invalid("profit_base", "Выберите способ расчёта прибыли")
        if self.sales_base == "personal" and self.sales_bp and not self.user_id:
            raise invalid("user_id", "Для процента от личных продаж привяжите аккаунт кассира")


@dataclass(frozen=True)
class Shift:
    id: UUID
    worker_id: UUID
    starts_at: datetime
    ends_at: datetime | None
    source: str
    note: str
    voided: bool
    actor_id: UUID
    created_at: datetime
    updated_at: datetime

    @property
    def hours(self) -> Decimal:
        if not self.ends_at or self.voided:
            return Decimal(0)
        return Decimal((self.ends_at - self.starts_at).total_seconds()) / 3600


@dataclass(frozen=True)
class Money:
    """An append-only money record: expense, salary payment or dividend."""

    id: UUID
    subject_id: UUID
    amount_minor: int
    payment_method_id: UUID
    at: datetime
    note: str
    actor_id: UUID
    created_at: datetime
    month: date | None = None
    kind: str = ""
    subject_name: str = ""
    method_name: str = ""


@dataclass(frozen=True)
class Owner:
    id: UUID
    name: str
    share_bp: int
    active: bool
    version: int
    created_at: datetime


@dataclass(frozen=True)
class Plan:
    month: date
    category: str
    target_minor: int
    version: int


@dataclass
class ProfitAndLoss:
    """Monthly result. Two profit lines serve different needs:
    simple = gross profit − operating expenses (before payroll and bank fees);
    full = simple − bank commission − payroll other than profit shares."""

    month: date
    revenue: int = 0
    returns: int = 0
    cost_of_goods: int = 0
    writeoffs: int = 0
    invoice_expenses: int = 0
    expenses: dict[str, int] = field(default_factory=dict)
    commission: int = 0
    payroll: int = 0
    profit_shares: int = 0
    sales_by_method: list[dict[str, object]] = field(default_factory=list)

    @property
    def net_revenue(self) -> int:
        return self.revenue - self.returns

    @property
    def gross_profit(self) -> int:
        return self.net_revenue - self.cost_of_goods

    @property
    def operating_expenses(self) -> int:
        return self.writeoffs + self.invoice_expenses + sum(self.expenses.values())

    @property
    def simple_profit(self) -> int:
        return self.gross_profit - self.operating_expenses

    @property
    def full_profit(self) -> int:
        return self.simple_profit - self.commission - self.payroll

    @property
    def net_profit(self) -> int:
        return self.full_profit - self.profit_shares

    def base(self, kind: str) -> int:
        return self.simple_profit if kind == "simple" else self.full_profit


@dataclass(frozen=True)
class Accrual:
    worker: Worker
    days: int
    hours: Decimal
    monthly: int
    daily: int
    hourly: int
    sales_base_minor: int
    sales: int
    profit_base_minor: int
    profit: int
    paid: int

    @property
    def total(self) -> int:
        return self.monthly + self.daily + self.hourly + self.sales + self.profit

    @property
    def balance(self) -> int:
        return self.total - self.paid


def hourly_pay(hours: Decimal, rate: int) -> int:
    return int((hours * rate).quantize(Decimal(1), ROUND_HALF_UP))
