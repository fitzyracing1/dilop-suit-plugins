"""dilop-sim: run the suit host through a scenario and print what each plugin did."""
from __future__ import annotations

import argparse
import json
import sys

from .plugin_manager import MODES
from .simulator import SCENARIOS, run
from .report import html_report


NOTABLE = {"emergency_stop", "distress", "link_lost", "alert", "force_limit", "cutoff_heating", "cutoff_cooling", "peer_distress", "message"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dilop-sim", description="Simulate the Dilop suit plugin host.")
    ap.add_argument("--scenario", "-s", default="normal", choices=sorted(SCENARIOS))
    ap.add_argument("--mode", "-m", default="full", choices=sorted(MODES))
    ap.add_argument("--ticks", "-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", action="store_true", help="print tick reports as JSON lines")
    ap.add_argument("--html", metavar="FILE", help="also write an HTML dashboard")
    ap.add_argument("--list", action="store_true", help="list scenarios and modes")
    ap.add_argument("--verbose", "-v", action="store_true", help="print allowed commands too")
    a = ap.parse_args(argv)
    if a.list:
        for n, s in sorted(SCENARIOS.items()):
            print(f"{n:<12} {s.description}")
        print("\nmodes: " + ", ".join(f"{k} ({'+'.join(v)})" for k, v in MODES.items()))
        return 0
    reports, m, state = run(a.scenario, a.mode, a.ticks, a.seed)
    if a.json:
        for r in reports:
            print(json.dumps(r.as_dict()))
    else:
        print(f"Dilop · scenario {a.scenario} · mode {a.mode} ({' + '.join(MODES[a.mode])}) · {a.ticks} ticks of 60 s")
        print(f"{'tick':>4} {'source':<8} {'in W':>6} {'load W':>7} {'batt %':>7}  {'active':<32} notes")
        for r in reports:
            notes = r.events + [f"VETO {c} ({c.vetoed_by})" for c in r.vetoed] + [f"deferred {d}" for d in r.deferred]
            notes += [f"{c}" for c in r.allowed if c.action in NOTABLE]
            print(f"{r.tick:>4} {r.power_source:<8} {r.power_in_w:>6.0f} {r.load_w:>7.0f} {r.battery_pct:>7.2f}  {','.join(r.active):<32} {'; '.join(dict.fromkeys(notes))}")
            if a.verbose:
                for c in r.allowed:
                    print(f"{'':>6}→ {c}  {c.reason}")
        if m.quarantined:
            print("quarantined: " + ", ".join(f"{k} ({v})" for k, v in m.quarantined.items()))
        print(f"path walked: {state.path_m:.0f} m · final battery {state.battery_pct:.1f}%")
    if a.html:
        with open(a.html, "w", encoding="utf-8") as f:
            f.write(html_report(a.scenario, a.mode, reports, m))
        print(f"wrote {a.html}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
