import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.engine import Engine

from ashana.modules.notifications.infrastructure.delivery import deliver_one
from ashana.modules.orders.application.service import OrderService

# Kitchen messages older than this are history, not news: never send them late.
STALE = timedelta(hours=6)


async def order_worker(
    service: OrderService, engine: Engine, sender: Callable[[str], None] | None
) -> None:
    while True:
        try:
            await asyncio.to_thread(service.expire)
            if sender:
                for _ in range(10):
                    if not await asyncio.to_thread(deliver_one, engine, sender, None, STALE):
                        break
        except Exception:
            logging.getLogger("ashana").warning(
                "Не удалось обновить резервы или уведомления; повтор позже"
            )
        await asyncio.sleep(15)
