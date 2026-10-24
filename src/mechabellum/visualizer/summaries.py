"""Replay -> Match Summary: what the Stats view needs about one past match."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..collector.memory.layouts import SUPPORTED_LAYOUTS
from ..collector.replay import parse_replay
from ..collector.replay.parser import PlayerHistory, ReplayMatch
from ..collector.unit_catalog import (
    ADVANCE_TEAM_NAMES,
    GAME_NAMES_VERSION,
    OFFICER_NAMES,
    advance_team_name,
    officer_name,
)
from ..contracts import FightResult
from .roles import board_composition

# Bump whenever the summary shape or its rules change; cached summaries of another version are rebuilt.
SUMMARY_VERSION = 1

# Specialists are the officers whose name is also a non-lineup advance team ("Supply Specialist", not "3 Fang + ...").
SPECIALIST_IDS: frozenset[int] = frozenset(
    officer_id
    for officer_id, name in OFFICER_NAMES.items()
    if name in {team for team in ADVANCE_TEAM_NAMES.values() if not team[:1].isdigit()}
)


class SkippedReplay(Exception):
    """A replay that is not a summary: not 1v1, or no known winner."""


def _known_game_versions() -> dict[int, str]:
    """Replay format -> game version, from game_names.json's source build and the memory layouts."""
    known = {layout.replay_version: layout.game_version for layout in SUPPORTED_LAYOUTS}
    names = json.loads(files("mechabellum.collector").joinpath("game_names.json").read_text(encoding="utf-8"))
    match = re.search(rf"game {re.escape(GAME_NAMES_VERSION)}\.(\d+)", names["sources"]["primary"])
    if match:
        known[int(match.group(1))] = GAME_NAMES_VERSION
    return known


KNOWN_GAME_VERSIONS = _known_game_versions()


def summarize_replay(path: Path, replay_root: Path | None = None) -> dict[str, Any]:
    """The Match Summary of one replay; raises SkippedReplay for replays that don't make one."""
    replay = parse_replay(path)
    if replay.match_mode != "VS_1_1" or len(replay.players) != 2:
        raise SkippedReplay(f"not a 1v1 replay ({replay.match_mode}, {len(replay.players)} players)")
    if replay.winner_index is None or replay.winner_index >= len(replay.players):
        raise SkippedReplay("no known winner")
    last_round = max((round_number for player in replay.players for round_number in player.rounds), default=0)
    return {
        "battleId": replay.battle_id,
        "date": battle_date(replay.battle_id),
        "endedAtUtc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z"),
        "replayPath": str(path),
        "replayVersion": replay.version,
        "gameVersion": game_version(path, replay.version, replay_root),
        "gameMode": replay.game_mode,
        "mapId": replay.map_id,
        "rounds": last_round,
        "winnerIndex": replay.winner_index,
        "players": [
            _player(replay, player, index == replay.winner_index, last_round)
            for index, player in enumerate(replay.players)
        ],
    }


def battle_date(battle_id: str | None) -> str | None:
    match = re.match(r"(\d{4})(\d{2})(\d{2})", battle_id or "")
    return None if match is None else "-".join(match.groups())


def game_version(path: Path, replay_version: int | None, replay_root: Path | None = None) -> str | None:
    """ "2.0.0.4.2331": the replay's version folder name, else the known game version of its replay format."""
    parent = path.parent
    if replay_root is None or parent.resolve() != replay_root.resolve():
        parts = parent.name.split(".")
        if len(parts) >= 5 and all(part for part in parts) and parts[-1].isdigit():
            return parent.name
    if replay_version is not None and replay_version in KNOWN_GAME_VERSIONS:
        return f"{KNOWN_GAME_VERSIONS[replay_version]}.{replay_version}"
    return None


def specialist(officer_ids: list[int] | None) -> tuple[int, str] | None:
    """The first round-1 officer that is a specialist, else the first unknown id (AsyncBattle's ids are unknown)."""
    if not officer_ids:
        return None
    for officer_id in officer_ids:
        if officer_id in SPECIALIST_IDS:
            return officer_id, OFFICER_NAMES[officer_id]
    unknown = next((officer_id for officer_id in officer_ids if officer_id not in OFFICER_NAMES), None)
    return None if unknown is None else (unknown, officer_name(unknown))


def opening(advance_team_id: int | None) -> tuple[int, str, str | None] | None:
    """(id, name, lead): the lead is the unit after "3 " in "3 Arclight + 2 Sledgehammer"."""
    if advance_team_id is None:
        return None
    name = advance_team_name(advance_team_id) if advance_team_id in ADVANCE_TEAM_NAMES else None
    if name is None:
        return advance_team_id, f"Unknown opening ({advance_team_id})", None
    match = re.match(r"3 (.+?)(?: \+ |$)", name)
    return advance_team_id, name, None if match is None else match.group(1)


def _player(replay: ReplayMatch, player: PlayerHistory, won: bool, last_round: int) -> dict[str, Any]:
    first = player.rounds.get(1)
    picked = specialist(None if first is None else first.officer_ids)
    lineup = player.opening_lineup()
    picked_opening = opening(None if lineup is None else lineup.advance_team_id)
    fielded: dict[int, None] = {}
    for round_number in sorted(player.rounds):
        for unit in player.rounds[round_number].units:
            fielded.setdefault(unit.unit_id)
    composition = [
        board_composition(player.rounds[round_number + 1].units, round_number)
        for round_number in replay.snapshot_rounds
    ]
    last = player.rounds.get(last_round)
    return {
        "playerId": player.player_id,
        "name": player.name,
        "won": won,
        "specialistId": None if picked is None else picked[0],
        "specialistName": None if picked is None else picked[1],
        "openingId": None if picked_opening is None else picked_opening[0],
        "openingName": None if picked_opening is None else picked_opening[1],
        "openingLead": None if picked_opening is None else picked_opening[2],
        "fieldedUnitIds": list(fielded),
        "fightResults": fight_results(player, won, last_round),
        "finalHp": None if last is None else last.reactor_core,
        "composition": composition,
    }


def fight_results(player: PlayerHistory, won: bool, last_round: int) -> list[FightResult]:
    """Every fight's result in order.

    Formats before 2340 never record the last fight, since no round record follows it; the match winner won it.
    """
    full = next((item.recorded_fight_results for item in player.rounds.values() if item.recorded_fight_results), None)
    if full is not None:
        return list(full[:last_round])
    results = player.fight_result_history(last_round) or []
    if len(results) == last_round - 1:
        results = [*results, "Win" if won else "Lose"]
    return results
