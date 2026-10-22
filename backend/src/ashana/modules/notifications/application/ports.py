from datetime import datetime
from typing import Protocol
from uuid import UUID


class NotificationWriter(Protocol):
    def enqueue(
        self, id: UUID, text: str, now: datetime, subject_id: UUID | None = None
    ) -> None: ...
