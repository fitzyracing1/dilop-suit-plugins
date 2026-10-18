"""Static HTML dashboard for a simulation run (inline SVG, no dependencies)."""
from __future__ import annotations

import html
from typing import List

from .plugin_manager import MODES, PluginManager, TickReport
from .simulator import SCENARIOS


def _line(values, w, h, vmax, color, vmin=0.0):
    if not values:
        return ""
    n = max(1, len(values) - 1)
    pts = " ".join(f"{i * w / n:.1f},{h - (v - vmin) / (vmax - vmin or 1) * h:.1f}" for i, v in enumerate(values))
    return f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{pts}"/>'


def html_report(scenario: str, mode: str, reports: List[TickReport], m: PluginManager) -> str:
    W, H = 860, 170
    batt = [r.battery_pct for r in reports]
    pin = [r.power_in_w for r in reports]
    load = [r.load_w for r in reports]
    pmax = max([1.0] + pin + load) * 1.1
    n = max(1, len(reports) - 1)
    bands = "".join(f'<rect x="{i * W / n - W / n / 2:.1f}" y="0" width="{W / n:.1f}" height="{H}" fill="{"#2dd4bf22" if r.power_source == "ship" else "#f59e0b18"}"/>' for i, r in enumerate(reports))
    marks = "".join(f'<circle cx="{i * W / n:.1f}" cy="12" r="6" fill="#ef4444"><title>{html.escape("; ".join(r.events + [str(c) for c in r.vetoed]))}</title></circle>' for i, r in enumerate(reports) if r.vetoed or r.events)
    rows = "".join(
        f"<tr><td>{r.tick}</td><td class='{r.power_source}'>{r.power_source}</td><td>{r.power_in_w:.0f}</td><td>{r.load_w:.0f}</td><td>{r.battery_pct:.2f}</td>"
        f"<td>{html.escape(', '.join(r.active))}</td><td>{html.escape('; '.join(dict.fromkeys(r.events + [f'VETO {c} — {c.vetoed_by}' for c in r.vetoed] + [f'deferred {d}' for d in r.deferred])))}</td></tr>"
        for r in reports)
    plugins = "".join(
        f"<div class='plug{' q' if name in m.quarantined else ''}'><b>{html.escape(name)}</b><span>priority {cls.contract.priority} · {cls.contract.resources.power_w:.0f} W · "
        f"{'veto · ' if cls.contract.can_veto else ''}{'essential' if cls.contract.essential else 'sheddable'}</span>"
        f"<small>{html.escape(', '.join(cls.contract.capabilities))}</small>{f'<em>isolated: {html.escape(m.quarantined[name])}</em>' if name in m.quarantined else ''}</div>"
        for name, cls in sorted(m.registry.items(), key=lambda kv: kv[1].contract.priority))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Dilop · {html.escape(scenario)}</title>
<style>body{{margin:0;background:#0a0f14;color:#e6edf3;font:14px/1.5 ui-sans-serif,system-ui,sans-serif}}.wrap{{max-width:960px;margin:0 auto;padding:24px}}
h1{{margin:0;font-size:26px;letter-spacing:1px}}.sub{{color:#8b98a5}}.card{{background:#111821;border:1px solid #1f2a36;border-radius:14px;padding:16px;margin-top:16px}}
h2{{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:2px;color:#8b98a5}}svg{{width:100%;height:auto;display:block}}
.legend span{{margin-right:16px;font-size:12px;color:#8b98a5}}.legend i{{display:inline-block;width:12px;height:3px;margin-right:6px;vertical-align:middle}}
.plugs{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.plug{{border:1px solid #1f2a36;border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:3px}}.plug span{{color:#2dd4bf;font-size:12px}}.plug small{{color:#8b98a5;font-size:11px}}.plug.q{{border-color:#ef4444}}.plug em{{color:#ef4444;font-size:11px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}td,th{{padding:5px 6px;border-bottom:1px solid #1f2a36;text-align:left;vertical-align:top}}th{{color:#8b98a5;font-weight:600}}td.ship{{color:#2dd4bf}}td.battery{{color:#f59e0b}}</style></head>
<body><div class="wrap"><h1>DILOP · suit plugin host</h1><div class="sub">Scenario <b>{html.escape(scenario)}</b>: {html.escape(SCENARIOS[scenario].description)} · mode <b>{html.escape(mode)}</b> ({' + '.join(MODES[mode])})</div>
<div class="card"><h2>Plugins</h2><div class="plugs">{plugins}</div></div>
<div class="card"><h2>Power · ship (teal band) vs battery (amber band)</h2><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none">{bands}{_line(pin, W, H, pmax, '#2dd4bf')}{_line(load, W, H, pmax, '#e6edf3')}{marks}</svg>
<div class="legend"><span><i style="background:#2dd4bf"></i>ship transfer W</span><span><i style="background:#e6edf3"></i>load W</span><span><i style="background:#ef4444;height:8px;border-radius:50%;width:8px"></i>veto / event</span></div></div>
<div class="card"><h2>Battery %</h2><svg viewBox="0 0 {W} 90" preserveAspectRatio="none">{_line(batt, W, 90, max(batt + [1]) + 2, '#a78bfa', max(0.0, min(batt + [0]) - 2))}</svg></div>
<div class="card"><h2>Tick log</h2><table><tr><th>tick</th><th>source</th><th>in W</th><th>load W</th><th>batt %</th><th>active</th><th>events · vetoes</th></tr>{rows}</table></div>
</div></body></html>"""
