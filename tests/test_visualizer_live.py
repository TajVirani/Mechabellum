from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from mechabellum.collector.memory import ObserverStateError
from mechabellum.collector.unit_catalog import card_name
from mechabellum.contracts import MatchSnapshot
from mechabellum.visualizer.cache import SummaryCache
from mechabellum.visualizer.hub import Hub
from mechabellum.visualizer.live import LiveProcessor, model_looks_available, run_memory, run_playback

PLAYBACK = Path(__file__).parent / "fixtures" / "live" / "playing-match.sample.jsonl"
LOCAL_PLAYER = "281474976710829150"
BATTLE = "20261024--67159493"


def make_hub(local_player_id: str | None = LOCAL_PLAYER) -> Hub:
    return Hub(
        server_version="test",
        model_available=True,
        replay_dir=None,
        live_source="playback",
        local_player_id=local_player_id,
    )


def events(client) -> list[tuple[str, dict]]:
    out = []
    while not client.empty():
        lines = client.get_nowait().decode("utf-8").split("\n")
        out.append((lines[0][len("event: ") :], json.loads(lines[1][len("data: ") :])))
    return out


class FakePredictor:
    def __init__(self) -> None:
        self.calls: list[MatchSnapshot] = []

    def __call__(self, snapshot: MatchSnapshot) -> list[float]:
        self.calls.append(snapshot)
        left = 0.5 + 0.01 * snapshot.match.round
        return [left, 1 - left]


def frames() -> list[MatchSnapshot]:
    return [MatchSnapshot.model_validate_json(line) for line in PLAYBACK.read_text(encoding="utf-8").splitlines()]


def test_playback_at_speed_zero_never_waits(tmp_path: Path) -> None:
    hub = make_hub()
    client = hub.subscribe()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"), FakePredictor())
    waits: list[float] = []

    count = run_playback(processor, hub, PLAYBACK, threading.Event(), speed=0, wait=waits.append)

    assert count == len(frames()) == 45
    assert waits == []
    assert hub.status["state"] == "playback_done"
    received = events(client)
    assert sum(name == "frame" for name, _ in received) == 45
    # The final state stays current.
    last_frame = dict(hub.catch_up())["frame"]
    assert last_frame["snapshot"]["match"]["round"] == 10
    assert last_frame["snapshot"]["match"]["phase"] == "fight_over"


def test_playback_paces_by_capture_time_over_speed(tmp_path: Path) -> None:
    hub = make_hub()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"))
    waits: list[float] = []
    run_playback(processor, hub, PLAYBACK, threading.Event(), speed=2.0, wait=waits.append)

    captured = [frame.source.captured_at_utc for frame in frames()]
    expected = [(later - earlier).total_seconds() / 2 for earlier, later in zip(captured, captured[1:], strict=False)]
    assert waits == pytest.approx([delay for delay in expected if delay > 0])


def test_predictions_fire_once_per_round_with_swing(tmp_path: Path) -> None:
    hub = make_hub()
    predictor = FakePredictor()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"), predictor)
    client = hub.subscribe()
    for frame in frames():
        processor.process(frame)
        processor.process(frame)  # a repeat is deduplicated

    rounds = [call.match.round for call in predictor.calls]
    assert rounds == list(range(1, 11))
    # Each prediction saw the FightOverHistory-filled histories, as live-predict does.
    assert predictor.calls[2].players[0].reactor_core_history is not None
    assert len(predictor.calls[2].players[0].reactor_core_history) == 3
    received = events(client)
    predictions = [data for name, data in received if name == "prediction"]
    assert [row["round"] for row in predictions] == rounds
    assert predictions[0]["swing"] == 0.0
    assert predictions[1]["swing"] == pytest.approx(0.01)
    assert predictions[0]["leftWinProbability"] == pytest.approx(0.51)
    assert all(row["battleId"] == BATTLE for row in predictions)
    assert sum(name == "frame" for name, _ in received) == 45
    final = dict(hub.catch_up())["predictions"]
    assert final["battleId"] == BATTLE and len(final["rows"]) == 10


def test_ratings_are_captured_once_per_battle_and_player(tmp_path: Path) -> None:
    hub = make_hub()
    cache = SummaryCache(tmp_path / "v.sqlite")
    processor = LiveProcessor(hub, cache)
    client = hub.subscribe()
    for frame in frames():
        processor.process(frame)
    ratings = [data for name, data in events(client) if name == "rating"]
    assert ratings == [
        {"battleId": BATTLE, "playerId": LOCAL_PLAYER, "rating": 1651},
        {"battleId": BATTLE, "playerId": "281474976710828382", "rating": 1179},
    ]
    assert cache.ratings() == {BATTLE: {LOCAL_PLAYER: 1651, "281474976710828382": 1179}}


def test_frame_marks_the_opponent_board_while_deploying(tmp_path: Path) -> None:
    hub = make_hub()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"))
    deploying = next(frame for frame in frames() if frame.match.phase == "deploying" and frame.match.round == 2)
    processor.process(deploying)
    frame = dict(hub.catch_up())["frame"]
    assert frame["localIndex"] == 0
    assert frame["boardAsOfLastFight"] == [False, True]
    assert len(frame["composition"]) == 2
    assert sum(frame["composition"][0]["roles"].values()) == pytest.approx(1.0)
    assert frame["snapshot"]["match"]["battleId"] == BATTLE
    offer = frame["snapshot"]["match"]["reinforcementOffer"]
    assert offer and frame["offerNames"] == [card_name(card_id) for card_id in offer]
    assert not any(name.startswith("Unknown card") for name in frame["offerNames"])


def test_spectating_uses_player_zero_and_no_board_marks(tmp_path: Path) -> None:
    hub = make_hub(local_player_id="someone-else")
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"), FakePredictor())
    for frame in frames():
        processor.process(frame)
    frame = dict(hub.catch_up())["frame"]
    assert frame["localIndex"] is None
    assert frame["boardAsOfLastFight"] == [False, False]


def test_suggested_player_counts_as_local_without_being_saved(tmp_path: Path) -> None:
    hub = make_hub(local_player_id=None)
    hub.set_summaries(
        [{"battleId": "b", "replayPath": "b", "players": [{"playerId": LOCAL_PLAYER, "won": True, "composition": []}]}]
    )
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"))
    processor.process(frames()[0])
    assert dict(hub.catch_up())["frame"]["localIndex"] == 0
    assert hub.local_player_id is None


def test_changing_the_local_player_flips_the_prediction_side(tmp_path: Path) -> None:
    hub = make_hub()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"), FakePredictor())
    for frame in frames():
        processor.process(frame)
    hub.set_local_player("281474976710828382")
    processor.refresh_local_player()
    state = dict(hub.catch_up())
    assert state["frame"]["localIndex"] == 1
    assert state["predictions"]["rows"][0]["leftWinProbability"] == pytest.approx(0.49)


class FlakySource:
    """Fails like the game does between rounds, then returns frames."""

    def __init__(self, stop: threading.Event, script: list[object]) -> None:
        self.stop = stop
        self.script = script
        self.closed = False

    def read_snapshot(self) -> MatchSnapshot:
        if not self.script:
            self.stop.set()
            raise ObserverStateError("No match is currently running.")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


def test_memory_loop_survives_read_errors_and_missing_game(tmp_path: Path) -> None:
    hub = make_hub()
    client = hub.subscribe()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"))
    stop = threading.Event()
    snapshots = frames()
    source = FlakySource(
        stop,
        [
            ObserverStateError("The match has not finished initializing player data."),
            OSError("ReadProcessMemory failed"),
            ValueError("bad pointer"),
            snapshots[0],
            snapshots[1],
        ],
    )
    attempts: list[int] = []

    def attach() -> FlakySource:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("Mechabellum is not running.")
        return source

    run_memory(processor, hub, stop, attach=attach, interval_seconds=0, attach_retry_seconds=0)

    states = [data["state"] for name, data in events(client) if name == "status"]
    # Catch-up, attach failure, attached, still loading, two failed reads, two frames, match gone.
    assert states == ["waiting", "no_game", "waiting", "waiting", "retrying", "retrying", "live", "waiting"]
    assert len(attempts) == 2
    assert dict(hub.catch_up())["frame"]["snapshot"]["match"]["round"] == snapshots[1].match.round
    assert source.closed


def test_unsupported_game_build_reports_layout_mismatch(tmp_path: Path) -> None:
    hub = make_hub()
    stop = threading.Event()

    def attach() -> None:
        stop.set()
        raise RuntimeError("GameAssembly.dll build is not supported (SHA256=ABC).")

    run_memory(LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite")), hub, stop, attach=attach)
    assert hub.status["state"] == "layout_mismatch"


def test_model_guess(tmp_path: Path) -> None:
    assert model_looks_available(tmp_path / "missing.joblib") is False


def test_a_frame_without_a_battle_id_does_not_reset_the_match(tmp_path: Path) -> None:
    hub = make_hub()
    processor = LiveProcessor(hub, SummaryCache(tmp_path / "v.sqlite"), FakePredictor())
    played = frames()
    for frame in played[:-1]:
        processor.process(frame)
    before = dict(hub.catch_up())["predictions"]
    assert before["battleId"] == BATTLE and before["rows"]
    anonymous = played[-1].model_copy(update={"match": played[-1].match.model_copy(update={"battle_id": None})})
    processor.process(anonymous)
    after = dict(hub.catch_up())
    assert after["predictions"] == before
    round_frames = [data for name, data in hub.catch_up() if name == "frame"]
    # The round history survives: rounds 1-10 plus the latest frame.
    assert len(round_frames) == 11
