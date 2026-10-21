import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, Uuid, or_, select
from sqlalchemy.engine import Connection, Engine

metadata = MetaData()
outbox = Table(
    "notification_outbox",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("text", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("lease", Uuid),
    Column("lease_until", DateTime(timezone=True)),
    Column("delivered_at", DateTime(timezone=True)),
    Column("error_code", String(30)),
)


class PostgresNotificationWriter:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def enqueue(self, id: UUID, text: str, now: datetime) -> None:
        self.connection.execute(
            outbox.insert().values(
                id=id, text=text, created_at=now, next_attempt_at=now, attempts=0
            )
        )


class DeliveryFailed(Exception):
    pass


class TelegramSender:
    def __init__(self, token: str, chat_id: str) -> None:
        self._token, self._chat_id = token, chat_id

    def __call__(self, message: str) -> None:
        payload = json.dumps(
            {"chat_id": self._chat_id, "text": message, "protect_content": True}
        ).encode()
        request = Request(
            f"https://api.telegram.org/bot{self._token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=8) as response:
                result = json.loads(response.read(65536))
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise DeliveryFailed("Отправка не подтверждена")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            # Transport exception text includes the bot token URL; never propagate or log it.
            raise DeliveryFailed("Telegram временно недоступен") from None


def deliver_one(engine: Engine, sender: Callable[[str], None], now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    lease = uuid4()
    with engine.begin() as connection:
        row = (
            connection.execute(
                select(outbox)
                .where(
                    outbox.c.delivered_at.is_(None),
                    outbox.c.attempts < 10,
                    outbox.c.next_attempt_at <= now,
                    or_(outbox.c.lease_until.is_(None), outbox.c.lease_until <= now),
                )
                .order_by(outbox.c.created_at, outbox.c.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if not row:
            return False
        id, message, attempts = row["id"], row["text"], row["attempts"] + 1
        connection.execute(
            outbox.update()
            .where(outbox.c.id == id)
            .values(lease=lease, lease_until=now + timedelta(seconds=60), attempts=attempts)
        )
    # External I/O never holds an order/stock transaction or database connection.
    try:
        sender(message)
    except DeliveryFailed:
        values = {
            "error_code": "TELEGRAM_UNAVAILABLE",
            "next_attempt_at": now + timedelta(seconds=min(3600, 30 * 2**attempts)),
            "lease": None,
            "lease_until": None,
        }
    else:
        values = {"delivered_at": now, "error_code": None, "lease": None, "lease_until": None}
    with engine.begin() as connection:
        connection.execute(
            outbox.update().where(outbox.c.id == id, outbox.c.lease == lease).values(**values)
        )
    return True
