"""Turn snapshots into padded integer and float arrays for the token models (no torch dependency)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

from ..contracts import MatchSnapshot, PlayerSnapshot
from ..features import UnitToken, build_features, unit_tokens

PAD = 0
UNKNOWN = 1
MAX_TOKENS = 64
MAX_TOKEN_TECHNOLOGIES = 8
MAX_TOKEN_EQUIPMENT = 4
MAX_PLAYER_ITEMS = 48
TOKEN_NUMERIC = 11
PLAYER_BAGS = ("officers", "commander_skills", "card", "opening", "pool")


@dataclass
class Vocabulary:
    """Id → index tables; 0 is padding and 1 is any id not seen in training."""

    tables: dict[str, dict[str, int]] = field(default_factory=dict)

    def fit(self, name: str, values: Iterable[object]) -> None:
        table = self.tables.setdefault(name, {})
        for value in values:
            key = str(value)
            if key not in table:
                table[key] = len(table) + 2

    def index(self, name: str, value: object) -> int:
        return self.tables.get(name, {}).get(str(value), UNKNOWN)

    def size(self, name: str) -> int:
        return len(self.tables.get(name, {})) + 2

    def to_dict(self) -> dict[str, dict[str, int]]:
        return self.tables

    @classmethod
    def from_dict(cls, tables: dict[str, dict[str, int]]) -> Vocabulary:
        return cls({name: dict(table) for name, table in tables.items()})


def _player_bags(player: PlayerSnapshot) -> dict[str, list[object]]:
    choice = player.reinforcement_choice
    return {
        "officers": list(player.officer_ids or []),
        "commander_skills": [skill.skill_id for skill in player.commander_skills or []],
        "card": [] if choice is None or choice.item_id is None else [choice.item_id],
        "opening": [] if player.opening_lineup is None else [player.opening_lineup.advance_team_id],
        "pool": list(player.unlocked_unit_ids or []) + [-unit for unit in player.locked_unit_ids or []],
    }


def build_vocabulary(snapshots: Sequence[MatchSnapshot]) -> Vocabulary:
    vocabulary = Vocabulary()
    for snapshot in snapshots:
        vocabulary.fit("map", [snapshot.match.map_id])
        vocabulary.fit("mode", [snapshot.match.game_mode])
        vocabulary.fit("version", [snapshot.game_build.replay_version])
        for player in snapshot.players:
            vocabulary.fit("unit", [unit.unit_id for unit in player.units])
            vocabulary.fit("technology", [tech for item in player.active_technologies for tech in item.technology_ids])
            vocabulary.fit("equipment", [item.equipment_id for unit in player.units for item in unit.equipment])
            for bag, values in _player_bags(player).items():
                vocabulary.fit(bag, values)
    return vocabulary


@dataclass(frozen=True)
class EncodedBatch:
    """Arrays for one perspective of many snapshots; the leading axis is the snapshot."""

    unit: np.ndarray  # (n, tokens)
    technologies: np.ndarray  # (n, tokens, MAX_TOKEN_TECHNOLOGIES)
    equipment: np.ndarray  # (n, tokens, MAX_TOKEN_EQUIPMENT)
    numeric: np.ndarray  # (n, tokens, TOKEN_NUMERIC)
    mask: np.ndarray  # (n, tokens) True for real tokens
    bags: dict[str, np.ndarray]  # name -> (n, 2, MAX_PLAYER_ITEMS), side 0 = perspective player
    context_ids: np.ndarray  # (n, 3): map, mode, version
    context_features: np.ndarray  # (n, features): feature schema 2


def _token_numeric(token: UnitToken) -> list[float]:
    return [
        float(token.side),
        token.level / 5.0,
        math.log1p(token.experience) / 8.0,
        token.value / 1000.0,
        token.x / 300.0,
        token.depth / 300.0,
        float(token.is_rotated),
        token.round_count / 10.0,
        float(token.known_unit),
        len(token.technology_ids) / 4.0,
        len(token.equipment_ids) / 2.0,
    ]


def encode(snapshots: Sequence[MatchSnapshot], perspective_of: Sequence[int], vocabulary: Vocabulary) -> EncodedBatch:
    n = len(snapshots)
    unit = np.zeros((n, MAX_TOKENS), dtype=np.int64)
    technologies = np.zeros((n, MAX_TOKENS, MAX_TOKEN_TECHNOLOGIES), dtype=np.int64)
    equipment = np.zeros((n, MAX_TOKENS, MAX_TOKEN_EQUIPMENT), dtype=np.int64)
    numeric = np.zeros((n, MAX_TOKENS, TOKEN_NUMERIC), dtype=np.float32)
    mask = np.zeros((n, MAX_TOKENS), dtype=bool)
    bags = {name: np.zeros((n, 2, MAX_PLAYER_ITEMS), dtype=np.int64) for name in PLAYER_BAGS}
    context_ids = np.zeros((n, 3), dtype=np.int64)
    features = []
    for row, (snapshot, perspective) in enumerate(zip(snapshots, perspective_of, strict=True)):
        tokens = sorted(unit_tokens(snapshot, perspective), key=lambda token: (token.side, token.depth))[:MAX_TOKENS]
        for index, token in enumerate(tokens):
            unit[row, index] = vocabulary.index("unit", token.unit_id)
            for slot, technology in enumerate(token.technology_ids[:MAX_TOKEN_TECHNOLOGIES]):
                technologies[row, index, slot] = vocabulary.index("technology", technology)
            for slot, item in enumerate(token.equipment_ids[:MAX_TOKEN_EQUIPMENT]):
                equipment[row, index, slot] = vocabulary.index("equipment", item)
            numeric[row, index] = _token_numeric(token)
            mask[row, index] = True
        for side, player_index in ((0, perspective), (1, 1 - perspective)):
            for name, values in _player_bags(snapshot.players[player_index]).items():
                for slot, value in enumerate(values[:MAX_PLAYER_ITEMS]):
                    bags[name][row, side, slot] = vocabulary.index(name, value)
        context_ids[row] = [
            vocabulary.index("map", snapshot.match.map_id),
            vocabulary.index("mode", snapshot.match.game_mode),
            vocabulary.index("version", snapshot.game_build.replay_version),
        ]
        features.append(build_features(snapshot, perspective))
    return EncodedBatch(
        unit, technologies, equipment, numeric, mask, bags, context_ids, np.asarray(features, dtype=np.float32)
    )
