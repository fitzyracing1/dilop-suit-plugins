import unittest

from dilop.power import decide_power, PRESENCE_USV_H, CRITICAL_BATTERY_PCT

BASE = dict(nuclear_reading_usv_h=5.0, ship_reactor_online=True, ship_link_quality=1.0,
            remote_link_m=50, remote_link_range_m=2000, battery_pct=80, demand_w=300, previous_transfer_w=1000)


class PowerTests(unittest.TestCase):
    def test_presence_and_ship_gives_gated_transfer(self):
        d = decide_power(**BASE)
        self.assertTrue(d.presence and d.gate_open)
        self.assertEqual(d.source, "ship")
        self.assertEqual(d.transfer_w, 450.0)  # load + trickle charge
        self.assertFalse(d.veto)

    def test_nuclear_reading_is_presence_only_never_a_source(self):
        d = decide_power(**{**BASE, "ship_reactor_online": False, "nuclear_reading_usv_h": 500})
        self.assertTrue(d.presence)
        self.assertEqual(d.source, "battery")
        self.assertEqual(d.transfer_w, 0)
        self.assertTrue(d.radiation_alarm)

    def test_no_presence_means_battery(self):
        d = decide_power(**{**BASE, "nuclear_reading_usv_h": PRESENCE_USV_H / 2})
        self.assertEqual((d.source, d.gate_open), ("battery", False))
        self.assertIn("no reactor presence", d.reason)

    def test_gate_checks_link_and_range(self):
        self.assertFalse(decide_power(**{**BASE, "ship_link_quality": 0.3}).gate_open)
        self.assertFalse(decide_power(**{**BASE, "remote_link_m": 2500}).gate_open)

    def test_ramp_limit(self):
        d = decide_power(**{**BASE, "previous_transfer_w": 0})
        self.assertEqual(d.transfer_w, 300.0)

    def test_critical_battery_without_ship_vetoes(self):
        d = decide_power(**{**BASE, "battery_pct": CRITICAL_BATTERY_PCT - 1, "remote_link_m": 5000})
        self.assertEqual(d.level, "critical")
        self.assertTrue(d.veto)
        ok = decide_power(**{**BASE, "battery_pct": CRITICAL_BATTERY_PCT - 1})
        self.assertFalse(ok.veto, "ship power covers the load, so no veto")


if __name__ == "__main__":
    unittest.main()
