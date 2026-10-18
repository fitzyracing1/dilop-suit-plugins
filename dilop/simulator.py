"""Scenario simulator for the Dilop suit host. Deterministic for a given seed."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List

from .plugin import Plugin, PluginContract, Resources
from .plugin_manager import PluginManager, TickReport
from .state import Command, SuitState

DT_S = 60.0  # one tick = one simulated minute


@dataclass
class Scenario:
    name: str
    description: str
    setup: Callable[[SuitState], None]
    world: Callable[[SuitState, int, random.Random], None]
    inject: Callable[[PluginManager, int], None] = lambda m, t: None


def _walk(s: SuitState, t: int, rng: random.Random, speed_mps: float = 1.0, heading: float = 0.6) -> None:
    x, y = s.position_m
    s.position_m = (x + speed_mps * DT_S * math.cos(heading) * 0.1, y + speed_mps * DT_S * math.sin(heading) * 0.1)
    s.nearest_obstacle_m = max(0.2, 6 + 4 * math.sin(t / 3) + rng.uniform(-0.5, 0.5))
    s.closing_speed_mps = max(0.0, rng.uniform(-0.2, 0.6))
    s.suit_temp_c += rng.uniform(-0.4, 0.5)
    s.fatigue = min(1.0, s.fatigue + 0.02)
    s.pressure_hotspot_kpa = 8 + 6 * abs(math.sin(t / 5))


def _ship_distance(s: SuitState, ship=(0.0, 0.0)) -> None:
    s.remote_link_m = math.dist(s.position_m, ship)
    # dosimeter: the reactor field falls off with distance (presence measurement only)
    s.nuclear_reading_usv_h = round(0.15 + 40.0 / (1 + (s.remote_link_m / 30.0) ** 2), 3)
    s.ship_link_quality = max(0.0, min(1.0, 1.1 - s.remote_link_m / s.remote_link_range_m))


def _normal_setup(s): s.battery_pct = 80
def _normal_world(s, t, rng): _walk(s, t, rng, 0.6); _ship_distance(s)


def _away_setup(s): s.battery_pct = 70; s.remote_link_range_m = 600
def _away_world(s, t, rng): _walk(s, t, rng, 4.0, 0.2); _ship_distance(s)


def _low_setup(s): s.battery_pct = 9.5; s.position_m = (900.0, 0.0); s.remote_link_range_m = 600
def _low_world(s, t, rng): _walk(s, t, rng, 0.3, 0.0); _ship_distance(s)


def _obstacle_setup(s): s.battery_pct = 80; s.fatigue = 0.5


def _obstacle_world(s, t, rng):
    _normal_world(s, t, rng)
    if 4 <= t <= 6:
        s.nearest_obstacle_m, s.closing_speed_mps = 1.2, 1.4


def _fall_world(s, t, rng):
    _normal_world(s, t, rng)
    s.accel_g = 0.1 if t == 5 else 3.4 if t == 6 else 1.0


def _reactor_world(s, t, rng):
    _normal_world(s, t, rng)
    s.ship_reactor_online = not (5 <= t <= 9)


def _hot_world(s, t, rng):
    _normal_world(s, t, rng)
    s.core_temp_c = 37.0 + 0.35 * t
    s.suit_temp_c = 18.0


class FaultyGadget(Plugin):
    """A third-party plugin that crashes, to show isolation."""
    contract = PluginContract("gadget", ["demo"], Resources(power_w=10, compute=0.05), priority=70)

    def step(self, s: SuitState) -> List[Command]:
        if s.tick >= 4:
            raise RuntimeError("gadget firmware panic")
        return [Command("gadget", "display", "hello", s.tick)]


def _crash_inject(m: PluginManager, t: int) -> None:
    if t == 1:
        m.register(FaultyGadget)
        m.load("gadget")


SCENARIOS: Dict[str, Scenario] = {s.name: s for s in [
    Scenario("normal", "Walking near the ship: reactor presence measured, gated ship power.", _normal_setup, _normal_world),
    Scenario("away", "Walking away from the ship until the link drops: falls back to battery.", _away_setup, _away_world),
    Scenario("low-battery", "Far from the ship on 9.5% battery: social shed at low, then critical: non-essential loads vetoed.", _low_setup, _low_world),
    Scenario("obstacle", "An obstacle closes fast at ticks 4-6: emergency stop, motion assist vetoed.", _obstacle_setup, _obstacle_world),
    Scenario("fall", "Free-fall then impact at tick 5-6: fall detected, distress call.", _normal_setup, _fall_world),
    Scenario("reactor-off", "Ship reactor offline for ticks 5-9: presence still measured, but no transfer.", _normal_setup, _reactor_world),
    Scenario("overheat", "Core temperature climbs: comfort switches to cooling, safety cuts off heating at 39 °C.", _normal_setup, _hot_world),
    Scenario("crash", "A third-party plugin panics at tick 4: isolated, the suit keeps running.", _normal_setup, _normal_world, _crash_inject),
]}


def run(scenario: str = "normal", mode: str = "full", ticks: int = 20, seed: int = 7,
        peers: bool = True) -> tuple[List[TickReport], PluginManager, SuitState]:
    sc = SCENARIOS[scenario]
    rng = random.Random(seed)
    m = PluginManager()
    m.scan()
    state = SuitState()
    sc.setup(state)
    m.set_mode(mode, state)
    if peers:
        state.peers = [{"id": "suit-B", "pos": (20.0, 5.0), "status": "ok"}, {"id": "suit-C", "pos": (-30.0, 12.0), "status": "ok"}]
    reports = []
    for t in range(ticks):
        state.tick = t
        sc.inject(m, t)
        sc.world(state, t, rng)
        if t == 3:
            state.inbox.append("thumbs_up")
        if scenario == "normal" and t == 12 and peers:
            state.peers[1]["status"] = "distress"
        r = m.tick(state)
        # energy balance over the tick
        net_w = state.power_in_w - state.load_w
        state.battery_pct = max(0.0, min(100.0, state.battery_pct + net_w * DT_S / 3600 / state.battery_capacity_wh * 100))
        r.battery_pct = state.battery_pct
        reports.append(r)
    return reports, m, state
