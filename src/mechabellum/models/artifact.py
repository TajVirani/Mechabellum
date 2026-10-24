from __future__ import annotations

from pathlib import Path
from typing import Any


def create_artifact(model: Any, feature_names: list[str]) -> dict[str, Any]:
    from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION, MODEL_SNAPSHOT_PHASE
    from ..features import FEATURE_SCHEMA_VERSION

    return {
        "model": model,
        "featureNames": feature_names,
        "featureSchemaVersion": FEATURE_SCHEMA_VERSION,
        "matchSnapshotSchemaVersion": MATCH_SNAPSHOT_SCHEMA_VERSION,
        "snapshotPhase": MODEL_SNAPSHOT_PHASE,
    }


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_artifact(path: Path, expected_feature_names: list[str]) -> dict[str, Any]:
    import joblib

    from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION, MODEL_SNAPSHOT_PHASE
    from ..features import FEATURE_SCHEMA_VERSION

    artifact = joblib.load(path)
    if artifact.get("featureSchemaVersion") != FEATURE_SCHEMA_VERSION:
        raise ValueError("Model feature schema version does not match the code; please retrain.")
    if artifact.get("featureNames") != expected_feature_names:
        raise ValueError("Model feature version does not match the code; please retrain.")
    if artifact.get("matchSnapshotSchemaVersion") != MATCH_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Model MatchSnapshot contract version does not match the code; please retrain.")
    if artifact.get("snapshotPhase") != MODEL_SNAPSHOT_PHASE:
        raise ValueError("Model was trained on a different snapshot phase; please retrain.")
    return artifact
