from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION, MODEL_SNAPSHOT_PHASE
from ..datasets import load_training_snapshots
from ..features import build_features, feature_names
from ..models import create_artifact, save_artifact


def train_model(
    dataset_path: Path,
    output_path: Path,
    *,
    test_size: float = 0.25,
    seed: int = 20260711,
    regularization: float | None = None,
) -> dict[str, object]:
    dataset_path = dataset_path.resolve()
    snapshots = load_training_snapshots(dataset_path)
    battle_ids = {snapshot.match.battle_id for snapshot in snapshots}
    if None in battle_ids:
        raise ValueError("Training snapshot is missing match.battleId.")
    if len(battle_ids) < 10:
        raise ValueError(f"Only {len(battle_ids)} usable 1v1 matches; at least 10 are required for a validation split.")

    rows: list[np.ndarray] = []
    labels: list[int] = []
    groups: list[str] = []
    rounds: list[int] = []
    for snapshot in snapshots:
        if snapshot.outcome is None or snapshot.match.battle_id is None:
            raise ValueError("Training snapshot is missing outcome or match.battleId.")
        winner_index = snapshot.outcome.winner_index
        battle_id = snapshot.match.battle_id
        round_number = snapshot.match.round
        for perspective in (0, 1):
            rows.append(build_features(snapshot, perspective))
            labels.append(int(perspective == winner_index))
            groups.append(battle_id)
            rounds.append(round_number)

    x = np.vstack(rows)
    y = np.asarray(labels, dtype=np.int8)
    group_values = np.asarray(groups)
    round_values = np.asarray(rounds)
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_indices, test_indices = next(splitter.split(x, y, group_values))

    selected_regularization, cross_validation = _select_regularization(
        x[train_indices], y[train_indices], group_values[train_indices], seed, regularization
    )
    model = _new_model(selected_regularization, seed)
    model.fit(x[train_indices], y[train_indices])
    probabilities = model.predict_proba(x[test_indices])[:, 1]
    metrics = _metrics(y[test_indices], probabilities)

    save_artifact(output_path, create_artifact(model, feature_names()))

    metadata: dict[str, object] = {
        "createdAtUtc": datetime.now(UTC).isoformat(),
        "datasetPath": str(dataset_path),
        "datasetSha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest().upper(),
        "matchSnapshotSchemaVersion": MATCH_SNAPSHOT_SCHEMA_VERSION,
        "featureSchemaVersion": 1,
        "snapshotPhase": MODEL_SNAPSHOT_PHASE,
        "inputSnapshotCount": len(snapshots),
        "usableMatchCount": len(battle_ids),
        "trainingMatchCount": len(set(group_values[train_indices])),
        "testMatchCount": len(set(group_values[test_indices])),
        "trainingSampleCount": int(len(train_indices)),
        "testSampleCount": int(len(test_indices)),
        "replayVersions": sorted(
            {
                snapshot.game_build.replay_version
                for snapshot in snapshots
                if snapshot.game_build.replay_version is not None
            }
        ),
        "selectedRegularization": selected_regularization,
        "crossValidation": cross_validation,
        "metrics": metrics,
        "metricsByRound": _metrics_by_round(y[test_indices], probabilities, round_values[test_indices]),
    }
    output_path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _new_model(regularization: float, seed: int) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(C=regularization, fit_intercept=False, max_iter=5000, random_state=seed),
            ),
        ]
    )


def _select_regularization(
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    seed: int,
    requested: float | None,
) -> tuple[float, list[dict[str, float]]]:
    candidates = [requested] if requested is not None else [0.001, 0.003, 0.01, 0.03, 0.1, 0.3]
    splitter = GroupKFold(n_splits=5, shuffle=True, random_state=seed)
    results = []
    for value in candidates:
        losses = []
        for fold_train, fold_validation in splitter.split(x, y, groups):
            model = _new_model(value, seed)
            model.fit(x[fold_train], y[fold_train])
            losses.append(float(log_loss(y[fold_validation], model.predict_proba(x[fold_validation])[:, 1])))
        results.append(
            {
                "regularization": float(value),
                "meanLogLoss": float(np.mean(losses)),
                "standardDeviation": float(np.std(losses)),
            }
        )
    selected = min(results, key=lambda result: result["meanLogLoss"])["regularization"]
    return selected, results


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(labels, probabilities >= 0.5)),
        "rocAuc": float(roc_auc_score(labels, probabilities)),
        "logLoss": float(log_loss(labels, probabilities)),
        "brier": float(brier_score_loss(labels, probabilities)),
    }


def _metrics_by_round(
    labels: np.ndarray, probabilities: np.ndarray, rounds: np.ndarray
) -> dict[str, dict[str, float | int]]:
    result = {}
    for round_number in sorted(set(rounds.tolist())):
        mask = rounds == round_number
        result[str(round_number)] = {
            "samples": int(mask.sum()),
            **_metrics(labels[mask], probabilities[mask]),
        }
    return result
