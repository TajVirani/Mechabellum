from __future__ import annotations

import json

from mechabellum.visualizer.hub import CLIENT_QUEUE_LIMIT, CLOSED, Hub, encode_event, suggest_player_id

CATCH_UP = ["hello", "summaries", "baseline", "ratings", "status"]


def hub(**overrides: object) -> Hub:
    options = {
        "server_version": "test",
        "model_available": False,
        "replay_dir": "Replay",
        "live_source": "playback",
        "local_player_id": None,
    }
    options.update(overrides)
    return Hub(**options)  # type: ignore[arg-type]


def summary(battle_id: str, *player_ids: str) -> dict:
    return {
        "battleId": battle_id,
        "replayPath": f"{battle_id}.grbr",
        "players": [
            {"playerId": player_id, "won": index == 0, "composition": []} for index, player_id in enumerate(player_ids)
        ],
    }


def decode(message: bytes) -> tuple[str, object]:
    text = message.decode("utf-8")
    assert text.endswith("\n\n")
    lines = text[:-2].split("\n")
    assert len(lines) == 2 and lines[0].startswith("event: ") and lines[1].startswith("data: ")
    return lines[0][len("event: ") :], json.loads(lines[1][len("data: ") :])


def drain(client) -> list[tuple[str, object]]:
    events = []
    while not client.empty():
        events.append(decode(client.get_nowait()))
    return events


def test_sse_framing_is_one_event_line_and_one_data_line() -> None:
    message = encode_event("summary", {"row": {"name": "猫头人\nline"}})
    assert message == 'event: summary\ndata: {"row":{"name":"猫头人\\nline"}}\n\n'.encode()
    assert decode(message) == ("summary", {"row": {"name": "猫头人\nline"}})


def test_catch_up_order_without_a_match() -> None:
    state = hub()
    assert [name for name, _ in state.catch_up()] == CATCH_UP
    hello = dict(state.catch_up())["hello"]
    assert hello == {
        "serverVersion": "test",
        "localPlayerId": None,
        "suggestedPlayerId": None,
        "modelAvailable": False,
        "replayDir": "Replay",
        "liveSource": "playback",
    }
    assert dict(state.catch_up())["status"]["state"] == "waiting"
    assert dict(hub(live_source="none").catch_up())["status"]["state"] == "off"


def test_catch_up_order_with_a_match() -> None:
    state = hub()
    state.set_predictions("b1", [])
    state.set_frame({"snapshot": {}, "localIndex": 0, "composition": [], "boardAsOfLastFight": [False, False]})
    state.add_prediction("b1", {"round": 1, "leftWinProbability": 0.6, "swing": 0.0})
    events = state.catch_up()
    assert [name for name, _ in events] == [*CATCH_UP, "frame", "predictions"]
    assert events[-1][1] == {"battleId": "b1", "rows": [{"round": 1, "leftWinProbability": 0.6, "swing": 0.0}]}


def test_subscriber_gets_catch_up_then_incremental_events() -> None:
    state = hub()
    state.set_summaries([summary("b1", "me", "x")])
    client = state.subscribe()
    events = drain(client)
    assert [name for name, _ in events] == CATCH_UP
    assert events[1][1] == {"rows": [summary("b1", "me", "x")]}

    state.upsert_summary(summary("b2", "me", "y"))
    state.add_rating("b2", "me", 1500)
    state.update_status(state="live")
    state.update_status(state="live")  # unchanged: not sent again
    state.set_local_player("me")
    names = [name for name, _ in drain(client)]
    assert names == ["summary", "baseline", "rating", "status", "config"]
    assert dict(state.catch_up())["ratings"] == {"byBattle": {"b2": {"me": 1500}}}
    assert dict(state.catch_up())["hello"]["localPlayerId"] == "me"

    state.unsubscribe(client)
    state.add_rating("b3", "me", 1510)
    assert client.empty()


def test_model_correction_resends_the_catch_up() -> None:
    state = hub(model_available=True)
    client = state.subscribe()
    drain(client)
    state.set_model_available(False)
    events = drain(client)
    assert [name for name, _ in events] == CATCH_UP
    assert events[0][1]["modelAvailable"] is False


def test_close_wakes_clients() -> None:
    state = hub()
    client = state.subscribe()
    drain(client)
    state.close()
    assert client.get_nowait() is CLOSED


def test_suggested_player_needs_sixty_percent() -> None:
    rows = [summary("b1", "me", "a"), summary("b2", "me", "b"), summary("b3", "c", "d")]
    assert suggest_player_id(rows) == "me"
    assert suggest_player_id([*rows, summary("b4", "e", "f")]) is None
    assert suggest_player_id([]) is None
    state = hub()
    state.set_summaries(rows)
    assert dict(state.catch_up())["hello"]["suggestedPlayerId"] == "me"


def frame(battle_id: str, round_number: int, phase: str) -> dict:
    return {"snapshot": {"match": {"battleId": battle_id, "round": round_number, "phase": phase}}}


def test_catch_up_replays_each_rounds_first_fight_over_frame() -> None:
    state = hub()
    state.set_frame(frame("old", 1, "fight_over"))
    for round_number in (1, 2, 3):
        state.set_frame(frame("b1", round_number, "deploying"))
        state.set_frame(frame("b1", round_number, "fight_over"))
        state.set_frame({**frame("b1", round_number, "fight_over"), "later": True})
    state.set_frame(frame("b1", 4, "deploying"))
    frames = [data for name, data in state.catch_up() if name == "frame"]
    history = [frame("b1", number, "fight_over") for number in (1, 2, 3)]
    assert frames == [*history, frame("b1", 4, "deploying")]


def test_a_stalled_client_is_dropped_with_only_the_close_marker_left() -> None:
    state = hub()
    stalled = state.subscribe()
    for index in range(CLIENT_QUEUE_LIMIT + 50):
        state.update_status(detail=f"tick {index}")
    assert stalled not in state._clients
    assert stalled.qsize() == 1 and stalled.get_nowait() is CLOSED
    # A reconnecting client starts again from a fresh catch-up.
    fresh = state.subscribe()
    assert [name for name, _ in drain(fresh)] == CATCH_UP
