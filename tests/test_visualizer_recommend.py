from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

from mechabellum.contracts import MatchSnapshot
from mechabellum.inference.actions import ActionCatalog, rank_actions
from mechabellum.visualizer.cache import SummaryCache
from mechabellum.visualizer.hub import Hub
from mechabellum.visualizer.insights import Insights
from mechabellum.visualizer.recommend import LiveRecommender, RecommendingProcessor, rank_player

PLAYBACK = Path(__file__).parent / "fixtures" / "live" / "playing-match.sample.jsonl"
LOCAL_PLAYER = "281474976710829150"


class FakeTokenModel:
    """Win probability grows with the perspective player's army value over the opponent's."""

    def win_probabilities(self, snapshots, perspectives):
        out = []
        for snapshot, perspective in zip(snapshots, perspectives, strict=True):
            own = sum(unit.sell_supply for unit in snapshot.players[perspective].units)
            other = sum(unit.sell_supply for unit in snapshot.players[1 - perspective].units)
            out.append(1 / (1 + math.exp(-(own - other) / 1000)))
        return out


FAKE_ARTIFACT = {"kind": "token", "model": FakeTokenModel()}


def make_hub(local_player_id: str | None = LOCAL_PLAYER) -> Hub:
    return Hub(
        server_version="test",
        model_available=True,
        replay_dir=None,
        live_source="playback",
        local_player_id=local_player_id,
    )


def frames() -> list[MatchSnapshot]:
    return [MatchSnapshot.model_validate_json(line) for line in PLAYBACK.read_text(encoding="utf-8").splitlines()]


def play(processor: RecommendingProcessor) -> list[dict]:
    payloads = []
    for frame in frames():
        processor.process(frame)
        payload = processor.recommender.flush()
        if payload is not None:
            payloads.append(payload)
    return payloads


def test_payload_ranks_purchases_for_the_local_player(tmp_path: Path) -> None:
    hub = make_hub()
    ranked_snapshots: list[MatchSnapshot] = []

    def spy(artifact, snapshot, perspective, candidates, *args):
        ranked_snapshots.append(snapshot)
        return rank_actions(artifact, snapshot, perspective, candidates, *args)

    recommender = LiveRecommender(hub, rank=spy)
    recommender.set_artifact(FAKE_ARTIFACT)
    processor = RecommendingProcessor(hub, SummaryCache(tmp_path / "v.sqlite"), recommender)
    payloads = play(processor)

    # One payload per deploying frame that changes the position, and per fight_over round; never round 0.
    assert payloads and all(item["phase"] in ("deploying", "fight_over") and item["round"] >= 1 for item in payloads)
    assert {item["round"] for item in payloads if item["phase"] == "fight_over"} == set(range(1, 11))
    deploying = next(item for item in payloads if item["phase"] == "deploying" and item["round"] == 4)
    assert deploying["modelAvailable"] is True and deploying["localIndex"] == 0
    assert [player["index"] for player in deploying["players"]] == [0]
    me = deploying["players"][0]
    assert deploying["budgetEstimated"] is False
    assert me["name"] == "Sleep Deprived" and me["budget"] == 800
    rows = me["rows"]
    assert 0 < len(rows) <= 8
    assert all(row["kind"] in ("buy", "unlock", "upgrade", "technology", "card") for row in rows)
    gains = [row["gain"] for row in rows]
    assert gains == sorted(gains, reverse=True)
    assert all((row["cost"] or 0) <= me["budget"] for row in rows)
    # The fake model rewards army value, so the best row spends the most on a unit.
    assert rows[0]["kind"] in ("buy", "unlock", "upgrade") and rows[0]["gain"] > 0
    assert len({(row["kind"], row.get("unitId")) for row in rows if row["kind"] in ("buy", "unlock")}) == len(
        [row for row in rows if row["kind"] in ("buy", "unlock")]
    )
    assert all(row["label"] and row["winProbability"] > 0 for row in rows)
    assert 0 < me["baselineWinProbability"] < 1
    # A deploying frame borrows the last fight's histories, as the model was trained on fight_over positions.
    round_four = [item for item in ranked_snapshots if item.match.phase == "deploying" and item.match.round == 4][0]
    assert len(round_four.players[0].reactor_core_history) == 3
    # At a fight's end the budget is the supply left plus this round's income.
    fight_over = next(item for item in payloads if item["phase"] == "fight_over" and item["round"] == 4)
    assert fight_over["budgetEstimated"] is True and fight_over["players"][0]["budget"] == 100 + 800
    catch_up = dict(hub.catch_up())
    assert catch_up["recommendations"] == payloads[-1]
    json.dumps(payloads)  # the payload is plain JSON


def test_offered_cards_are_ranked_for_the_local_player_only() -> None:
    snapshot = next(item for item in frames() if item.match.phase == "deploying" and item.match.round == 4)
    catalog = ActionCatalog.from_game_data()
    offer = snapshot.match.reinforcement_offer
    result = rank_player(FAKE_ARTIFACT, snapshot, 0, catalog, offer, top=200)
    assert not [row for row in result["rows"] if row["kind"] == "move"]
    cards = [row for row in result["rows"] if row["kind"] == "card"]
    assert cards and {row["itemId"] for row in cards} <= set(offer)
    recommender = LiveRecommender(make_hub(local_player_id=None))
    spectating = recommender.compute(snapshot, None, FAKE_ARTIFACT)
    assert [player["index"] for player in spectating["players"]] == [0, 1]
    assert not [row for player in spectating["players"] for row in player["rows"] if row["kind"] == "card"]


def test_without_a_model_the_payload_has_no_rows_but_still_counters() -> None:
    hub = make_hub()
    snapshot = next(item for item in frames() if item.match.phase == "deploying" and item.match.round == 5)
    enemy = max(snapshot.players[1].units, key=lambda unit: unit.sell_supply).unit_id
    mine = snapshot.players[0].units[0].unit_id
    other = 31 if mine != 31 else 32

    def summary(index: int, won: bool, my_unit: int) -> dict:
        boards = [
            [{"round": 5, "unitIds": [my_unit], "technologyIds": []}],
            [{"round": 5, "unitIds": [enemy], "technologyIds": []}],
        ]
        return {
            "battleId": f"b{index}",
            "replayPath": f"b{index}.grbr",
            "gameMode": "Normal",
            "players": [
                {"playerId": "a", "won": won, "boards": boards[0]},
                {"playerId": "b", "won": not won, "boards": boards[1]},
            ],
        }

    # Against `enemy`, `mine` won 3 of 3 and `other` 0 of 3.
    hub.set_summaries([summary(i, True, mine) for i in range(3)] + [summary(i + 3, False, other) for i in range(3)])
    recommender = LiveRecommender(hub, Insights(hub.summaries_snapshot), min_sample=3)
    recommender.submit(snapshot, 0)
    payload = recommender.flush()
    assert payload["modelAvailable"] is False and payload["counterBand"] == "mid"
    me = payload["players"][0]
    assert me["rows"] == [] and me["baselineWinProbability"] is None
    # Opponent units in order of the supply they hold; each has its own entry, thin ones with no rows.
    invested = {}
    for unit in snapshot.players[1].units:
        invested[unit.unit_id] = invested.get(unit.unit_id, 0) + unit.sell_supply
    assert [entry["enemyUnitId"] for entry in me["counters"]] == sorted(invested, key=lambda unit: -invested[unit])
    first = next(entry for entry in me["counters"] if entry["enemyUnitId"] == enemy)
    assert first["enemyUnitId"] == enemy and first["n"] == 6 and first["baselineWinRate"] == 0.5
    assert [(row["unitId"], row["owned"]) for row in first["rows"]] == [(mine, True)]
    assert first["rows"][0]["delta"] == 0.5
    assert "not a causal" in payload["counterNote"]


def test_submissions_are_deduplicated_on_what_the_ranking_uses() -> None:
    recommender = LiveRecommender(make_hub())
    snapshot = next(item for item in frames() if item.match.phase == "deploying" and item.match.round == 3)
    assert recommender.submit(snapshot, 0)
    assert not recommender.submit(snapshot, 0)
    players = list(snapshot.players)
    unit = players[0].units[0]
    players[0] = players[0].model_copy(
        update={"units": [unit.model_copy(update={"x": unit.x + 40}), *players[0].units[1:]]}
    )
    moved = snapshot.model_copy(update={"players": players})
    assert not recommender.submit(moved, 0)
    assert recommender.submit(moved, 0, force=True)
    assert recommender.submit(snapshot, None)  # spectating ranks both players: a new key
    battle_start = next(item for item in frames() if item.match.phase == "battle_start")
    assert not recommender.submit(battle_start, 0)


def test_worker_thread_sends_the_latest_frame() -> None:
    hub = make_hub()
    recommender = LiveRecommender(hub)
    stop = threading.Event()
    worker = threading.Thread(target=recommender.run, args=(stop, 0.05), daemon=True)
    worker.start()
    snapshot = next(item for item in frames() if item.match.phase == "deploying" and item.match.round == 2)
    client = hub.subscribe()
    recommender.submit(snapshot, 0)
    message = ""
    while not message.startswith("event: recommendations"):
        message = client.get(timeout=10).decode()
    stop.set()
    worker.join(5)
    assert hub.recommendations["round"] == 2


def test_counters_are_refreshed_when_the_summaries_change() -> None:
    hub = make_hub()
    recommender = LiveRecommender(hub, Insights(hub.summaries_snapshot), min_sample=1, refresh_seconds=5)
    snapshot = next(item for item in frames() if item.match.phase == "deploying" and item.match.round == 5)
    recommender.submit(snapshot, 0)
    first = recommender.flush()
    assert all(entry["n"] == 0 for entry in first["players"][0]["counters"])
    assert not recommender.refresh_if_stale(now=time.monotonic() + 60)  # nothing changed
    enemy = snapshot.players[1].units[0].unit_id
    boards = [[{"round": 5, "unitIds": [snapshot.players[0].units[0].unit_id]}], [{"round": 5, "unitIds": [enemy]}]]
    row = {
        "battleId": "b1",
        "replayPath": "b1.grbr",
        "players": [
            {"playerId": "a", "won": True, "boards": boards[0]},
            {"playerId": "b", "won": False, "boards": boards[1]},
        ],
    }
    hub.upsert_summary(row)
    assert not recommender.refresh_if_stale(now=time.monotonic())  # rate-limited
    assert recommender.refresh_if_stale(now=time.monotonic() + 60)
    second = recommender.flush()
    assert next(entry for entry in second["players"][0]["counters"] if entry["enemyUnitId"] == enemy)["n"] == 1
