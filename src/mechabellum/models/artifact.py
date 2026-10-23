from __future__ import annotations

from pathlib import Path
from typing import Any


def create_artifact(model: Any, feature_names: list[str]) -> dict[str, Any]:
    from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION

    return {
        "model": model,
        "featureNames": feature_names,
        "featureSchemaVersion": 1,
        "matchSnapshotSchemaVersion": MATCH_SNAPSHOT_SCHEMA_VERSION,
        "snapshotPhase": "battle_start",
    }


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_artifact(path: Path, expected_feature_names: list[str]) -> dict[str, Any]:
    import joblib

    from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION

    artifact = joblib.load(path)
    if artifact.get("featureNames") != expected_feature_names:
        raise ValueError("Model feature version does not match the code; please retrain.")
    if artifact.get("matchSnapshotSchemaVersion") != MATCH_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Model MatchSnapshot contract version does not match the code; please retrain.")
    return artifact
