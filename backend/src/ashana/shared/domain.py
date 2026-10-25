import unicodedata
from dataclasses import dataclass
from uuid import UUID


class BusinessError(Exception):
    """A rule of the canteen was broken; the message is shown to the user in Russian."""

    def __init__(self, code: str, message: str, field_errors: dict[str, list[str]] | None = None):
        super().__init__(message)
        self.code, self.message, self.field_errors = code, message, field_errors or {}


def invalid(field: str, message: str) -> BusinessError:
    return BusinessError("VALIDATION_ERROR", message, {field: [message]})


def text_value(value: str, field: str, maximum: int = 200) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    if (
        not value
        or len(value) > maximum
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise invalid(field, f"Введите текст от 1 до {maximum} символов без управляющих знаков")
    return value


@dataclass(frozen=True)
class Result:
    """Outcome of an idempotent write: the changed record and its new version."""

    subject_id: UUID
    version: int
