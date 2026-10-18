"""Social networking plugin (operational): presence broadcast, shared awareness,
gesture-to-message, multi-suit coordination."""
from __future__ import annotations

import math
from typing import List

from ..plugin import Plugin, PluginContract, Resources, PRIORITY_SOCIAL
from ..state import Command, SuitState


class SocialPlugin(Plugin):
    contract = PluginContract(
        name="social",
        capabilities=["presence_broadcast", "shared_awareness", "gesture_to_message", "multi_suit_coordination"],
        resources=Resources(power_w=40, compute=0.1, bandwidth_kbps=64),
        safety_constraints=["operational messages only", "first to be shed on low power"],
        priority=PRIORITY_SOCIAL)

    BROADCAST_EVERY = 5

    def step(self, s: SuitState) -> List[Command]:
        out: List[Command] = []
        if s.tick % self.BROADCAST_EVERY == 0:
            out.append(Command("social", "comms", "presence", {"status": s.status, "pos": [round(v, 1) for v in s.position_m]}))
        if s.peers:
            near = min(s.peers, key=lambda p: math.dist(p.get("pos", (0, 0)), s.position_m))
            out.append(Command("social", "display", "nearest_peer", {"id": near.get("id"), "m": round(math.dist(near.get("pos", (0, 0)), s.position_m), 1)}))
            for p in s.peers:
                if p.get("status") == "distress":
                    out.append(Command("social", "display", "peer_distress", p.get("id"), essential=True, reason="multi-suit coordination"))
        while s.inbox:
            gesture = s.inbox.pop(0)
            msg = {"thumbs_up": "All good", "wave": "Over here", "fist": "Hold position", "point": "Go that way"}.get(gesture, gesture)
            out.append(Command("social", "comms", "message", msg, reason=f"gesture {gesture}"))
        return out
