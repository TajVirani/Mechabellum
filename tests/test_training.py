import json
from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from mechabellum.contracts import validate_snapshot
from mechabellum.datasets import write_snapshots
from mechabellum.features import feature_names
from mechabellum.inference import predict_snapshot
from mechabellum.models import load_artifact
from mechabellum.training import train_model

ROOT = Path(__file__).resolve().parents[1]


def test_training_and_prediction_pipeline(tmp_path: Path) -> None:
    example = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    snapshots = []
    for index in range(10):
        data = deepcopy(example)
        data["match"]["battleId"] = f"battle-{index}"
        winner = index % 2
        data["outcome"] = {
            "winnerIndex": winner,
            "winnerPlayerId": data["players"][winner]["playerId"],
            "winnerName": data["players"][winner]["name"],
        }
        data["players"][winner]["reactorCore"] += index * 10
        snapshots.append(validate_snapshot(data))

    dataset = tmp_path / "dataset.jsonl"
    model_path = tmp_path / "model.joblib"
    write_snapshots(dataset, snapshots)
    metadata = train_model(dataset, model_path, seed=7)
    artifact = load_artifact(model_path, feature_names())
    result = predict_snapshot(artifact, snapshots[0], model_path)

    assert metadata["usableMatchCount"] == 10
    assert model_path.is_file()
    assert abs(sum(item["winProbability"] for item in result["predictions"]) - 1.0) < 1e-12


def test_time_split_with_calibration_and_evaluation(tmp_path: Path) -> None:
    from mechabellum.training import evaluate_model

    example = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    snapshots = []
    for index in range(12):
        data = deepcopy(example)
        data["match"]["battleId"] = f"20261024--{67100000 + index}"
        winner = index % 2
        data["outcome"] = {
            "winnerIndex": winner,
            "winnerPlayerId": data["players"][winner]["playerId"],
            "winnerName": data["players"][winner]["name"],
        }
        data["players"][winner]["reactorCore"] += 500 + index * 10
        data["players"][0]["rating"], data["players"][1]["rating"] = 1600, 1700
        snapshots.append(validate_snapshot(data))
    dataset = tmp_path / "dataset.jsonl"
    model_path = tmp_path / "model.joblib"
    write_snapshots(dataset, snapshots)
    metadata = train_model(dataset, model_path, seed=7, split="time", calibration="sigmoid")

    # The newest matches are held out for testing.
    assert metadata["testBattleIdRange"] == ["20261024--67100009", "20261024--67100011"]
    assert metadata["calibrationMatchCount"] == 2
    report = evaluate_model(dataset, model_path)
    assert report["matches"] == 12
    assert set(report["byRatingTier"]) == {"1500-1749"}
    assert report["calibration"]["expectedCalibrationError"] >= 0
