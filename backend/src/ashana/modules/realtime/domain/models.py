import json
from dataclasses import dataclass
from typing import Literal

Topic = Literal["orders", "pos", "stock"]

# A change signal only tells a screen what to reload; data still comes from the HTTP API.
TOPIC_PERMISSIONS: dict[str, frozenset[str]] = {
    "orders": frozenset({"kitchen.read"}),
    "pos": frozenset({"pos.sell"}),
    "stock": frozenset({"pos.sell", "kitchen.read", "inventory.manage"}),
}


@dataclass(frozen=True)
class ChangeEvent:
    topic: Topic
    kind: str = ""
    subject_id: str = ""
    # Guest who owns the order; used only for routing, never put into a message.
    owner: str = ""

    @classmethod
    def parse(cls, payload: str) -> "ChangeEvent | None":
        try:
            data = json.loads(payload)
        except ValueError:
            return None
        topic = data.get("topic") if isinstance(data, dict) else None
        if topic not in TOPIC_PERMISSIONS:
            return None
        return cls(
            topic,
            str(data.get("kind") or "")[:30],
            str(data.get("id") or "")[:36],
            str(data.get("guest") or "")[:36],
        )

    def visible_to(self, permissions: frozenset[str]) -> bool:
        return bool(TOPIC_PERMISSIONS[self.topic] & permissions)

    def message(self) -> str:
        return json.dumps({"topic": self.topic, "kind": self.kind, "id": self.subject_id})
