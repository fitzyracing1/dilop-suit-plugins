# Dilop architecture

```
Suit Host (computer)
├── Plugin Manager (scan / load / unload / modes / priority / resource arbitration / quarantine)
├── Safety Layer (always loaded, can veto, owns power-source selection)
├── Bus (topics: state, commands, telemetry; a broken subscriber is isolated)
│   ├── Safety Plugin    priority 0
│   ├── Distance Plugin  priority 20
│   ├── Comfort Plugin   priority 40
│   └── Social Plugin    priority 60
└── Output (actuators, displays, comms)
```

## One tick

1. **Scan and mode.** `PluginManager.scan()` finds every `Plugin` subclass in `dilop.plugins`.
   A mode (`work`, `explore`, `social`, `baseline`, `full`) picks which ones run. Safety is in every mode
   and `unload("safety")` raises.
2. **Arbitrate.** Plugins are admitted in priority order against the power, compute and bandwidth budgets.
   Whatever doesn't fit is deferred for that tick. At low battery the social plugin is shed first.
   At critical battery (or after a safety fault) the manager enters the **safe baseline**: only safety and distance run.
3. **Step.** Each plugin reads the shared `SuitState` and returns `Command`s. Exceptions are caught:
   the plugin is quarantined and the suit keeps running. If safety itself throws, that counts as an
   emergency stop and the manager drops to the safe baseline.
4. **Veto.** Safety produces its own commands first. Then other commands go through the veto filter:
   motion and assist commands are blocked during an emergency stop, and all non-essential commands are
   blocked while power is critical.
5. **Apply and publish.** The allowed commands update the actuators. The manager publishes telemetry on the bus,
   and the tick returns a `TickReport`.

## Power logic (inside the safety plugin)

From the chat: *"the nuclear material just uses your presence as a measurement, sending power based on
if there was a reactor powering your suit, but the power's coming from the battery."*

`dilop/power.py::decide_power` encodes that:

| input | meaning |
|---|---|
| `nuclear_reading_usv_h` | dosimeter. ≥ 0.5 µSv/h means a reactor is **present** nearby. It is only a measurement, never a power source |
| `ship_reactor_online`, `ship_link_quality`, `remote_link_m` | whether the ship can actually transfer |
| `battery_pct`, `demand_w` | battery state and suit load |

- presence + reactor online + link ≥ 0.6 + in range → **ship** power, transfer = load + trickle charge,
  capped at 900 W and ramped at 300 W per tick
- otherwise → **battery**
- ≥ 100 µSv/h → radiation alarm (still not a power source)
- battery < 20 % → low (social shed). Below 8 % with the ship not covering the load → **veto** of non-essential loads

## Plugin contract

```python
PluginContract(name, capabilities, Resources(power_w, compute, bandwidth_kbps),
               safety_constraints, priority, can_veto=False)
```

Only the safety plugin has `can_veto=True`. Third-party plugins subclass `dilop.Plugin`, declare a
contract, implement `step(state) -> list[Command]`, then `manager.register(cls)` and `manager.load(name)`.
