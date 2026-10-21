import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.engine import Engine

from ashana.modules.notifications.infrastructure.delivery import deliver_one
from ashana.modules.orders.application.service import OrderService


async def order_worker(
    service: OrderService, engine: Engine, sender: Callable[[str], None] | None
) -> None:
    while True:
        try:
            await asyncio.to_thread(service.expire)
            if sender:
                for _ in range(10):
                    if not await asyncio.to_thread(deliver_one, engine, sender):
                        break
        except Exception:
            logging.getLogger("ashana").warning(
                "Не удалось обновить резервы или уведомления; повтор позже"
            )
        await asyncio.sleep(15)
