from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.inventory.domain.models import InventoryError


class ErrorResponse(BaseModel):
    code: str
    message: str
    field_errors: dict[str, list[str]] = Field(default_factory=dict)
    request_id: str


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    field_errors: dict[str, list[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            code=code,
            message=message,
            field_errors=field_errors or {},
            request_id=request.state.request_id,
        ).model_dump(),
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IdentityError)
    async def identity_error(request: Request, exc: IdentityError) -> JSONResponse:
        statuses = {
            "VALIDATION_ERROR": 422,
            "INVALID_CREDENTIALS": 401,
            "UNAUTHENTICATED": 401,
            "FORBIDDEN": 403,
            "CSRF_FAILED": 403,
            "NOT_FOUND": 404,
            "RATE_LIMITED": 429,
            "LAST_ADMIN": 409,
            "USER_EXISTS": 409,
            "ADMIN_EXISTS": 409,
        }
        return error_response(
            request,
            statuses.get(exc.code, 400),
            exc.code,
            exc.message,
            exc.field_errors,
            {"Retry-After": "900"} if exc.code == "RATE_LIMITED" else None,
        )

    @app.exception_handler(InventoryError)
    async def inventory_error(request: Request, exc: InventoryError) -> JSONResponse:
        status = 422 if exc.code == "VALIDATION_ERROR" else 404 if exc.code == "NOT_FOUND" else 409
        return error_response(request, status, exc.code, exc.message, exc.field_errors)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        messages = {
            400: ("BAD_REQUEST", "Некорректный запрос"),
            401: ("UNAUTHENTICATED", "Войдите в свой аккаунт"),
            403: ("FORBIDDEN", "Доступ запрещён"),
            404: ("NOT_FOUND", "Страница не найдена"),
            405: ("METHOD_NOT_ALLOWED", "Действие недоступно"),
            409: ("CONFLICT", "Не удалось выполнить действие: данные изменились"),
            429: ("RATE_LIMITED", "Слишком много запросов. Попробуйте позже"),
            500: ("INTERNAL_ERROR", "Не удалось выполнить действие"),
        }
        code, message = messages.get(
            exc.status_code, ("REQUEST_FAILED", "Не удалось выполнить запрос")
        )
        return error_response(request, exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        field_errors: dict[str, list[str]] = {}
        translations = {
            "missing": "Обязательное поле",
            "int_parsing": "Введите целое число",
            "int_type": "Введите целое число",
            "string_type": "Введите текст",
            "bool_parsing": "Выберите допустимое значение",
            "json_invalid": "Некорректный формат запроса",
        }
        for error in exc.errors():
            # Locations and inputs can contain user-supplied keys; only expose declared fields.
            location = error.get("loc", ())
            field = safe_field_name(request, location)
            message = translations.get(error["type"], "Проверьте значение поля")
            field_errors.setdefault(field, []).append(message)
        return error_response(
            request, 422, "VALIDATION_ERROR", "Проверьте введённые данные", field_errors
        )


def safe_field_name(request: Request, location: tuple[Any, ...]) -> str:
    route = request.scope.get("route")
    dependant = getattr(route, "dependant", None)
    declared = {
        field.alias
        for group in (
            "path_params",
            "query_params",
            "header_params",
            "cookie_params",
            "body_params",
        )
        for field in getattr(dependant, group, ())
    }
    for parameter in getattr(dependant, "body_params", ()):
        declared.update(getattr(parameter.field_info.annotation, "model_fields", {}).keys())
    if len(location) > 1 and isinstance(location[1], str) and location[1] in declared:
        return location[1]
    return "request"
