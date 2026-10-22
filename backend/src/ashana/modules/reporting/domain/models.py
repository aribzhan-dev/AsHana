from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from ashana.modules.inventory.domain.models import invalid

ReportKind = Literal[
    "sales",
    "production",
    "stock",
    "writeoffs",
    "top",
    "abc",
    "unsold",
    "returns",
    "inventory",
    "expenses",
    "cashbook",
    "debts",
]


@dataclass(frozen=True)
class ReportFilter:
    start: date
    end: date
    item_id: UUID | None = None
    period_id: UUID | None = None
    channel: Literal["all", "online", "cashier"] = "all"
    mode: Literal["mock", "real"] = "mock"

    def bounds(self) -> tuple[datetime, datetime]:
        if self.end < self.start or (self.end - self.start).days > 365 or self.end == date.max:
            raise invalid("end", "Выберите период от 1 до 366 дней, окончание не раньше начала")
        zone = ZoneInfo("Asia/Almaty")
        return (
            datetime.combine(self.start, time.min, zone),
            datetime.combine(self.end + timedelta(days=1), time.min, zone),
        )


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    format: Literal["text", "quantity", "money"] = "text"


@dataclass(frozen=True)
class Report:
    kind: ReportKind
    generated_at: datetime
    columns: tuple[Column, ...]
    rows: list[dict[str, str]]
    totals: dict[str, str]
    unit_totals: dict[str, dict[str, str]]
    total_rows: int
    offset: int
    limit: int
    note: str


COLUMNS: dict[ReportKind, tuple[Column, ...]] = {
    "sales": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("channel", "Канал"),
        Column("period", "Период питания"),
        Column("paid_quantity", "Оплачено", "quantity"),
        Column("issued_quantity", "Выдано", "quantity"),
        Column("cancelled_quantity", "Отменено", "quantity"),
        Column("expired_quantity", "Истёк резерв", "quantity"),
        Column("paid_minor", "Поступления", "money"),
        Column("issued_minor", "Выдано на сумму", "money"),
        Column("refund_minor", "Возвраты", "money"),
    ),
    "production": (
        Column("name", "Продукт"),
        Column("unit", "Ед."),
        Column("batches", "Выпусков", "quantity"),
        Column("quantity", "Выпущено", "quantity"),
    ),
    "stock": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("on_hand", "На складе", "quantity"),
        Column("reserved", "В резерве", "quantity"),
        Column("available", "Доступно", "quantity"),
        Column("blocked", "Недоступно вне резерва", "quantity"),
    ),
    "writeoffs": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("written_off", "Списано", "quantity"),
        Column("count_loss", "Недостача при пересчёте", "quantity"),
        Column("count_gain", "Излишек при пересчёте", "quantity"),
    ),
    "top": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("quantity", "Продано", "quantity"),
        Column("revenue_minor", "Выручка", "money"),
        Column("share", "Доля выручки, %"),
    ),
    "abc": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("revenue_minor", "Выручка", "money"),
        Column("share", "Доля, %"),
        Column("cumulative", "Накопительно, %"),
        Column("grade", "Группа"),
    ),
    "unsold": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("category", "Категория"),
        Column("on_hand", "Сейчас на складе", "quantity"),
    ),
    "returns": (
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("channel", "Канал"),
        Column("quantity", "Возвращено", "quantity"),
        Column("amount_minor", "Сумма возврата", "money"),
    ),
    "inventory": (
        Column("day_label", "Дата"),
        Column("name", "Товар"),
        Column("unit", "Ед."),
        Column("before_quantity", "По учёту", "quantity"),
        Column("after_quantity", "Фактически", "quantity"),
        Column("difference", "Расхождение", "quantity"),
        Column("reason", "Причина"),
        Column("author", "Сотрудник"),
    ),
    "expenses": (
        Column("day_label", "Дата"),
        Column("name", "Поставщик · накладная"),
        Column("goods_minor", "Товары", "money"),
        Column("expenses_minor", "Доп. расходы", "money"),
        Column("total_minor", "Итого", "money"),
        Column("paid_minor", "Оплачено", "money"),
    ),
    "cashbook": (
        Column("name", "Способ оплаты"),
        Column("income_minor", "Приход", "money"),
        Column("outcome_minor", "Расход", "money"),
        Column("balance_minor", "Сальдо", "money"),
    ),
    "debts": (
        Column("name", "Поставщик"),
        Column("invoices", "Накладных с долгом", "quantity"),
        Column("total_minor", "Сумма накладных", "money"),
        Column("paid_minor", "Оплачено", "money"),
        Column("debt_minor", "Долг", "money"),
    ),
}


@dataclass(frozen=True)
class Dashboard:
    generated_at: datetime
    totals: dict[str, str]
    top: list[dict[str, str]]
    low: list[dict[str, str]]
    hours: list[dict[str, str]]
