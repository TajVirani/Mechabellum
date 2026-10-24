"""Train the token models (Deep Sets, Transformer, GNN); requires the `deep` extra."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..datasets import load_training_snapshots
from ..features import feature_names
from ..models import artifact_metadata
from .evaluation import EvaluationRows, evaluation_report
from .pipeline import SplitMode, split_matches
from .targets import next_fight_advantages


def train_token_model(
    dataset_path: Path,
    output_path: Path,
    *,
    architecture: str = "transformer",
    split: SplitMode = "group",
    test_size: float = 0.25,
    validation_size: float = 0.2,
    seed: int = 20260711,
    epochs: int = 300,
    patience: int = 30,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-2,
    width: int = 64,
    advantage_weight: float = 0.0,
) -> dict[str, object]:
    """Fit a token model; validation matches (taken from the training side) pick the epoch to keep.

    With `advantage_weight > 0` the model is multi-task: besides the final result it predicts the advantage of
    the next fight from each position (training/targets.py), weighted by `advantage_weight` in the loss. The
    epoch is still chosen on the final-result log loss alone.
    """
    import torch

    from ..models.token_encoding import build_vocabulary, encode
    from ..models.token_model import TokenModel, save_token_artifact
    from ..models.token_net import TokenNet, TokenNetConfig, to_tensors

    torch.manual_seed(seed)
    np.random.seed(seed)
    dataset_path = dataset_path.resolve()
    snapshots = load_training_snapshots(dataset_path)
    rows = EvaluationRows.from_snapshots(snapshots)
    if len(set(rows.battle_ids.tolist())) < 10:
        raise ValueError("At least 10 usable 1v1 matches are required.")
    fit_indices, test_indices = split_matches(rows.battle_ids, test_size, split, seed)
    train_part, validation_part = split_matches(rows.battle_ids[fit_indices], validation_size, split, seed)
    train_indices, validation_indices = fit_indices[train_part], fit_indices[validation_part]

    vocabulary = build_vocabulary([rows.snapshots[index] for index in train_indices])
    advantages = next_fight_advantages(snapshots)
    row_advantages = [
        advantages.get((snapshot.match.battle_id, snapshot.match.round, int(perspective)))  # type: ignore[arg-type]
        for snapshot, perspective in zip(rows.snapshots, rows.perspectives, strict=True)
    ]
    advantage_values = torch.tensor([0.0 if value is None else value for value in row_advantages])
    advantage_known = torch.tensor([value is not None for value in row_advantages])

    def views(indices: np.ndarray) -> tuple[dict[str, torch.Tensor], dict[str, torch.Tensor], torch.Tensor]:
        chosen = [rows.snapshots[index] for index in indices]
        perspectives = rows.perspectives[indices].tolist()
        own = to_tensors(encode(chosen, perspectives, vocabulary))
        opponent = to_tensors(encode(chosen, [1 - item for item in perspectives], vocabulary))
        return own, opponent, torch.from_numpy(rows.y[indices].astype(np.float32))

    train_own, train_opponent, train_y = views(train_indices)
    validation_own, validation_opponent, validation_y = views(validation_indices)
    train_advantage = advantage_values[torch.from_numpy(train_indices)]
    train_advantage_known = advantage_known[torch.from_numpy(train_indices)]
    config = TokenNetConfig(architecture=architecture, feature_count=len(feature_names()), width=width)  # type: ignore[arg-type]
    net = TokenNet(config, vocabulary)
    optimizer = torch.optim.AdamW(net.parameters(), lr=learning_rate, weight_decay=weight_decay)
    loss_function = torch.nn.BCEWithLogitsLoss()
    best_loss, best_state, best_epoch, waited = float("inf"), None, 0, 0
    history = []
    batch_size = 64
    count = len(train_y)
    for epoch in range(1, epochs + 1):
        net.train()
        order = torch.randperm(count)
        for start in range(0, count, batch_size):
            batch = order[start : start + batch_size]
            optimizer.zero_grad()
            if advantage_weight > 0:
                logit, advantage = net.heads(_take(train_own, batch), _take(train_opponent, batch))
                loss = loss_function(logit, train_y[batch])
                known = train_advantage_known[batch]
                if known.any():
                    error = (advantage[known] - train_advantage[batch][known]) ** 2
                    loss = loss + advantage_weight * error.mean()
            else:
                loss = loss_function(net(_take(train_own, batch), _take(train_opponent, batch)), train_y[batch])
            loss.backward()
            optimizer.step()
        net.eval()
        with torch.no_grad():
            validation_loss = float(loss_function(net(validation_own, validation_opponent), validation_y))
        history.append(validation_loss)
        if validation_loss < best_loss - 1e-4:
            best_loss, best_epoch, waited = validation_loss, epoch, 0
            best_state = {key: value.clone() for key, value in net.state_dict().items()}
        else:
            waited += 1
            if waited >= patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)

    model = TokenModel(net, vocabulary)
    test = rows.subset(test_indices)
    probabilities = model.win_probabilities(test.snapshots, test.perspectives.tolist())
    report = evaluation_report(test, probabilities)
    test_own, test_opponent, _ = views(test_indices)
    with torch.no_grad():
        _, predicted_advantage = net.heads(test_own, test_opponent)
    test_known = advantage_known[torch.from_numpy(test_indices)]
    test_advantage = advantage_values[torch.from_numpy(test_indices)]
    if test_known.any():
        error = predicted_advantage[test_known] - test_advantage[test_known]
        report["nextFightAdvantage"] = {
            "samples": int(test_known.sum()),
            "rmse": float(error.pow(2).mean().sqrt()),
            "signAccuracy": float(
                (torch.sign(predicted_advantage[test_known]) == torch.sign(test_advantage[test_known])).float().mean()
            ),
        }
    metadata: dict[str, object] = {
        "createdAtUtc": datetime.now(UTC).isoformat(),
        "datasetPath": str(dataset_path),
        "datasetSha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest().upper(),
        "architecture": architecture,
        "advantageWeight": advantage_weight,
        "split": split,
        "trainingMatchCount": len(set(rows.battle_ids[train_indices].tolist())),
        "validationMatchCount": len(set(rows.battle_ids[validation_indices].tolist())),
        "testMatchCount": len(set(test.battle_ids.tolist())),
        "parameterCount": sum(parameter.numel() for parameter in net.parameters()),
        "bestEpoch": best_epoch,
        "epochsRun": len(history),
        "bestValidationLogLoss": best_loss,
        "metrics": report["metrics"],
        "evaluation": report,
    }
    save_token_artifact(output_path, model, {**artifact_metadata(feature_names()), "training": _plain(metadata)})
    output_path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _take(batch: dict[str, object], index: object) -> dict[str, object]:
    return {key: value[index] for key, value in batch.items()}  # type: ignore[index]


def _plain(value: object) -> object:
    """JSON round trip, so the metadata stored in the .pt file only holds types `weights_only` loading accepts."""
    return json.loads(json.dumps(value))
