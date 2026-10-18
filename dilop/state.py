"""Shared suit state and the commands plugins propose."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class SuitState:
    """Minimal state shared over the bus. Sensors write it, plugins read it."""
    tick: int = 0
    # body / environment
    core_temp_c: float = 37.0
    suit_temp_c: float = 22.0
    humidity_pct: float = 40.0
    pressure_hotspot_kpa: float = 8.0
    fatigue: float = 0.0              # 0..1
    accel_g: float = 1.0              # magnitude; a free-fall dip then spike signals a fall
    joint_force_n: float = 0.0
    # ranging
    nearest_obstacle_m: float = 10.0
    closing_speed_mps: float = 0.0
    geofence_m: float = 500.0         # radius
    position_m: tuple = (0.0, 0.0)
    path_m: float = 0.0
    remote_link_m: float = 0.0        # distance to the remote/ship link
    remote_link_range_m: float = 2000.0
    # power
    battery_pct: float = 100.0
    battery_capacity_wh: float = 1200.0
    nuclear_reading_usv_h: float = 0.0   # presence measurement only, never a power source
    ship_reactor_online: bool = True
    ship_link_quality: float = 1.0       # 0..1
    # social / coordination
    peers: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"
    inbox: List[str] = field(default_factory=list)
    # outputs (written by the manager after arbitration)
    power_source: str = "battery"
    power_in_w: float = 0.0
    load_w: float = 0.0
    emergency_stop: bool = False
    actuators: Dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Command:
    """A proposed output. The manager arbitrates; safety can veto."""
    source: str                 # plugin name
    target: str                 # actuator/display/comms channel, e.g. "hvac", "display", "comms", "power"
    action: str
    value: Any = None
    essential: bool = False     # survives a low-power safe baseline
    reason: str = ""
    vetoed_by: Optional[str] = None

    def __str__(self) -> str:
        v = "" if self.value is None else f"={self.value}"
        return f"{self.source}:{self.target}.{self.action}{v}"
