from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION, MODEL_SNAPSHOT_PHASE
from ..datasets import load_training_snapshots
from ..features import FEATURE_SCHEMA_VERSION, feature_names
from ..models import create_artifact, save_artifact
from .calibration import CalibratedModel
from .evaluation import EvaluationRows, evaluation_report

SplitMode = Literal["group", "time"]
CalibrationMethod = Literal["none", "sigmoid", "isotonic"]


def train_model(
    dataset_path: Path,
    output_path: Path,
    *,
    test_size: float = 0.25,
    seed: int = 20260711,
    regularization: float | None = None,
    split: SplitMode = "group",
    calibration: CalibrationMethod = "none",
    calibration_size: float = 0.2,
) -> dict[str, object]:
    """Train the win model.

    `split="group"` holds out random whole matches; `split="time"` holds out the newest matches by battle id, so
    the test set measures performance on games played after the training data. With calibration, a further slice
    of matches (the newest before the test set, for a time split) fits a sigmoid or isotonic map on top of the
    trained model.
    """
    dataset_path = dataset_path.resolve()
    snapshots = load_training_snapshots(dataset_path)
    battle_ids = {snapshot.match.battle_id for snapshot in snapshots}
    if None in battle_ids:
        raise ValueError("Training snapshot is missing match.battleId.")
    if len(battle_ids) < 10:
        raise ValueError(f"Only {len(battle_ids)} usable 1v1 matches; at least 10 are required for a validation split.")

    rows = EvaluationRows.from_snapshots(snapshots)
    fit_indices, test_indices = split_matches(rows.battle_ids, test_size, split, seed)
    calibration_indices = np.asarray([], dtype=int)
    if calibration != "none":
        fit_part, calibration_part = split_matches(rows.battle_ids[fit_indices], calibration_size, split, seed)
        fit_indices, calibration_indices = fit_indices[fit_part], fit_indices[calibration_part]
    fit = rows.subset(fit_indices)
    test = rows.subset(test_indices)

    selected_regularization, cross_validation = _select_regularization(
        fit.x, fit.y, fit.battle_ids, seed, regularization
    )
    model = _new_model(selected_regularization, seed)
    model.fit(fit.x, fit.y)
    final_model: object = model
    if calibration != "none":
        held = rows.subset(calibration_indices)
        if len(set(held.y.tolist())) < 2:
            raise ValueError("The calibration slice holds only one class; use more matches or no calibration.")
        final_model = CalibratedModel(model, calibration).fit(held.x, held.y)
    probabilities = final_model.predict_proba(test.x)[:, 1]  # type: ignore[attr-defined]
    report = evaluation_report(test, probabilities)
    if calibration != "none":
        report["uncalibrated"] = evaluation_report(test, model.predict_proba(test.x)[:, 1])["metrics"]

    save_artifact(output_path, create_artifact(final_model, feature_names()))

    metadata: dict[str, object] = {
        "createdAtUtc": datetime.now(UTC).isoformat(),
        "datasetPath": str(dataset_path),
        "datasetSha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest().upper(),
        "matchSnapshotSchemaVersion": MATCH_SNAPSHOT_SCHEMA_VERSION,
        "featureSchemaVersion": FEATURE_SCHEMA_VERSION,
        "snapshotPhase": MODEL_SNAPSHOT_PHASE,
        "split": split,
        "calibration": calibration,
        "inputSnapshotCount": len(snapshots),
        "usableMatchCount": len(battle_ids),
        "trainingMatchCount": len(set(fit.battle_ids.tolist())),
        "calibrationMatchCount": len(set(rows.battle_ids[calibration_indices].tolist())),
        "testMatchCount": len(set(test.battle_ids.tolist())),
        "trainingSampleCount": int(len(fit_indices)),
        "testSampleCount": int(len(test_indices)),
        "testBattleIdRange": [min(test.battle_ids.tolist()), max(test.battle_ids.tolist())],
        "replayVersions": sorted(
            {
                snapshot.game_build.replay_version
                for snapshot in snapshots
                if snapshot.game_build.replay_version is not None
            }
        ),
        "selectedRegularization": selected_regularization,
        "crossValidation": cross_validation,
        "metrics": report["metrics"],
        "evaluation": report,
    }
    output_path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def battle_order_key(battle_id: str) -> tuple[int, ...]:
    """Battle ids look like `20261024--67150459`: the date, then a running number. Sort by both."""
    parts = [part for part in battle_id.replace("-", " ").split() if part.isdigit()]
    return tuple(int(part) for part in parts) or (0,)


def split_matches(battle_ids: np.ndarray, size: float, mode: SplitMode, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Indices of the kept rows and the held-out rows; whole matches always stay on one side."""
    if mode == "group":
        splitter = GroupShuffleSplit(n_splits=1, test_size=size, random_state=seed)
        kept, held = next(splitter.split(np.zeros(len(battle_ids)), groups=battle_ids))
        return kept, held
    ordered = sorted(set(battle_ids.tolist()), key=battle_order_key)
    held_count = max(1, round(len(ordered) * size))
    held_ids = set(ordered[-held_count:])
    held_mask = np.asarray([battle_id in held_ids for battle_id in battle_ids.tolist()])
    return np.flatnonzero(~held_mask), np.flatnonzero(held_mask)


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
