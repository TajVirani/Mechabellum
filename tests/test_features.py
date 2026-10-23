import json
from pathlib import Path

import numpy as np

from mechabellum.contracts import validate_snapshot
from mechabellum.features import build_features, feature_names

ROOT = Path(__file__).resolve().parents[1]


def test_perspectives_are_exact_opposites() -> None:
    data = json.loads((ROOT / "contracts/match-snapshot/v2/battle-start.example.json").read_text(encoding="utf-8"))
    snapshot = validate_snapshot(data)
    first = build_features(snapshot, 0)
    second = build_features(snapshot, 1)
    assert first.shape == (len(feature_names()),)
    np.testing.assert_allclose(first, -second, atol=1e-12)
