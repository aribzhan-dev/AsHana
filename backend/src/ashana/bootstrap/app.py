import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from ashana.bootstrap.catalog import catalog_service
from ashana.bootstrap.database import create_database_engine, database_is_ready
from ashana.bootstrap.errors import ErrorResponse, error_response, register_error_handlers
from ashana.bootstrap.inventory import inventory_service
from ashana.bootstrap.order_worker import order_worker
from ashana.bootstrap.orders import order_service
from ashana.bootstrap.production import production_service
from ashana.bootstrap.settings import Settings
from ashana.modules.catalog.presentation.http import router as catalog_router
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.infrastructure.database import PostgresIdentityUnitOfWork
from ashana.modules.identity.infrastructure.security import ArgonPasswords, KazakhstanMobilePhones
from ashana.modules.identity.presentation.http import router
from ashana.modules.inventory.presentation.http import router as inventory_router
from ashana.modules.notifications.infrastructure.delivery import TelegramSender
from ashana.modules.orders.presentation.http import router as orders_router
from ashana.modules.production.presentation.http import router as production_router

logger = logging.getLogger("ashana")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["ashana-api"] = "ashana-api"


def create_app(
    settings: Settings | None = None,
    readiness_probe: Callable[[], bool] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if readiness_probe is not None:
            app.state.readiness_probe = readiness_probe
            yield
            return
        configured = settings or Settings()  # type: ignore[call-arg]
        engine = create_database_engine(configured)
        app.state.settings = configured
        app.state.identity = IdentityService(
            lambda: PostgresIdentityUnitOfWork(engine),
            ArgonPasswords(),
            KazakhstanMobilePhones(),
            allow_demo=configured.demo_identity,
            session_seconds=configured.session_seconds,
        )
        app.state.orders = order_service(engine, app.state.identity, configured)
        app.state.catalog = catalog_service(engine, app.state.identity)
        app.state.inventory = inventory_service(engine, app.state.identity)
        app.state.production = production_service(engine, app.state.identity)
        app.state.readiness_probe = lambda: database_is_ready(engine)
        sender = (
            TelegramSender(
                configured.telegram_bot_token.get_secret_value(), configured.telegram_chat_id
            )
            if configured.telegram_bot_token and configured.telegram_chat_id
            else None
        )
        worker = (
            asyncio.create_task(order_worker(app.state.orders, engine, sender))
            if configured.environment != "test"
            else None
        )
        try:
            yield
        finally:
            if worker:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker
            engine.dispose()

    app = FastAPI(
        title="AsHana API",
        version="0.1.0",
        description="API системы столовой",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    register_error_handlers(app)
    app.include_router(router)
    app.include_router(catalog_router)
    app.include_router(orders_router)
    app.include_router(inventory_router)
    app.include_router(production_router)

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(
                request, 500, "INTERNAL_ERROR", "Не удалось выполнить действие"
            )
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith(
            (
                "/api/v1/auth/",
                "/api/v1/admin/",
                "/api/v1/inventory/",
                "/api/v1/production/",
                "/api/v1/catalog/",
                "/api/v1/orders",
            )
        ):
            response.headers["Cache-Control"] = "no-store"
        # Never log URLs, query strings, bodies or exception text: they can contain secrets.
        logger.info(
            json.dumps(
                {
                    "message": "Запрос обработан",
                    "operation": "http_request",
                    "request_id": request.state.request_id,
                    "outcome": response.status_code,
                },
                ensure_ascii=False,
            )
        )
        return response

    @app.get("/api/v1/health/live", operation_id="getLiveness", tags=["Состояние"])
    def liveness() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/api/v1/health/ready",
        operation_id="getReadiness",
        tags=["Состояние"],
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}},
    )
    def readiness(request: Request) -> HealthResponse | Response:
        if not request.app.state.readiness_probe():
            return error_response(
                request, 503, "SERVICE_UNAVAILABLE", "Сервис временно недоступен. Попробуйте позже"
            )
        return HealthResponse(status="ok")

    return app
