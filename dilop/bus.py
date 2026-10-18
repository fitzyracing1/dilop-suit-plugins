"""Standardized message bus: topics for state, commands and telemetry."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List


class Bus:
    """Tiny synchronous pub/sub. Handlers that raise are isolated (logged, never propagate)."""

    def __init__(self) -> None:
        self._subs: DefaultDict[str, List[Callable[[str, Any], None]]] = defaultdict(list)
        self.log: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    def subscribe(self, topic: str, handler: Callable[[str, Any], None]) -> None:
        self._subs[topic].append(handler)

    def publish(self, topic: str, payload: Any) -> None:
        self.log.append({"topic": topic, "payload": payload})
        if len(self.log) > 5000:
            del self.log[:1000]
        for t in (topic, "*"):
            for h in list(self._subs.get(t, ())):
                try:
                    h(topic, payload)
                except Exception as exc:  # isolation: one bad subscriber can't take the bus down
                    self.errors.append(f"{topic}: {exc!r}")
