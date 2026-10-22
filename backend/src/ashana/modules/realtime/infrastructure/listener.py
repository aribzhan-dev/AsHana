import asyncio
import logging

import psycopg

from ashana.bootstrap.settings import Settings
from ashana.modules.realtime.application.hub import Hub
from ashana.modules.realtime.domain.models import ChangeEvent

CHANNEL = "ashana_events"


async def listen(settings: Settings, hub: Hub) -> None:
    """Relay committed database change signals to connected screens; reconnect on failure."""
    delay = 1.0
    while True:
        try:
            connection = await psycopg.AsyncConnection.connect(
                host=settings.db_host,
                port=settings.db_port,
                dbname=settings.db_name,
                user=settings.db_user,
                password=settings.db_password.get_secret_value(),
                autocommit=True,
                connect_timeout=3,
            )
            async with connection:
                await connection.execute(f"LISTEN {CHANNEL}")
                hub.listening = True
                # Events may have been missed while disconnected.
                hub.resync()
                delay = 1.0
                async for notification in connection.notifies():
                    event = ChangeEvent.parse(notification.payload)
                    if event:
                        hub.publish(event)
        except asyncio.CancelledError:
            hub.listening = False
            raise
        except Exception:
            logging.getLogger("ashana").warning(
                "Канал обновлений недоступен; экраны используют периодическое обновление"
            )
        hub.listening = False
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)
