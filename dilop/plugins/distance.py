"""Distance plugin: ranging, proximity alerts, geofence, path length, remote-link range."""
from __future__ import annotations

import math
from typing import List

from ..plugin import Plugin, PluginContract, Resources, PRIORITY_DISTANCE
from ..state import Command, SuitState

PROXIMITY_WARN_M = 3.0
LINK_WARN_FRACTION = 0.8


class DistancePlugin(Plugin):
    contract = PluginContract(
        name="distance",
        capabilities=["ranging", "proximity_alerts", "geofence", "path_length", "remote_link_range"],
        resources=Resources(power_w=25, compute=0.2, bandwidth_kbps=4),
        safety_constraints=["read-only sensors", "alerts only; motion is safety's call"],
        priority=PRIORITY_DISTANCE, essential=True)

    def __init__(self) -> None:
        self._last = None

    def step(self, s: SuitState) -> List[Command]:
        out: List[Command] = []
        if self._last is not None:
            s.path_m += math.dist(self._last, s.position_m)
        self._last = s.position_m
        if s.nearest_obstacle_m < PROXIMITY_WARN_M:
            out.append(Command("distance", "display", "proximity", round(s.nearest_obstacle_m, 2), reason="obstacle near"))
        r = math.hypot(*s.position_m)
        if r > s.geofence_m:
            out.append(Command("distance", "display", "geofence", round(r - s.geofence_m, 1), reason=f"{r:.0f} m from origin"))
        frac = s.remote_link_m / s.remote_link_range_m if s.remote_link_range_m else 1
        if frac >= 1:
            out.append(Command("distance", "comms", "link_lost", round(s.remote_link_m), essential=True, reason="beyond ship link range"))
        elif frac >= LINK_WARN_FRACTION:
            out.append(Command("distance", "comms", "boost_link", round(frac, 2), reason="near edge of ship link range"))
        out.append(Command("distance", "telemetry", "path_m", round(s.path_m, 1)))
        return out
