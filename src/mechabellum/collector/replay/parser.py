from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from ...contracts import (
    GameBuild,
    MatchInfo,
    MatchOutcome,
    MatchSnapshot,
    PlayerSnapshot,
    SnapshotSource,
    UnitDeployment,
    UnitTechnologySet,
)
from ..unit_catalog import unit_name
from .extractor import extract_battle_record


@dataclass(frozen=True)
class PlayerRound:
    round: int
    supply: int | None
    reactor_core: int | None
    previous_fight_result: str | None
    units: list[UnitDeployment]
    active_technologies: list[UnitTechnologySet]


@dataclass(frozen=True)
class PlayerHistory:
    player_id: str | None
    name: str
    team: int | None
    rounds: dict[int, PlayerRound]


@dataclass(frozen=True)
class ReplayMatch:
    source_file: Path
    version: int | None
    battle_id: str | None
    map_id: int | None
    game_mode: str | None
    match_mode: str | None
    winner_index: int | None
    players: list[PlayerHistory]

    @property
    def common_rounds(self) -> list[int]:
        if not self.players:
            return []
        common = set(self.players[0].rounds)
        for player in self.players[1:]:
            common.intersection_update(player.rounds)
        return sorted(common)


def parse_replay(path: Path) -> ReplayMatch:
    root = extract_battle_record(path)
    if root.tag != "BattleRecord":
        raise ValueError(f"Unsupported XML root element: {root.tag}")
    battle_info = root.find("BattleInfo")
    players = [_parse_player(node) for node in root.findall("./playerRecords/PlayerRecord")]
    if not players:
        raise ValueError("Replay contains no player round records.")
    return ReplayMatch(
        source_file=path.resolve(),
        version=_optional_int(root, "Version"),
        battle_id=_text(battle_info, "BattleID"),
        map_id=_optional_int(battle_info, "MapID"),
        game_mode=_text(battle_info, "GameMode"),
        match_mode=_text(battle_info, "MatchMode"),
        winner_index=_winner_index(root, len(players)),
        players=players,
    )


def select_round(replay: ReplayMatch, round_number: int | None = None) -> MatchSnapshot:
    if round_number is None:
        if not replay.common_rounds:
            raise ValueError("Replay has no rounds shared by both players.")
        round_number = max(replay.common_rounds)
    players = []
    for player in replay.players:
        state = player.rounds.get(round_number)
        if state is None:
            raise ValueError(f"Player {player.name} has no snapshot for round {round_number}.")
        players.append(
            PlayerSnapshot(
                player_id=player.player_id,
                name=player.name,
                team=player.team,
                state="BattleStart",
                supply=state.supply,
                reactor_core=state.reactor_core,
                previous_fight_result=state.previous_fight_result,
                units=state.units,
                active_technologies=state.active_technologies,
            )
        )
    outcome = None
    if replay.winner_index is not None and replay.winner_index < len(players):
        winner = players[replay.winner_index]
        outcome = MatchOutcome(
            winner_index=replay.winner_index, winner_player_id=winner.player_id, winner_name=winner.name
        )
    return MatchSnapshot(
        game_build=GameBuild(replay_version=replay.version, game_version=None, game_assembly_sha256=None),
        source=SnapshotSource(type="replay", uri=replay.source_file.as_uri(), captured_at_utc=None),
        match=MatchInfo(
            battle_id=replay.battle_id,
            map_id=replay.map_id,
            game_mode=replay.game_mode,
            match_mode=replay.match_mode,
            round=round_number,
            phase="battle_start",
        ),
        players=players,
        outcome=outcome,
    )


def _parse_player(node: ElementTree.Element) -> PlayerHistory:
    rounds = {}
    for round_node in node.findall("./playerRoundRecords/PlayerRoundRecord"):
        parsed = _parse_round(round_node)
        rounds[parsed.round] = parsed
    return PlayerHistory(
        player_id=_text(node, "id"),
        name=_text(node, "name") or "Unknown player",
        team=_optional_int(node.find("data"), "team"),
        rounds=rounds,
    )


def _parse_round(node: ElementTree.Element) -> PlayerRound:
    data = node.find("playerData")
    units = sorted(
        (_parse_unit(item) for item in node.findall("./playerData/units/NewUnitData")),
        key=lambda item: item.formation_index,
    )
    technologies = [_parse_technologies(item) for item in node.findall("./playerData/activeTechnologies/UnitData")]
    return PlayerRound(
        round=_int(node, "round"),
        supply=_optional_int(data, "supply"),
        reactor_core=_optional_int(data, "reactorCore"),
        previous_fight_result=_text(data, "preRoundFightResult"),
        units=units,
        active_technologies=technologies,
    )


def _parse_unit(node: ElementTree.Element) -> UnitDeployment:
    unit_id = _int(node, "id")
    raw_level = _int(node, "Level")
    position = node.find("Position")
    return UnitDeployment(
        unit_id=unit_id,
        unit_name=unit_name(unit_id),
        formation_index=_int(node, "Index"),
        raw_level=raw_level,
        display_level=raw_level + 1,
        experience=_int(node, "Exp"),
        x=_float(position, "x"),
        y=_float(position, "y"),
        is_rotated=(_text(node, "IsRotate") or "").lower() == "true",
        equipment_id=_int(node, "EquipmentID"),
        sell_supply=_int(node, "SellSupply"),
        round_count=_int(node, "RoundCount"),
        durability=_int(node, "Durability"),
    )


def _parse_technologies(node: ElementTree.Element) -> UnitTechnologySet:
    unit_id = _int(node, "id")
    ids = []
    for technology in node.findall("./techs/tech"):
        try:
            value = int(technology.attrib.get("data", "0"))
        except ValueError:
            value = 0
        if value > 0:
            ids.append(value)
    return UnitTechnologySet(unit_id=unit_id, unit_name=unit_name(unit_id), technology_ids=ids)


def _winner_index(root: ElementTree.Element, player_count: int) -> int | None:
    snapshots = root.findall("./matchDatas/MatchSnapshotData")
    if not snapshots:
        return None
    scores = [_int(report, "Score") for report in snapshots[-1].findall("./lastFightResult/Reports/FightReport")]
    if len(scores) != player_count or not scores:
        return None
    maximum = max(scores)
    winners = [index for index, score in enumerate(scores) if score == maximum]
    return winners[0] if len(winners) == 1 else None


def _text(parent: ElementTree.Element | None, name: str) -> str | None:
    if parent is None:
        return None
    value = parent.findtext(name)
    return value.strip() if value and value.strip() else None


def _optional_int(parent: ElementTree.Element | None, name: str) -> int | None:
    value = _text(parent, name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _int(parent: ElementTree.Element | None, name: str) -> int:
    return _optional_int(parent, name) or 0


def _float(parent: ElementTree.Element | None, name: str) -> float:
    value = _text(parent, name)
    try:
        return float(value) if value is not None else 0.0
    except ValueError:
        return 0.0
