import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from ashana.modules.inventory.application.ports import InventoryRepository, InventoryUnitOfWork
from ashana.shared.domain import Result, invalid


def known_category(repo: InventoryRepository, category: str) -> str:
    """Return the directory spelling so one category is never stored twice."""
    if not category.strip():
        return ""
    wanted = category.strip().casefold()
    match = next((d for d in repo.directories("category") if d.name.casefold() == wanted), None)
    if not match:
        raise invalid("category", "Выберите категорию из списка или создайте новую")
    return match.name


class InventoryBase:
    """Shared state and the idempotent, audited write used by every inventory operation."""

    uow: Callable[[], InventoryUnitOfWork]
    clock: Callable[[], datetime]

    def _write(
        self,
        token: str,
        operation: str,
        key: UUID,
        payload: dict[str, object],
        action: Callable[[InventoryRepository, UUID, datetime], Result],
    ) -> Result:
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        with self.uow() as uow:
            actor = uow.authorize(token)
            replay = uow.repository.replay(actor, operation, key, fingerprint)
            if replay:
                return replay
            now = self.clock()
            result = action(uow.repository, actor, now)
            uow.repository.audit(actor, operation, result.subject_id, now)
            uow.repository.remember(actor, operation, key, fingerprint, result, now)
            uow.commit()
            return result
