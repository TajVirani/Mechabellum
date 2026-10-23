import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from mechabellum.contracts import snapshot_to_dict, snapshot_to_json, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


def test_contract_example_round_trips() -> None:
    data = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    snapshot = validate_snapshot(data)
    assert snapshot.schema_version == 2
    assert snapshot.match.phase == "fight_over"
    assert snapshot_to_dict(snapshot) == data
    assert json.loads(snapshot_to_json(snapshot)) == data


def test_missing_required_field_is_rejected() -> None:
    data = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    invalid = deepcopy(data)
    del invalid["players"][0]["reactorCore"]
    with pytest.raises(ValidationError):
        validate_snapshot(invalid)


def test_v1_document_is_rejected() -> None:
    data = json.loads((ROOT / "contracts/match-snapshot/v1/battle-start.example.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        validate_snapshot(data)
