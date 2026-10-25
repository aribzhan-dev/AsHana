from datetime import datetime
from uuid import UUID, uuid4

from ashana.modules.inventory.application.base import InventoryBase
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.domain.models import DirectoryEntry
from ashana.shared.domain import BusinessError, Result, invalid, text_value


class DirectoryOperations(InventoryBase):
    """Settings entries: suppliers, warehouses, payment methods, categories, expense items."""

    def directories(self, token: str, kind: str) -> list[DirectoryEntry]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.directories(kind)

    def create_directory(self, token: str, key: UUID, kind: str, name: str) -> Result:
        if kind not in ("supplier", "warehouse", "payment_method", "category", "expense_category"):
            raise invalid("kind", "Неизвестный справочник")

        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            # Menu entries store categories in 60 characters.
            limit = 60 if kind == "category" else 100
            entry = DirectoryEntry(uuid4(), kind, text_value(name, "name", limit))
            repo.add_directory(entry)
            return Result(entry.id, 1)

        return self._write(token, "directory_created", key, {"kind": kind, "name": name}, action)

    def directory(self, token: str, id: UUID) -> tuple[DirectoryEntry, dict[str, int]]:
        """An entry with the places that use it, for the settings preview."""
        with self.uow() as uow:
            uow.authorize(token)
            entry = uow.repository.directory(id)
            if not entry:
                raise BusinessError("NOT_FOUND", "Запись не найдена")
            return entry, uow.repository.directory_usage(entry)

    def rename_directory(self, token: str, key: UUID, id: UUID, name: str) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            entry = repo.directory(id, lock=True)
            if not entry:
                raise BusinessError("NOT_FOUND", "Запись не найдена")
            # Menu entries store categories in 60 characters.
            new = text_value(name, "name", 60 if entry.kind == "category" else 100)
            if new != entry.name:
                repo.rename_directory(entry, new)
            return Result(entry.id, 1)

        return self._write(token, "directory_renamed", key, {"id": id, "name": name}, action)

    def delete_directory(self, token: str, key: UUID, id: UUID) -> Result:
        def action(repo: InventoryRepository, actor: UUID, now: datetime) -> Result:
            entry = repo.directory(id, lock=True)
            if not entry:
                raise BusinessError("NOT_FOUND", "Запись не найдена")
            if entry.system:
                raise BusinessError(
                    "DIRECTORY_SYSTEM", "Системную запись нельзя удалить, только переименовать"
                )
            if repo.directory_usage(entry):
                raise BusinessError(
                    "DIRECTORY_IN_USE",
                    "Запись уже используется — её можно только переименовать",
                )
            repo.delete_directory(entry)
            return Result(entry.id, 1)

        return self._write(token, "directory_deleted", key, {"id": id}, action)
