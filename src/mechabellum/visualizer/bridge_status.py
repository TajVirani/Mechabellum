"""Optional MechaBridge probe: game version and online state, through `StatusRequest` only.

Never sends any other request: fetches and downloads make the game contact its servers, which the Visualizer must
not do. Without the `bridge` extra, or when the mod doesn't answer, the bridge is simply "absent".
"""

from __future__ import annotations

from dataclasses import dataclass

CONNECT_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class BridgeStatus:
    state: str  # "online" | "offline" | "absent"
    game_version: str | None = None


ABSENT = BridgeStatus("absent")


def probe_bridge(port: int | None = None) -> BridgeStatus:
    try:
        from ..bridge import DEFAULT_PORT, BridgeClient
    except ImportError:
        return ABSENT
    try:
        with BridgeClient.connect(port or DEFAULT_PORT, timeout=CONNECT_TIMEOUT_SECONDS) as client:
            reply = client.status()
    except Exception:
        return ABSENT
    return BridgeStatus("online" if reply.online else "offline", reply.game_version or None)
