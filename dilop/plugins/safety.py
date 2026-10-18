"""Safety plugin: always on, highest priority, can veto.

Collision avoidance, force limiting, fall detection, thermal and electrical
cutoffs, emergency stop, radiation alarm, and the power logic (ship vs battery).
"""
from __future__ import annotations

from typing import List, Optional

from ..plugin import Plugin, PluginContract, Resources, PRIORITY_SAFETY
from ..power import decide_power
from ..state import Command, SuitState

TTC_STOP_S = 1.5
MIN_CLEARANCE_M = 0.5
MAX_JOINT_FORCE_N = 400.0
CORE_HOT_C, CORE_COLD_C = 39.0, 35.0
MOTION_TARGETS = {"motion", "actuator", "assist"}


class SafetyPlugin(Plugin):
    contract = PluginContract(
        name="safety",
        capabilities=["collision_avoidance", "force_limit", "fall_detection", "thermal_cutoff", "electrical_cutoff",
                      "emergency_stop", "radiation_alarm", "power_source_selection"],
        resources=Resources(power_w=15, compute=0.15, bandwidth_kbps=8),
        safety_constraints=["always loaded", "veto authority over all plugins", "fails closed"],
        priority=PRIORITY_SAFETY, essential=True, can_veto=True)

    def __init__(self) -> None:
        self._prev_accel = 1.0
        self._prev_transfer = 0.0
        self.power = None
        self.estop = False

    def step(self, s: SuitState) -> List[Command]:
        out: List[Command] = []
        # collision
        ttc = s.nearest_obstacle_m / s.closing_speed_mps if s.closing_speed_mps > 0 else float("inf")
        self.estop = s.nearest_obstacle_m < MIN_CLEARANCE_M or ttc < TTC_STOP_S
        # fall: free-fall dip followed by an impact spike
        fall = self._prev_accel < 0.3 and s.accel_g > 2.5
        self._prev_accel = s.accel_g
        if fall:
            self.estop = True
            out.append(Command("safety", "comms", "distress", "fall detected", essential=True, reason="fall"))
        if self.estop:
            out.append(Command("safety", "motion", "emergency_stop", True, essential=True,
                               reason=f"obstacle {s.nearest_obstacle_m:.1f} m, ttc {ttc:.1f} s" if not fall else "fall"))
        if s.joint_force_n > MAX_JOINT_FORCE_N:
            out.append(Command("safety", "actuator", "force_limit", MAX_JOINT_FORCE_N, essential=True, reason=f"{s.joint_force_n:.0f} N"))
        # thermal
        if s.core_temp_c >= CORE_HOT_C:
            out.append(Command("safety", "hvac", "cutoff_heating", True, essential=True, reason=f"core {s.core_temp_c:.1f} °C"))
        elif s.core_temp_c <= CORE_COLD_C:
            out.append(Command("safety", "hvac", "cutoff_cooling", True, essential=True, reason=f"core {s.core_temp_c:.1f} °C"))
        # power
        p = decide_power(nuclear_reading_usv_h=s.nuclear_reading_usv_h, ship_reactor_online=s.ship_reactor_online,
                         ship_link_quality=s.ship_link_quality, remote_link_m=s.remote_link_m,
                         remote_link_range_m=s.remote_link_range_m, battery_pct=s.battery_pct,
                         demand_w=s.load_w, previous_transfer_w=self._prev_transfer)
        self._prev_transfer = p.transfer_w
        self.power = p
        out.append(Command("safety", "power", "select_source", {"source": p.source, "transfer_w": p.transfer_w}, essential=True, reason=p.reason))
        if p.radiation_alarm:
            out.append(Command("safety", "display", "alert", f"radiation {s.nuclear_reading_usv_h:.0f} µSv/h: leave the area", essential=True))
        if p.veto:
            out.append(Command("safety", "display", "alert", "battery critical, no ship power: safe baseline", essential=True))
        return out

    def veto(self, c: Command, s: SuitState) -> Optional[str]:
        if c.source == "safety":
            return None
        if self.estop and c.target in MOTION_TARGETS:
            return "emergency stop active"
        if self.power is not None and self.power.veto and not c.essential:
            return "battery critical with no ship power"
        if s.core_temp_c >= CORE_HOT_C and c.target == "hvac" and c.action == "heat":
            return "core temperature high"
        if s.core_temp_c <= CORE_COLD_C and c.target == "hvac" and c.action == "cool":
            return "core temperature low"
        return None
