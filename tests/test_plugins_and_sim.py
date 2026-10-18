import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from dilop import SuitState
from dilop.plugins import SafetyPlugin, DistancePlugin, ComfortPlugin, SocialPlugin
from dilop.simulator import run, SCENARIOS
from dilop.cli import main


class PluginTests(unittest.TestCase):
    def test_contracts(self):
        for cls in (SafetyPlugin, DistancePlugin, ComfortPlugin, SocialPlugin):
            c = cls.contract
            self.assertTrue(c.capabilities and c.safety_constraints)
            self.assertEqual(c.can_veto, cls is SafetyPlugin)
        self.assertLess(SafetyPlugin.contract.priority, DistancePlugin.contract.priority)

    def test_safety_fall_detection(self):
        p = SafetyPlugin()
        p.step(SuitState(accel_g=0.1))
        cmds = p.step(SuitState(accel_g=3.0))
        self.assertIn("safety:comms.distress=fall detected", [str(c) for c in cmds])
        self.assertTrue(p.estop)

    def test_safety_force_limit_and_thermal(self):
        cmds = [str(c) for c in SafetyPlugin().step(SuitState(joint_force_n=600, core_temp_c=39.5))]
        self.assertIn("safety:actuator.force_limit=400.0", cmds)
        self.assertIn("safety:hvac.cutoff_heating=True", cmds)

    def test_distance(self):
        p = DistancePlugin()
        p.step(SuitState(position_m=(0, 0)))
        s = SuitState(position_m=(3, 4), nearest_obstacle_m=2, remote_link_m=1700, remote_link_range_m=2000, geofence_m=4)
        cmds = [str(c) for c in p.step(s)]
        self.assertEqual(s.path_m, 5.0)
        self.assertIn("distance:display.proximity=2", cmds)
        self.assertIn("distance:comms.boost_link=0.85", cmds)
        self.assertIn("distance:display.geofence=1.0", cmds)

    def test_comfort(self):
        cmds = [str(c) for c in ComfortPlugin().step(SuitState(suit_temp_c=18, pressure_hotspot_kpa=14, fatigue=0.7))]
        self.assertIn("comfort:hvac.heat=80.0", cmds)
        self.assertIn("comfort:bladders.redistribute=14", cmds)
        self.assertIn("comfort:assist.posture_support=0.7", cmds)

    def test_social(self):
        s = SuitState(tick=5, peers=[{"id": "B", "pos": (3, 4), "status": "distress"}], inbox=["wave"])
        cmds = [str(c) for c in SocialPlugin().step(s)]
        self.assertTrue(any(c.startswith("social:comms.presence") for c in cmds))
        self.assertIn("social:display.peer_distress=B", cmds)
        self.assertIn("social:comms.message=Over here", cmds)


class SimulatorTests(unittest.TestCase):
    def test_every_scenario_runs(self):
        for name in SCENARIOS:
            reports, m, state = run(name, "full", 12)
            self.assertEqual(len(reports), 12, name)
            self.assertTrue(all("safety" in r.active for r in reports), name)

    def test_scenarios_show_their_behaviour(self):
        r, m, _ = run("away", "full", 20)
        self.assertEqual(r[0].power_source, "ship")
        self.assertEqual(r[-1].power_source, "battery")
        r, m, _ = run("low-battery", "full", 10)
        self.assertTrue(any(x.baseline for x in r))
        self.assertTrue(any(x.vetoed for x in r))
        r, m, _ = run("obstacle", "work", 8)
        self.assertTrue(any(x.vetoed and "emergency stop" in x.vetoed[0].vetoed_by for x in r))
        r, m, _ = run("crash", "full", 8)
        self.assertIn("gadget", m.quarantined)
        r, m, _ = run("reactor-off", "full", 10)
        self.assertEqual([x.power_source for x in r[5:10]], ["battery"] * 5)

    def test_deterministic(self):
        a = [x.as_dict() for x in run("normal", "full", 10, seed=3)[0]]
        b = [x.as_dict() for x in run("normal", "full", 10, seed=3)[0]]
        self.assertEqual(a, b)

    def test_cli_text_json_html(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["-s", "crash", "-n", "6"]), 0)
        self.assertIn("isolated gadget", out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            main(["-s", "normal", "-n", "3", "--json"])
        self.assertEqual(json.loads(out.getvalue().splitlines()[0])["tick"], 0)
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "r.html")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                main(["-s", "low-battery", "-n", "10", "--html", f])
            html = open(f, encoding="utf-8").read()
            self.assertIn("<svg", html)
            self.assertIn("battery critical", html)


if __name__ == "__main__":
    unittest.main()
