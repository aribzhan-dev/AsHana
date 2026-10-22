import asyncio
from contextlib import suppress
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.orders.application.service import OrderService
from ashana.modules.realtime.application.hub import Hub

router = APIRouter()
RECHECK_SECONDS = 60


@router.websocket("/api/v1/staff/events")
async def staff_events(websocket: WebSocket) -> None:
    settings = cast(Settings, websocket.app.state.settings)
    identity = cast(IdentityService, websocket.app.state.identity)
    hub = cast(Hub, websocket.app.state.hub)
    # Browsers send cookies with cross-site WebSocket requests, so check the origin.
    if websocket.headers.get("origin") not in settings.allowed_origins:
        await websocket.close(code=4403)
        return
    token = websocket.cookies.get(settings.session_cookie, "")[:256]

    def permissions() -> frozenset[str] | None:
        try:
            return identity.authenticate(token).user.effective_permissions
        except IdentityError:
            return None

    allowed = await asyncio.to_thread(permissions) if token else None
    if not allowed:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    with hub.subscribe(allowed) as subscriber:
        receiver = asyncio.create_task(drain(websocket))
        try:
            while not receiver.done():
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), RECHECK_SECONDS)
                except TimeoutError:
                    # Revoked sessions and changed roles end the stream.
                    current = await asyncio.to_thread(permissions)
                    if current is None:
                        await websocket.close(code=4401)
                        return
                    subscriber.permissions = current
                    await websocket.send_text('{"topic":"ping"}')
                    continue
                await websocket.send_text(event.message())
        except WebSocketDisconnect:
            pass
        finally:
            receiver.cancel()
            with suppress(asyncio.CancelledError, WebSocketDisconnect):
                await receiver


async def drain(websocket: WebSocket) -> None:
    """Read and discard client frames so a closed socket is noticed promptly."""
    with suppress(WebSocketDisconnect):
        while True:
            await websocket.receive_text()


@router.websocket("/api/v1/orders/live")
async def guest_events(websocket: WebSocket) -> None:
    settings = cast(Settings, websocket.app.state.settings)
    orders = cast(OrderService, websocket.app.state.orders)
    hub = cast(Hub, websocket.app.state.hub)
    if websocket.headers.get("origin") not in settings.allowed_origins:
        await websocket.close(code=4403)
        return
    token = websocket.cookies.get(settings.guest_cookie, "")

    def guest() -> str | None:
        try:
            return str(orders.guest_id(token))
        except IdentityError:
            return None

    owner = await asyncio.to_thread(guest) if token else None
    if not owner:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    with hub.subscribe(frozenset(), owner) as subscriber:
        receiver = asyncio.create_task(drain(websocket))
        try:
            while not receiver.done():
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), RECHECK_SECONDS)
                except TimeoutError:
                    await websocket.send_text('{"topic":"ping"}')
                    continue
                await websocket.send_text(event.message())
        except WebSocketDisconnect:
            pass
        finally:
            receiver.cancel()
            with suppress(asyncio.CancelledError, WebSocketDisconnect):
                await receiver
