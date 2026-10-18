"""Plugin manager: load / unload / priority / resource arbitration / safety veto / isolation."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Type

from .bus import Bus
from .plugin import Plugin, PRIORITY_SOCIAL
from .power import LOW_BATTERY_PCT
from .state import Command, SuitState

MODES: Dict[str, List[str]] = {
    "work": ["safety", "comfort", "distance"],
    "explore": ["safety", "distance", "social"],
    "social": ["safety", "social", "comfort"],
    "baseline": ["safety", "distance"],
    "full": ["safety", "distance", "comfort", "social"],
}

COMPUTE_BUDGET = 1.0
BANDWIDTH_BUDGET_KBPS = 128.0
BASE_LOAD_W = 60.0              # life support, displays, the computer itself
MAX_BATTERY_DISCHARGE_W = 400.0


@dataclass
class TickReport:
    tick: int
    mode: str
    active: List[str]
    deferred: List[str]
    allowed: List[Command]
    vetoed: List[Command]
    events: List[str] = field(default_factory=list)
    power_source: str = "battery"
    power_in_w: float = 0.0
    load_w: float = 0.0
    battery_pct: float = 100.0
    baseline: bool = False

    def as_dict(self) -> dict:
        return {"tick": self.tick, "mode": self.mode, "active": self.active, "deferred": self.deferred,
                "allowed": [str(c) for c in self.allowed],
                "vetoed": [f"{c} (by {c.vetoed_by})" for c in self.vetoed], "events": self.events,
                "power_source": self.power_source, "power_in_w": self.power_in_w, "load_w": round(self.load_w, 1),
                "battery_pct": round(self.battery_pct, 2), "baseline": self.baseline}


class PluginManager:
    """The suit host. Boots, scans for plugins, runs a mode, arbitrates, isolates failures."""

    def __init__(self, bus: Optional[Bus] = None) -> None:
        self.bus = bus or Bus()
        self.registry: Dict[str, Type[Plugin]] = {}
        self.loaded: Dict[str, Plugin] = {}
        self.quarantined: Dict[str, str] = {}
        self.mode = "baseline"
        self.baseline = False

    # ---- discovery / lifecycle
    def register(self, cls: Type[Plugin]) -> None:
        name = cls.contract.name
        if name in self.registry and self.registry[name] is not cls:
            raise ValueError(f"plugin name {name!r} already registered")
        self.registry[name] = cls

    def scan(self, modules: Iterable[str] = ("dilop.plugins",)) -> List[str]:
        """Import modules and register every Plugin subclass with a contract (the suit 'boots and scans')."""
        found = []
        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            for obj in vars(mod).values():
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin and hasattr(obj, "contract"):
                    self.register(obj)
                    found.append(obj.contract.name)
        return sorted(set(found))

    def load(self, name: str, state: Optional[SuitState] = None) -> Plugin:
        if name in self.quarantined:
            raise RuntimeError(f"{name} is quarantined: {self.quarantined[name]}")
        if name not in self.registry:
            raise KeyError(f"unknown plugin {name!r}; registered: {sorted(self.registry)}")
        if name not in self.loaded:
            p = self.registry[name]()
            p.on_load(state or SuitState())
            self.loaded[name] = p
            self.bus.publish("events", f"loaded {name}")
        return self.loaded[name]

    def unload(self, name: str) -> None:
        p = self.loaded.get(name)
        if p is None:
            return
        if p.contract.can_veto:
            raise RuntimeError("the safety layer cannot be unloaded")
        p.on_unload()
        del self.loaded[name]
        self.bus.publish("events", f"unloaded {name}")

    def set_mode(self, mode: str, state: Optional[SuitState] = None) -> List[str]:
        if mode not in MODES:
            raise KeyError(f"unknown mode {mode!r}; modes: {sorted(MODES)}")
        want = [n for n in MODES[mode] if n not in self.quarantined]
        if "safety" not in want:
            want.insert(0, "safety")
        for name in list(self.loaded):
            if name not in want and not self.loaded[name].contract.can_veto:
                self.unload(name)
        for name in want:
            self.load(name, state)
        self.mode = mode
        return self.active()

    def active(self) -> List[str]:
        return [p.name for p in sorted(self.loaded.values(), key=lambda p: (p.contract.priority, p.name))]

    def quarantine(self, name: str, why: str) -> None:
        self.quarantined[name] = why
        p = self.loaded.pop(name, None)
        if p is not None:
            try:
                p.on_unload()
            except Exception:
                pass
        self.bus.publish("events", f"isolated {name}: {why}")

    # ---- arbitration
    def arbitrate(self, state: SuitState, power_available_w: float) -> tuple[List[Plugin], List[str]]:
        """Grant resources in priority order. Safety always runs; others run only if they fit."""
        compute = bandwidth = 0.0
        power = BASE_LOAD_W
        run, deferred = [], []
        for p in sorted(self.loaded.values(), key=lambda p: (p.contract.priority, p.name)):
            r = p.contract.resources
            if self.baseline and not p.contract.essential:
                deferred.append(f"{p.name} (safe baseline)")
                continue
            if (state.battery_pct <= LOW_BATTERY_PCT and state.power_in_w <= 0 and not p.contract.essential
                    and p.contract.priority >= PRIORITY_SOCIAL):
                deferred.append(f"{p.name} (low battery, shed first)")
                continue
            fits = (compute + r.compute <= COMPUTE_BUDGET + 1e-9 and bandwidth + r.bandwidth_kbps <= BANDWIDTH_BUDGET_KBPS
                    and power + r.power_w <= power_available_w)
            if fits or p.contract.can_veto:
                compute += r.compute; bandwidth += r.bandwidth_kbps; power += r.power_w
                run.append(p)
            else:
                deferred.append(f"{p.name} (resources)")
        return run, deferred

    # ---- one control cycle
    def tick(self, state: SuitState) -> TickReport:
        events: List[str] = []
        safety = next((p for p in self.loaded.values() if p.contract.can_veto), None)
        if safety is None:
            raise RuntimeError("no safety plugin loaded")
        available = MAX_BATTERY_DISCHARGE_W * (1 if state.battery_pct > 0 else 0) + state.power_in_w
        run, deferred = self.arbitrate(state, available)
        state.load_w = BASE_LOAD_W + sum(p.contract.resources.power_w for p in run)

        proposals: List[Command] = []
        for p in run:
            try:
                proposals.extend(p.step(state))
            except Exception as exc:
                if p.contract.can_veto:
                    # safety itself failed: fail closed
                    state.emergency_stop = True
                    self.baseline = True
                    events.append(f"SAFETY FAULT {exc!r}: emergency stop, safe baseline")
                    proposals.append(Command("manager", "motion", "emergency_stop", True, essential=True, reason="safety fault"))
                else:
                    self.quarantine(p.name, repr(exc))
                    events.append(f"isolated {p.name}: {exc!r}")

        # safe baseline follows the safety layer's power verdict
        power = getattr(safety, "power", None)
        new_baseline = bool(power and power.veto)
        if new_baseline != self.baseline and not state.emergency_stop:
            events.append("entering safe baseline" if new_baseline else "leaving safe baseline")
            self.baseline = new_baseline

        allowed, vetoed = [], []
        for c in proposals:
            reason = None if c.source in ("safety", "manager") else safety.veto(c, state)
            if reason:
                c.vetoed_by = f"safety: {reason}"
                vetoed.append(c)
            else:
                allowed.append(c)

        # apply
        state.emergency_stop = any(c.target == "motion" and c.action == "emergency_stop" for c in allowed)
        for c in allowed:
            if c.target == "power" and c.action == "select_source":
                if state.tick > 0 and c.value["source"] != state.power_source:
                    events.append(f"power {state.power_source} -> {c.value['source']}: {c.reason}")
                state.power_source = c.value["source"]
                state.power_in_w = c.value["transfer_w"]
            elif c.target not in ("telemetry",):
                state.actuators[f"{c.target}.{c.action}"] = c.value
        if power is not None and power.radiation_alarm:
            events.append("radiation alarm")

        report = TickReport(state.tick, self.mode, [p.name for p in run], deferred, allowed, vetoed, events,
                            state.power_source, state.power_in_w, state.load_w, state.battery_pct, self.baseline)
        self.bus.publish("commands", [str(c) for c in allowed])
        self.bus.publish("telemetry", report.as_dict())
        for e in events:
            self.bus.publish("events", e)
        return report


def default_manager(mode: str = "work") -> PluginManager:
    m = PluginManager()
    m.scan()
    m.set_mode(mode)
    return m
