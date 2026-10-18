"""Power logic for the safety layer.

Nuclear material is treated strictly as a *measurement of presence*, never as a
power source. A dosimeter reading above background confirms the suit is inside
the ship's reactor field. When presence is confirmed and the ship can deliver,
power is transferred from the ship through a gate (link quality, range, ramp
limit). Otherwise the suit runs on its own battery. A critically low battery
with no ship power is a safety condition: the safety plugin vetoes every
non-essential load.
"""
from __future__ import annotations

from dataclasses import dataclass

PRESENCE_USV_H = 0.5          # above typical background (~0.1-0.3 µSv/h): reactor field present
DANGER_USV_H = 100.0          # radiation alarm: leave the area, independent of power
MIN_LINK_QUALITY = 0.6
MAX_TRANSFER_W = 900.0
RAMP_W_PER_TICK = 300.0
LOW_BATTERY_PCT = 20.0
CRITICAL_BATTERY_PCT = 8.0


@dataclass(frozen=True)
class PowerDecision:
    source: str            # "ship" | "battery" | "none"
    transfer_w: float      # gated power accepted from the ship this tick
    presence: bool         # nuclear reading confirms presence in the reactor field
    gate_open: bool
    level: str             # "ok" | "low" | "critical"
    veto: bool             # critical battery with no ship power -> veto non-essential loads
    radiation_alarm: bool
    reason: str


def decide_power(*, nuclear_reading_usv_h: float, ship_reactor_online: bool, ship_link_quality: float,
                 remote_link_m: float, remote_link_range_m: float, battery_pct: float,
                 demand_w: float, previous_transfer_w: float = 0.0) -> PowerDecision:
    presence = nuclear_reading_usv_h >= PRESENCE_USV_H
    alarm = nuclear_reading_usv_h >= DANGER_USV_H
    in_range = remote_link_m <= remote_link_range_m
    why = []
    if not presence:
        why.append("no reactor presence measured")
    if not ship_reactor_online:
        why.append("ship reactor offline")
    if ship_link_quality < MIN_LINK_QUALITY:
        why.append(f"link quality {ship_link_quality:.2f} < {MIN_LINK_QUALITY}")
    if not in_range:
        why.append("ship link out of range")
    gate = presence and ship_reactor_online and ship_link_quality >= MIN_LINK_QUALITY and in_range

    if gate:
        want = min(MAX_TRANSFER_W, max(0.0, demand_w) + (150.0 if battery_pct < 95 else 0.0))  # cover load + trickle charge
        want *= min(1.0, ship_link_quality)
        transfer = min(want, previous_transfer_w + RAMP_W_PER_TICK)
        source = "ship" if transfer > 0 else "battery"
    else:
        transfer = 0.0
        source = "battery" if battery_pct > 0 else "none"

    level = "critical" if battery_pct <= CRITICAL_BATTERY_PCT else "low" if battery_pct <= LOW_BATTERY_PCT else "ok"
    veto = level == "critical" and transfer < demand_w
    reason = ("gated transfer from ship" if gate else "battery: " + ", ".join(why)) + (" · CRITICAL: non-essential loads vetoed" if veto else "")
    return PowerDecision(source, round(transfer, 1), presence, gate, level, veto, alarm, reason)
