import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from ashana.modules.realtime.domain.models import ChangeEvent

# Marks a subscriber that missed events; the client then reloads everything.
RESYNC = ChangeEvent("stock", "resync")


class Subscriber:
    def __init__(self, permissions: frozenset[str], guest: str = "") -> None:
        self.permissions = permissions
        self.guest = guest
        self.queue: asyncio.Queue[ChangeEvent] = asyncio.Queue(maxsize=100)

    def offer(self, event: ChangeEvent) -> None:
        if self.guest:
            # A guest hears only about their own orders, and a resync to reload them.
            if event.topic != "orders" or (event.owner != self.guest and event.kind != "resync"):
                return
        elif not event.visible_to(self.permissions):
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # A slow screen loses detail, not correctness: drop backlog and ask for a reload.
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait(RESYNC)


class Hub:
    """In-process fan-out. Each API process runs its own PostgreSQL listener."""

    def __init__(self) -> None:
        self.subscribers: set[Subscriber] = set()
        # True while the database listener is attached; otherwise screens rely on polling.
        self.listening = False

    @contextmanager
    def subscribe(self, permissions: frozenset[str], guest: str = "") -> Iterator[Subscriber]:
        subscriber = Subscriber(permissions, guest)
        self.subscribers.add(subscriber)
        try:
            yield subscriber
        finally:
            self.subscribers.discard(subscriber)

    def publish(self, event: ChangeEvent) -> None:
        for subscriber in list(self.subscribers):
            subscriber.offer(event)

    def resync(self) -> None:
        for subscriber in list(self.subscribers):
            subscriber.offer(ChangeEvent("orders", "resync"))
            subscriber.offer(ChangeEvent("pos", "resync"))
            subscriber.offer(RESYNC)
