from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from ashana.modules.inventory.domain.models import invalid

ALMATY = ZoneInfo("Asia/Almaty")


def meal_date(instant: datetime) -> date:
    return instant.astimezone(ALMATY).date()


def validate_period(starts_at: datetime, ends_at: datetime) -> None:
    if not starts_at.tzinfo or not ends_at.tzinfo:
        raise invalid("starts_at", "Укажите время с часовым поясом")
    if not timedelta(0) < ends_at - starts_at <= timedelta(days=1):
        raise invalid(
            "ends_at", "Окончание должно быть позже начала, длительность — не более суток"
        )


def price_minor(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 999999999999:
        raise invalid("price_minor", "Цена должна быть от 0 до 999999999999 тиынов")
    return value


@dataclass(frozen=True)
class Period:
    id: UUID
    name: str
    starts_at: datetime
    ends_at: datetime
    published: bool
    version: int
    actor_id: UUID
    created_at: datetime
    updated_at: datetime

    def active_at(self, now: datetime) -> bool:
        return self.published and self.starts_at <= now < self.ends_at


@dataclass(frozen=True)
class Entry:
    id: UUID
    period_id: UUID
    item_id: UUID
    description: str
    portion_label: str
    price_minor: int
    published: bool
    version: int
    actor_id: UUID
    created_at: datetime
    updated_at: datetime
    name: str = ""
    unit: str = "portion"
    category: str = ""


@dataclass(frozen=True)
class MenuEntry:
    id: UUID
    period_id: UUID
    period_name: str
    starts_at: datetime
    ends_at: datetime
    name: str
    unit: str
    description: str
    portion_label: str
    price_minor: int
    available: int
    category: str = ""
