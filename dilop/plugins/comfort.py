"""Comfort plugin: temperature/humidity, pressure distribution, vibration damping, posture, fatigue."""
from __future__ import annotations

from typing import List

from ..plugin import Plugin, PluginContract, Resources, PRIORITY_COMFORT
from ..state import Command, SuitState

SETPOINT_C = 22.0
HOTSPOT_KPA = 12.0


class ComfortPlugin(Plugin):
    contract = PluginContract(
        name="comfort",
        capabilities=["thermal_regulation", "humidity", "pressure_distribution", "vibration_damping", "posture_support", "fatigue_monitor"],
        resources=Resources(power_w=180, compute=0.1, bandwidth_kbps=1),
        safety_constraints=["never heats above 39 °C core", "assist limited by safety force limit"],
        priority=PRIORITY_COMFORT)

    def step(self, s: SuitState) -> List[Command]:
        out: List[Command] = []
        err = s.suit_temp_c - SETPOINT_C
        if err > 1.0 or s.core_temp_c > 38.0:
            out.append(Command("comfort", "hvac", "cool", round(min(100, 20 * max(err, 1)), 0)))
        elif err < -1.0:
            out.append(Command("comfort", "hvac", "heat", round(min(100, -20 * err), 0)))
        if s.humidity_pct > 65:
            out.append(Command("comfort", "hvac", "vent", round(s.humidity_pct - 50)))
        if s.pressure_hotspot_kpa > HOTSPOT_KPA:
            out.append(Command("comfort", "bladders", "redistribute", round(s.pressure_hotspot_kpa, 1)))
        out.append(Command("comfort", "dampers", "vibration_damping", "on"))
        if s.fatigue > 0.4:
            out.append(Command("comfort", "assist", "posture_support", round(min(1.0, s.fatigue), 2), reason=f"fatigue {s.fatigue:.2f}"))
        return out
