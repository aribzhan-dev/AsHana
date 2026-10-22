import asyncio

from ashana.modules.realtime.application.hub import Hub
from ashana.modules.realtime.domain.models import ChangeEvent


def test_change_event_parsing_rejects_unknown_topics_and_trims_fields() -> None:
    event = ChangeEvent.parse('{"topic":"orders","kind":"confirmed","id":"abc"}')
    assert event == ChangeEvent("orders", "confirmed", "abc")
    assert ChangeEvent.parse('{"topic":"secrets"}') is None
    assert ChangeEvent.parse("not json") is None
    assert ChangeEvent.parse("[1]") is None
    long = ChangeEvent.parse('{"topic":"stock","kind":"' + "x" * 100 + '"}')
    assert long is not None and len(long.kind) == 30


def test_hub_sends_only_permitted_topics_and_resyncs_slow_screens() -> None:
    async def scenario() -> None:
        hub = Hub()
        with (
            hub.subscribe(frozenset({"kitchen.read"})) as kitchen,
            hub.subscribe(frozenset({"inventory.manage"})) as store,
        ):
            hub.publish(ChangeEvent("orders", "confirmed", "1"))
            hub.publish(ChangeEvent("pos", "success", "2"))
            hub.publish(ChangeEvent("stock"))
            assert [e.topic for e in drain(kitchen.queue)] == ["orders", "stock"]
            assert [e.topic for e in drain(store.queue)] == ["stock"]
            for n in range(150):
                hub.publish(ChangeEvent("orders", "confirmed", str(n)))
            backlog = drain(kitchen.queue)
            assert backlog[0].kind == "resync" and len(backlog) < 100
        assert not hub.subscribers

    asyncio.run(scenario())


def test_guest_hears_only_own_orders_and_owner_is_never_sent() -> None:
    async def scenario() -> None:
        hub = Hub()
        with hub.subscribe(frozenset(), "guest-a") as guest:
            hub.publish(ChangeEvent("orders", "ready", "1", "guest-a"))
            hub.publish(ChangeEvent("orders", "ready", "2", "guest-b"))
            hub.publish(ChangeEvent("stock"))
            hub.publish(ChangeEvent("pos", "success", "3"))
            hub.resync()
            events = drain(guest.queue)
            assert [(e.subject_id, e.kind) for e in events] == [("1", "ready"), ("", "resync")]
            assert "guest-a" not in events[0].message()

    asyncio.run(scenario())


def drain(queue: asyncio.Queue[ChangeEvent]) -> list[ChangeEvent]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items
