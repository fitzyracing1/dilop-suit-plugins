"""The plugin contract: capabilities, resources, safety constraints, priority."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .state import Command, SuitState

# Lower number = higher priority. Safety is always first.
PRIORITY_SAFETY = 0
PRIORITY_DISTANCE = 20
PRIORITY_COMFORT = 40
PRIORITY_SOCIAL = 60


@dataclass(frozen=True)
class Resources:
    power_w: float = 0.0        # average draw while active
    compute: float = 0.0        # share of the suit computer, 0..1
    bandwidth_kbps: float = 0.0


@dataclass(frozen=True)
class PluginContract:
    name: str
    capabilities: List[str]
    resources: Resources
    safety_constraints: List[str] = field(default_factory=list)
    priority: int = 50
    essential: bool = False     # kept in the low-power safe baseline
    can_veto: bool = False      # only the safety layer gets this


class Plugin:
    """Base class. Override `contract` and `step`. `veto` is only honoured for can_veto plugins."""

    contract: PluginContract

    def on_load(self, state: SuitState) -> None:  # pragma: no cover - default no-op
        pass

    def on_unload(self) -> None:  # pragma: no cover - default no-op
        pass

    def step(self, state: SuitState) -> List[Command]:
        raise NotImplementedError

    def veto(self, command: Command, state: SuitState) -> str | None:
        """Return a reason to block `command`, or None to allow it."""
        return None

    @property
    def name(self) -> str:
        return self.contract.name
