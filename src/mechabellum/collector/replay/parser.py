from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar
from xml.etree import ElementTree

from ...contracts import (
    Building,
    CommanderSkill,
    Contraption,
    EquipmentItem,
    FightReport,
    FightResult,
    GameBuild,
    MatchInfo,
    MatchOutcome,
    MatchSnapshot,
    OpeningLineup,
    PlayerAction,
    PlayerSnapshot,
    ReinforcementChoice,
    SnapshotSource,
    UnitDeployment,
    UnitTechnologySet,
)
from ..unit_catalog import unit_name
from ..versions import split_application_version
from .extractor import extract_battle_record

T = TypeVar("T")
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
OPENING_LINEUP_ACTION = "PAD_ChooseAdvanceTeam"
ACTION_TIME_FIELDS = ("Time", "LocalTime")
FIGHT_RESULTS: dict[str, FightResult] = {"win": "Win", "lose": "Lose", "deuce": "Deuce"}


@dataclass(frozen=True)
class PlayerRound:
    round: int
    supply: int | None
    reactor_core: int | None
    recorded_previous_fight_result: FightResult | None
    recorded_fight_results: list[FightResult] | None
    units: list[UnitDeployment]
    active_technologies: list[UnitTechnologySet]
    equipment_inventory: list[EquipmentItem] | None
    commander_skills: list[CommanderSkill] | None
    officer_ids: list[int] | None
    buildings: list[Building] | None
    contraptions: list[Contraption] | None
    blueprint_ids: list[int] | None
    energy_tower_skill_ids: list[int] | None
    tower_strengthen_levels: list[int] | None
    unlocked_unit_ids: list[int] | None
    locked_unit_ids: list[int] | None
    reinforcement_choice: ReinforcementChoice | None
    round_actions: list[PlayerAction] | None


@dataclass(frozen=True)
class PlayerHistory:
    player_id: str | None
    name: str
    team: int | None
    rounds: dict[int, PlayerRound]

    def opening_lineup(self) -> OpeningLineup | None:
        """The advance team picked in the round 0 opening selection; None when that record is missing."""
        opening = self.rounds.get(0)
        if opening is None or opening.round_actions is None:
            return None
        picks = [action for action in opening.round_actions if action.type == OPENING_LINEUP_ACTION]
        if not picks:
            return None
        team_id, index = picks[-1].parameters.get("ID"), picks[-1].parameters.get("Index")
        if not isinstance(team_id, int):
            return None
        return OpeningLineup(advance_team_id=team_id, offer_index=index if isinstance(index, int) else None)

    def fight_result_history(self, round_number: int) -> list[FightResult] | None:
        """Results of the fights before `round_number`; never includes later rounds."""
        completed = max(0, round_number - 1)
        # Since replay format 2340 every round record carries the full match history, so it must be truncated.
        full = next((item.recorded_fight_results for item in self.rounds.values() if item.recorded_fight_results), None)
        if full is not None:
            return full[:completed] if len(full) >= completed else None
        # Older formats only record the previous result per round: round r holds the result of fight r - 1.
        history: list[FightResult] = []
        for later_round in range(2, round_number + 1):
            state = self.rounds.get(later_round)
            if state is None or state.recorded_previous_fight_result is None:
                return None
            history.append(state.recorded_previous_fight_result)
        return history

    def values_after_fights(self, round_number: int, value: Callable[[PlayerRound], int | None]) -> list[int] | None:
        """`value` after each of fights 1..round_number, read from records 2..round_number + 1."""
        values = []
        for later_round in range(2, round_number + 2):
            state = self.rounds.get(later_round)
            item = None if state is None else value(state)
            if item is None:
                return None
            values.append(item)
        return values


@dataclass(frozen=True)
class ReplayMatch:
    source_file: Path
    version: int | None
    # The game version from the folder the game saves downloaded replays in, such as 2.0.0.5.2340/.
    game_version: str | None
    battle_id: str | None
    map_id: int | None
    game_mode: str | None
    match_mode: str | None
    winner_index: int | None
    players: list[PlayerHistory]
    reinforcement_offers: dict[int, list[int] | None]
    # Fight number -> one report per player, in player order.
    fight_reports: dict[int, list[FightReport | None]]

    @property
    def common_rounds(self) -> list[int]:
        if not self.players:
            return []
        common = set(self.players[0].rounds)
        for player in self.players[1:]:
            common.intersection_update(player.rounds)
        return sorted(common)

    @property
    def snapshot_rounds(self) -> list[int]:
        """Rounds with a fight_over snapshot: both the round's record and the next one are present."""
        common = set(self.common_rounds)
        return [round_number for round_number in sorted(common) if round_number >= 1 and round_number + 1 in common]


def parse_replay(path: Path) -> ReplayMatch:
    root = extract_battle_record(path)
    if root.tag != "BattleRecord":
        raise ValueError(f"Unsupported XML root element: {root.tag}")
    battle_info = root.find("BattleInfo")
    player_nodes = root.findall("./playerRecords/PlayerRecord")
    players = [_parse_player(node) for node in player_nodes]
    if not players:
        raise ValueError("Replay contains no player round records.")
    # Current replays write team 0 for every player, which is not a real team assignment.
    teams = [player.team for player in players]
    if None in teams or len(set(teams)) < 2:
        players = [replace(player, team=None) for player in players]
    version = _optional_int(root, "Version")
    return ReplayMatch(
        source_file=path.resolve(),
        version=version,
        game_version=_folder_game_version(path, version),
        battle_id=_text(battle_info, "BattleID"),
        map_id=_optional_int(battle_info, "MapID"),
        game_mode=_text(battle_info, "GameMode"),
        match_mode=_text(battle_info, "MatchMode"),
        winner_index=_winner_index(root, len(players)),
        players=players,
        reinforcement_offers=_reinforcement_offers(root),
        fight_reports=_fight_reports(root, len(players)),
    )


def select_round(replay: ReplayMatch, round_number: int | None = None) -> MatchSnapshot:
    """The fight_over snapshot of `round_number`.

    A replay's round record is written when that round begins, before income and deployment, so record r + 1 holds
    the board as it stood when fight r ended. Record r itself holds round r's card offer and choice.
    """
    if round_number is None:
        if not replay.snapshot_rounds:
            raise ValueError("Replay has no fight_over snapshot shared by both players.")
        round_number = max(replay.snapshot_rounds)
    players = []
    reports = replay.fight_reports.get(round_number, [])
    for player_index, player in enumerate(replay.players):
        current = player.rounds.get(round_number)
        state = player.rounds.get(round_number + 1)
        if current is None or state is None:
            raise ValueError(
                f"Player {player.name} needs records for rounds {round_number} and {round_number + 1} "
                f"to build the round {round_number} snapshot."
            )
        history = player.fight_result_history(round_number + 1)
        players.append(
            PlayerSnapshot(
                player_id=player.player_id,
                name=player.name,
                team=player.team,
                rating=None,
                state="FightOver",
                supply=state.supply,
                reactor_core=state.reactor_core,
                max_reactor_core=None,
                round_supply_income=None,
                previous_fight_result=history[-1] if history else None,
                fight_result_history=history,
                units=state.units,
                active_technologies=state.active_technologies,
                equipment_inventory=state.equipment_inventory,
                commander_skills=state.commander_skills,
                officer_ids=state.officer_ids,
                buildings=state.buildings,
                contraptions=state.contraptions,
                blueprint_ids=state.blueprint_ids,
                energy_tower_skill_ids=state.energy_tower_skill_ids,
                tower_strengthen_levels=state.tower_strengthen_levels,
                unlocked_unit_ids=state.unlocked_unit_ids,
                locked_unit_ids=state.locked_unit_ids,
                last_fight_report=reports[player_index] if player_index < len(reports) else None,
                reactor_core_history=player.values_after_fights(round_number, lambda item: item.reactor_core),
                supply_history=player.values_after_fights(round_number, lambda item: item.supply),
                reinforcement_choice=current.reinforcement_choice,
                opening_lineup=player.opening_lineup(),
                round_actions=current.round_actions,
            )
        )
    outcome = None
    if replay.winner_index is not None and replay.winner_index < len(players):
        winner = players[replay.winner_index]
        outcome = MatchOutcome(
            winner_index=replay.winner_index, winner_player_id=winner.player_id, winner_name=winner.name
        )
    return MatchSnapshot(
        game_build=GameBuild(
            replay_version=replay.version, game_version=replay.game_version, game_assembly_sha256=None
        ),
        source=SnapshotSource(type="replay", uri=replay.source_file.as_uri(), captured_at_utc=None),
        match=MatchInfo(
            battle_id=replay.battle_id,
            map_id=replay.map_id,
            game_mode=replay.game_mode,
            match_mode=replay.match_mode,
            round=round_number,
            phase="fight_over",
            reinforcement_offer=replay.reinforcement_offers.get(round_number),
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
    recorded_results = None
    if data is not None and data.find("roundFightResult") is not None:
        parsed = [_fight_result(item.text) for item in data.findall("./roundFightResult/FightResultType")]
        recorded_results = None if None in parsed else [item for item in parsed if item is not None]
    return PlayerRound(
        round=_int(node, "round"),
        supply=_optional_int(data, "supply"),
        reactor_core=_optional_int(data, "reactorCore"),
        recorded_previous_fight_result=_fight_result(_text(data, "preRoundFightResult")),
        recorded_fight_results=recorded_results,
        units=units,
        active_technologies=technologies,
        equipment_inventory=_parse_list(data, "equipmentDatas", "EquipmentData", _parse_inventory_item),
        commander_skills=_parse_list(data, "commanderSkills", "CommanderSkillData", _parse_commander_skill),
        officer_ids=_int_list(data, "officers"),
        buildings=_parse_list(data, "constructionSnapshotDatas", "ConstructionSnapshotData", _parse_building),
        contraptions=_parse_list(data, "contraptions", "ContraptionData", _parse_contraption),
        blueprint_ids=_int_list(data, "bluepints"),
        energy_tower_skill_ids=_int_list(data, "energyTowerSkills"),
        tower_strengthen_levels=_int_list(data, "towerStrengthenLevels"),
        unlocked_unit_ids=_int_list(data, "shop/unlockedUnits"),
        locked_unit_ids=_int_list(data, "shop/lockedUnits"),
        reinforcement_choice=_parse_reinforcement_choice(node),
        round_actions=_parse_actions(node),
    )


def _parse_unit(node: ElementTree.Element) -> UnitDeployment:
    unit_id = _int(node, "id")
    raw_level = _int(node, "Level")
    position = node.find("Position")
    equipment = [
        EquipmentItem(equipment_id=equipment_id, durability=None)
        for item in node.findall("./equipments/equipment")
        if (equipment_id := _int_attribute(item, "data")) > 0
    ]
    # Older formats stored a single item in EquipmentID; current ones leave it 0 and use the equipments list.
    legacy_id = _int(node, "EquipmentID")
    if legacy_id > 0 and all(item.equipment_id != legacy_id for item in equipment):
        equipment.insert(0, EquipmentItem(equipment_id=legacy_id, durability=_optional_int(node, "Durability")))
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
        sell_supply=_int(node, "SellSupply"),
        round_count=_int(node, "RoundCount"),
        equipment=equipment,
    )


def _parse_technologies(node: ElementTree.Element) -> UnitTechnologySet:
    unit_id = _int(node, "id")
    ids = []
    for technology in node.findall("./techs/tech"):
        value = _int_attribute(technology, "data")
        if value > 0:
            ids.append(value)
    return UnitTechnologySet(unit_id=unit_id, unit_name=unit_name(unit_id), technology_ids=ids)


def _parse_inventory_item(node: ElementTree.Element) -> EquipmentItem | None:
    equipment_id = _int(node, "id")
    if equipment_id <= 0:
        return None
    return EquipmentItem(equipment_id=equipment_id, durability=_optional_int(node, "durability"))


def _parse_commander_skill(node: ElementTree.Element) -> CommanderSkill | None:
    skill_id = _int(node, "id")
    if skill_id <= 0:
        return None
    active = _text(node, "isActive")
    return CommanderSkill(
        skill_id=skill_id,
        slot_index=_int(node, "index"),
        acquired_round=_optional_int(node, "getRound"),
        cooldown_rounds=_optional_int(node, "coolingRound"),
        is_active=None if active is None else active.lower() == "true",
    )


def _parse_building(node: ElementTree.Element) -> Building | None:
    building_id = _int(node, "ID")
    if building_id <= 0:
        return None
    position = node.find("Position")
    return Building(
        building_id=building_id,
        index=_int(node, "Index"),
        x=_float(position, "x"),
        y=_float(position, "y"),
        durability=_int_list(node, "durability"),
    )


def _parse_contraption(node: ElementTree.Element) -> Contraption | None:
    contraption_id = _int(node, "id")
    if contraption_id <= 0:
        return None
    position = node.find("position")
    return Contraption(
        contraption_id=contraption_id, index=_int(node, "index"), x=_float(position, "x"), y=_float(position, "y")
    )


def _parse_actions(node: ElementTree.Element) -> list[PlayerAction] | None:
    records = node.find("actionRecords")
    if records is None:
        return None
    actions = []
    for action in records:
        parameters = {child.tag: _xml_value(child) for child in action if child.tag not in ACTION_TIME_FIELDS}
        actions.append(
            PlayerAction(
                type=action.attrib.get(XSI_TYPE, action.tag),
                time=_number(action.findtext("Time")),
                local_time=_number(action.findtext("LocalTime")),
                parameters=parameters,
            )
        )
    return actions


def _xml_value(element: ElementTree.Element) -> object:
    """An action field as JSON: repeated children become a list, distinct children an object, text a scalar."""
    attributes = {key: _scalar(value) for key, value in element.attrib.items() if key != XSI_TYPE}
    children = list(element)
    if children:
        tags = {child.tag for child in children}
        if len(tags) == 1 and (len(children) > 1 or not attributes):
            values = [_xml_value(child) for child in children]
            return values if not attributes else {**attributes, "items": values}
        return {**attributes, **{child.tag: _xml_value(child) for child in children}}
    if attributes:
        return attributes
    text = (element.text or "").strip()
    return None if not text else _scalar(text)


def _scalar(text: str) -> object:
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    for convert in (int, float):
        try:
            return convert(text)
        except ValueError:
            continue
    return text


def _number(text: str | None) -> float | None:
    try:
        return None if text is None or not text.strip() else float(text)
    except ValueError:
        return None


def _parse_reinforcement_choice(node: ElementTree.Element) -> ReinforcementChoice | None:
    choices = [
        action
        for action in node.findall("./actionRecords/*")
        if action.attrib.get(XSI_TYPE) == "PAD_ChooseReinforceItem"
    ]
    if not choices:
        return None
    item_id = _int(choices[-1], "ID")
    if item_id <= 0:
        return ReinforcementChoice(status="declined", item_id=None, offer_index=None)
    return ReinforcementChoice(status="chosen", item_id=item_id, offer_index=_optional_int(choices[-1], "Index"))


def _reinforcement_offers(root: ElementTree.Element) -> dict[int, list[int] | None]:
    offers: dict[int, list[int] | None] = {}
    for data in root.findall("./matchDatas/MatchSnapshotData"):
        round_number = _optional_int(data, "round")
        container = data.find("reinforceItems")
        if round_number is None or container is None:
            continue
        arrays = container.findall("ArrayOfInt")
        # Both players are dealt the same offer; more than one array has not been observed and is left unknown.
        if not arrays:
            offers[round_number] = []
        elif len(arrays) == 1:
            offers[round_number] = [_int_text(item) for item in arrays[0].findall("int")]
        else:
            offers[round_number] = None
    return offers


def _fight_reports(root: ElementTree.Element, player_count: int) -> dict[int, list[FightReport | None]]:
    """Reports keyed by the fight they describe: the MatchSnapshotData for round r reports fight r - 1."""
    reports: dict[int, list[FightReport | None]] = {}
    for data in root.findall("./matchDatas/MatchSnapshotData"):
        round_number = _optional_int(data, "round")
        nodes = data.findall("./lastFightResult/Reports/FightReport")
        if round_number is None or round_number < 2 or len(nodes) != player_count:
            continue
        reports[round_number - 1] = [
            None
            if _optional_int(node, "Score") is None
            else FightReport(
                score=_int(node, "Score"),
                dead_score=_optional_int(node, "DeadScore"),
                alive_mech_count=_optional_int(node, "AliveMechCount"),
                destroyed_crystal_count=_optional_int(node, "DestroyedCrystalCount"),
            )
            for node in nodes
        ]
    return reports


def _parse_list(
    parent: ElementTree.Element | None,
    container: str,
    item: str,
    parse: Callable[[ElementTree.Element], T | None],
) -> list[T] | None:
    if parent is None or parent.find(container) is None:
        return None
    return [parsed for node in parent.findall(f"./{container}/{item}") if (parsed := parse(node)) is not None]


def _int_list(parent: ElementTree.Element | None, container: str) -> list[int] | None:
    if parent is None or parent.find(container) is None:
        return None
    return [_int_text(node) for node in parent.findall(f"./{container}/int")]


def _fight_result(value: str | None) -> FightResult | None:
    return FIGHT_RESULTS.get((value or "").strip().lower())


def _winner_index(root: ElementTree.Element, player_count: int) -> int | None:
    """The player ranked 0 in the final teamRanks.

    Fight report scores cannot be used: the MatchSnapshotData for round r reports fight r - 1, so the last one
    describes the second-to-last fight and the deciding fight has no report.
    """
    snapshots = root.findall("./matchDatas/MatchSnapshotData")
    if not snapshots:
        return None
    ranks = [_int_text(item) for item in snapshots[-1].findall("./teamRanks/int")]
    if len(ranks) != player_count or ranks.count(0) != 1:
        return None
    return ranks.index(0)


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


def _int_text(node: ElementTree.Element) -> int:
    try:
        return int((node.text or "").strip())
    except ValueError:
        return 0


def _int_attribute(node: ElementTree.Element, name: str) -> int:
    try:
        return int(node.attrib.get(name, "0"))
    except ValueError:
        return 0


def _float(parent: ElementTree.Element | None, name: str) -> float:
    value = _text(parent, name)
    try:
        return float(value) if value is not None else 0.0
    except ValueError:
        return 0.0


def _folder_game_version(path: Path, replay_format: int | None) -> str | None:
    """The game version of a replay saved in a folder named after the application version, when the folder's
    replay format matches the file's; the game's own saves at the top level carry none."""
    parsed = split_application_version(path.parent.name)
    if parsed is None or replay_format is None or parsed[1] != replay_format:
        return None
    return parsed[0]
