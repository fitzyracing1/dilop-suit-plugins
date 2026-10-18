import unittest

from dilop import PluginManager, SuitState, Command, Plugin, PluginContract, Resources, MODES
from dilop.plugin_manager import default_manager


class Boom(Plugin):
    contract = PluginContract("boom", ["demo"], Resources(power_w=5, compute=0.01), priority=80)

    def step(self, s):
        raise ValueError("bad firmware")


class Hog(Plugin):
    contract = PluginContract("hog", ["demo"], Resources(power_w=5, compute=0.9), priority=90)

    def step(self, s):
        return [Command("hog", "display", "hi")]


class Mover(Plugin):
    contract = PluginContract("mover", ["motion"], Resources(power_w=5, compute=0.01), priority=30)

    def step(self, s):
        return [Command("mover", "motion", "walk", 1.0)]


class ManagerTests(unittest.TestCase):
    def test_scan_finds_builtin_plugins(self):
        m = PluginManager()
        self.assertEqual(m.scan(), ["comfort", "distance", "safety", "social"])

    def test_modes_and_priority_order(self):
        m = default_manager("work")
        self.assertEqual(m.active(), ["safety", "distance", "comfort"])
        m.set_mode("explore")
        self.assertEqual(m.active(), ["safety", "distance", "social"])
        for mode, names in MODES.items():
            self.assertEqual(names[0], "safety", mode)

    def test_safety_cannot_be_unloaded(self):
        m = default_manager()
        with self.assertRaises(RuntimeError):
            m.unload("safety")

    def test_crashing_plugin_is_isolated(self):
        m = default_manager("work")
        m.register(Boom); m.load("boom")
        s = SuitState()
        r = m.tick(s)
        self.assertIn("boom", m.quarantined)
        self.assertNotIn("boom", m.active())
        self.assertTrue(any("isolated boom" in e for e in r.events))
        m.tick(s)  # keeps running
        with self.assertRaises(RuntimeError):
            m.load("boom")

    def test_resource_arbitration_defers_what_does_not_fit(self):
        m = default_manager("full")
        m.register(Hog); m.load("hog")
        r = m.tick(SuitState())
        self.assertIn("hog (resources)", r.deferred)
        self.assertNotIn("hog", r.active)

    def test_safety_vetoes_motion_during_emergency_stop(self):
        m = default_manager("work")
        m.register(Mover); m.load("mover")
        s = SuitState(nearest_obstacle_m=0.3)
        r = m.tick(s)
        self.assertTrue(s.emergency_stop)
        self.assertEqual([str(c) for c in r.vetoed], ["mover:motion.walk=1.0"])
        s.nearest_obstacle_m = 8.0
        r = m.tick(s)
        self.assertFalse(s.emergency_stop)
        self.assertEqual(r.vetoed, [])

    def test_critical_battery_enters_safe_baseline(self):
        m = default_manager("full")
        s = SuitState(battery_pct=5, remote_link_m=9000, nuclear_reading_usv_h=0.1, load_w=300)
        r1 = m.tick(s)
        self.assertTrue(r1.baseline)
        self.assertTrue(all(c.essential for c in r1.allowed))
        r2 = m.tick(s)
        self.assertEqual(r2.active, ["safety", "distance"])

    def test_ship_power_selected_near_reactor(self):
        m = default_manager("work")
        s = SuitState(nuclear_reading_usv_h=10, remote_link_m=20, load_w=280)
        m.tick(s)
        self.assertEqual(s.power_source, "ship")
        self.assertGreater(s.power_in_w, 0)

    def test_bus_carries_telemetry(self):
        m = default_manager("work")
        seen = []
        m.bus.subscribe("telemetry", lambda t, p: seen.append(p["tick"]))
        m.bus.subscribe("telemetry", lambda t, p: 1 / 0)  # a broken subscriber is isolated
        m.tick(SuitState(tick=3))
        self.assertEqual(seen, [3])
        self.assertTrue(m.bus.errors)


if __name__ == "__main__":
    unittest.main()
