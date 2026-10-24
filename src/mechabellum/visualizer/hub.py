"""The Visualizer's current state, and its fan-out to SSE clients with a catch-up on connect."""

from __future__ import annotations

import json
import queue
import threading
from collections import Counter
from collections.abc import Iterable
from typing import Any

from .baseline import compute_baseline

# Share of summaries a player id must appear in to be suggested as the Local Player.
SUGGESTION_SHARE = 0.6
CLOSED = None


def encode_event(name: str, data: Any) -> bytes:
    """One SSE event: `event: <name>` and a single `data:` line of compact JSON."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {payload}\n\n".encode()


def suggest_player_id(summaries: Iterable[dict[str, Any]]) -> str | None:
    """The player id in the most summaries, when it is in at least 60% of them."""
    rows = list(summaries)
    counts = Counter(
        player_id for row in rows for player_id in {player.get("playerId") for player in row["players"]} if player_id
    )
    if not counts:
        return None
    player_id, count = counts.most_common(1)[0]
    return player_id if count >= SUGGESTION_SHARE * len(rows) else None


class Hub:
    """Holds what a newly connected browser needs and pushes every change to the connected ones.

    Every mutation and every subscription takes the same lock, so a new client's catch-up and the incremental
    events after it never overlap or miss each other.
    """

    def __init__(
        self,
        *,
        server_version: str,
        model_available: bool,
        replay_dir: str | None,
        live_source: str,
        local_player_id: str | None,
    ) -> None:
        self._lock = threading.Lock()
        self._clients: set[queue.Queue[bytes | None]] = set()
        self._server_version = server_version
        self._model_available = model_available
        self._replay_dir = replay_dir
        self._live_source = live_source
        self._local_player_id = local_player_id
        self._summaries: dict[str, dict[str, Any]] = {}
        self._suggested: str | None = None
        self._baseline: dict[str, Any] = compute_baseline([])
        self._ratings: dict[str, dict[str, int]] = {}
        self._status: dict[str, Any] = {
            "state": "off" if live_source == "none" else "waiting",
            "detail": None,
            "gameVersion": None,
            "bridge": "absent",
        }
        self._frame: dict[str, Any] | None = None
        # The current battle's first fight_over frame per round, replayed in the catch-up to rebuild round charts.
        self._round_frames: dict[int, dict[str, Any]] = {}
        self._round_battle: str | None = None
        self._predictions: dict[str, Any] = {"battleId": None, "rows": []}

    # ---- reading ---------------------------------------------------------------------------------------------

    @property
    def local_player_id(self) -> str | None:
        return self._local_player_id

    @property
    def suggested_player_id(self) -> str | None:
        return self._suggested

    @property
    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._sorted_summaries()

    def catch_up(self) -> list[tuple[str, Any]]:
        with self._lock:
            return self._catch_up()

    # ---- clients ---------------------------------------------------------------------------------------------

    def subscribe(self) -> queue.Queue[bytes | None]:
        """A new client queue, preloaded with the catch-up; None in the queue means the server is closing."""
        client: queue.Queue[bytes | None] = queue.Queue()
        with self._lock:
            for name, data in self._catch_up():
                client.put(encode_event(name, data))
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue[bytes | None]) -> None:
        with self._lock:
            self._clients.discard(client)

    def close(self) -> None:
        with self._lock:
            for client in self._clients:
                client.put(CLOSED)
            self._clients.clear()

    # ---- writing ---------------------------------------------------------------------------------------------

    def set_summaries(self, rows: Iterable[dict[str, Any]]) -> None:
        with self._lock:
            self._summaries = {}
            for row in rows:
                self._summaries.setdefault(_summary_key(row), row)
            self._summaries_changed()
            self._send("summaries", {"rows": self._sorted_summaries()})
            self._send("baseline", self._baseline)

    def upsert_summary(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._summaries[_summary_key(row)] = row
            self._summaries_changed()
            self._send("summary", {"row": row})
            self._send("baseline", self._baseline)

    def set_ratings(self, ratings: dict[str, dict[str, int]]) -> None:
        with self._lock:
            self._ratings = {battle: dict(players) for battle, players in ratings.items()}
            self._send("ratings", {"byBattle": self._ratings})

    def add_rating(self, battle_id: str, player_id: str, rating: int) -> None:
        with self._lock:
            self._ratings.setdefault(battle_id, {})[player_id] = rating
            self._send("rating", {"battleId": battle_id, "playerId": player_id, "rating": rating})

    def update_status(self, **changes: Any) -> None:
        """Merge `changes` (state, detail, gameVersion, bridge) and send `status` when anything differs."""
        with self._lock:
            updated = {**self._status, **changes}
            if updated != self._status:
                self._status = updated
                self._send("status", dict(updated))

    def set_frame(self, frame: dict[str, Any]) -> None:
        with self._lock:
            self._frame = frame
            match = frame.get("snapshot", {}).get("match", {})
            if match.get("battleId") != self._round_battle:
                self._round_battle = match.get("battleId")
                self._round_frames = {}
            if match.get("phase") == "fight_over" and isinstance(match.get("round"), int):
                self._round_frames.setdefault(match["round"], frame)
            self._send("frame", frame)

    def set_predictions(self, battle_id: str | None, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            self._predictions = {"battleId": battle_id, "rows": list(rows)}
            self._send("predictions", self._predictions)

    def add_prediction(self, battle_id: str | None, row: dict[str, Any]) -> None:
        with self._lock:
            if self._predictions["battleId"] != battle_id:
                self._predictions = {"battleId": battle_id, "rows": []}
            self._predictions["rows"].append(row)
            self._send("prediction", {"battleId": battle_id, **row})

    def set_model_available(self, available: bool) -> None:
        """Correct `modelAvailable`; every client gets a fresh catch-up, since only `hello` carries it."""
        with self._lock:
            if available == self._model_available:
                return
            self._model_available = available
            for name, data in self._catch_up():
                self._send(name, data)

    def set_local_player(self, player_id: str | None) -> None:
        with self._lock:
            self._local_player_id = player_id
            self._send("config", {"localPlayerId": player_id})

    # ---- internals (lock held) -------------------------------------------------------------------------------

    def _catch_up(self) -> list[tuple[str, Any]]:
        events: list[tuple[str, Any]] = [
            (
                "hello",
                {
                    "serverVersion": self._server_version,
                    "localPlayerId": self._local_player_id,
                    "suggestedPlayerId": self._suggested,
                    "modelAvailable": self._model_available,
                    "replayDir": self._replay_dir,
                    "liveSource": self._live_source,
                },
            ),
            ("summaries", {"rows": self._sorted_summaries()}),
            ("baseline", self._baseline),
            ("ratings", {"byBattle": self._ratings}),
            ("status", dict(self._status)),
        ]
        if self._frame is not None:
            # Round history first (oldest round first), then the latest frame.
            events.extend(("frame", self._round_frames[number]) for number in sorted(self._round_frames))
            events.append(("frame", self._frame))
            events.append(("predictions", self._predictions))
        return events

    def _summaries_changed(self) -> None:
        self._baseline = compute_baseline(self._summaries.values())
        self._suggested = suggest_player_id(self._summaries.values())

    def _sorted_summaries(self) -> list[dict[str, Any]]:
        return sorted(self._summaries.values(), key=lambda row: (row.get("battleId") or "", row["replayPath"]))

    def _send(self, name: str, data: Any) -> None:
        message = encode_event(name, data)
        for client in self._clients:
            client.put(message)


def _summary_key(row: dict[str, Any]) -> str:
    return row.get("battleId") or row["replayPath"]
