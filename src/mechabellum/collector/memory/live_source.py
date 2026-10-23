from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from ...contracts import (
    EquipmentItem,
    FightResult,
    GameBuild,
    MatchInfo,
    MatchSnapshot,
    PlayerSnapshot,
    PlayerState,
    SnapshotSource,
    UnitDeployment,
    UnitTechnologySet,
)
from ..unit_catalog import unit_name
from .il2cpp_reader import Il2CppReader
from .layouts import (
    ACTIVABLE_ITEM_IS_ACTIVE,
    CLASS_STATIC_FIELDS,
    EQUIPMENT_DATA,
    EQUIPMENT_DURABILITY,
    GR_OBJECT_ID,
    ITEM_DATA,
    MAP_ELEMENT_BOUND,
    MAP_ELEMENT_IS_ROTATE,
    MATCH_CLIENT_CURRENT,
    PLAYER_MANAGER_CONTROLLERS,
    RISK_INFO_NAME,
    TEAM_SYSTEM_CONTROLLERS,
    TECHNOLOGY_MANAGER_TECHNOLOGIES,
    TECHNOLOGY_MANAGER_UNIT_ID,
    UNIT_MANAGER_UNITS,
    MemoryLayout,
    find_layout,
)
from .windows_process import WindowsProcessMemory, find_module, find_process_id

MAX_EQUIPMENT_PER_UNIT = 8
MAX_ROUNDS = 128


class ObserverStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryStatus:
    layout_replay_version: int
    layout_game_version: str
    root_class: str
    current_match_type: str | None
    deployment_read_available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "layoutReplayVersion": self.layout_replay_version,
            "layoutGameVersion": self.layout_game_version,
            "rootClass": self.root_class,
            "currentMatchType": self.current_match_type,
            "deploymentReadAvailable": self.deployment_read_available,
        }


class LiveMemorySource:
    def __init__(
        self,
        process_id: int,
        process_memory: WindowsProcessMemory,
        game_assembly_base: int,
        layout: MemoryLayout,
    ) -> None:
        self.process_id = process_id
        self._process_memory = process_memory
        self._memory = Il2CppReader(process_memory)
        self._game_assembly_base = game_assembly_base
        self._layout = layout

    @classmethod
    def attach(cls) -> LiveMemorySource:
        if os.name != "nt":
            raise OSError("The live memory source only supports Windows.")
        process_id = find_process_id("Mechabellum.exe")
        if process_id is None:
            raise RuntimeError("Mechabellum is not running.")
        module = find_module(process_id, "GameAssembly.dll")
        if module is None:
            raise RuntimeError("The running process has not loaded GameAssembly.dll.")
        digest = hashlib.sha256(module.path.read_bytes()).hexdigest().upper()
        layout = find_layout(digest)
        if layout is None:
            raise RuntimeError(f"GameAssembly.dll build is not supported (SHA256={digest}).")
        return cls(process_id, WindowsProcessMemory(process_id), module.base_address, layout)

    @property
    def layout(self) -> MemoryLayout:
        return self._layout

    def get_status(self) -> MemoryStatus:
        layout = self._layout
        match_client_class = self._memory.read_pointer(self._game_assembly_base + layout.match_client_class_global_rva)
        if match_client_class == 0:
            return MemoryStatus(layout.replay_version, layout.game_version, "MatchClient", None, False)
        root_class_name = self._memory.read_class_name(match_client_class)
        static_fields = self._memory.read_pointer(match_client_class + CLASS_STATIC_FIELDS)
        current_match = 0 if static_fields == 0 else self._memory.read_pointer(static_fields + MATCH_CLIENT_CURRENT)
        current_type = None if current_match == 0 else self._memory.read_object_class_name(current_match)
        return MemoryStatus(
            layout.replay_version, layout.game_version, root_class_name, current_type, current_match != 0
        )

    def read_snapshot(self) -> MatchSnapshot:
        offsets = self._layout.match
        battle_offsets = self._layout.battle_info
        match, match_type = self._current_match()
        battle_info = self._memory.read_pointer(match + offsets.battle_info)
        player_manager = self._memory.read_pointer(match + offsets.player_manager)
        if player_manager == 0:
            raise ObserverStateError("The match has not finished initializing player data.")
        controllers_list = self._memory.read_pointer(player_manager + PLAYER_MANAGER_CONTROLLERS)
        controllers = self._memory.read_list_pointers(controllers_list, 8)
        if len(controllers) < 2:
            raise ObserverStateError(f"Only found {len(controllers)} player(s); the match snapshot is still loading.")
        round_number = self._memory.read_int32(match + offsets.round_count)
        players = [self._read_player(controller, round_number) for controller in controllers if controller != 0]
        return MatchSnapshot(
            game_build=GameBuild(
                replay_version=self._layout.replay_version,
                game_version=self._layout.game_version,
                game_assembly_sha256=self._layout.game_assembly_sha256,
            ),
            source=SnapshotSource(
                type="memory",
                uri=f"memory://Mechabellum/{self.process_id}",
                captured_at_utc=datetime.now(UTC),
            ),
            match=MatchInfo(
                battle_id=None
                if battle_info == 0
                else self._memory.read_managed_string(
                    self._memory.read_pointer(battle_info + battle_offsets.battle_id)
                ),
                map_id=None if battle_info == 0 else self._memory.read_int32(battle_info + battle_offsets.map_id),
                game_mode=None
                if battle_info == 0
                else _game_mode(self._memory.read_int32(battle_info + battle_offsets.game_mode)),
                match_mode=match_type
                if battle_info == 0
                else _match_mode(self._memory.read_int32(battle_info + battle_offsets.match_mode)),
                round=round_number,
                phase=_resolve_phase(players),
                reinforcement_offer=None,
            ),
            players=players,
            outcome=None,
        )

    def _current_match(self) -> tuple[int, str]:
        match_client_class = self._memory.read_pointer(
            self._game_assembly_base + self._layout.match_client_class_global_rva
        )
        if match_client_class == 0 or self._memory.read_class_name(match_client_class) != "MatchClient":
            raise ValueError("Layout validation failed: invalid MatchClient class root pointer.")
        static_fields = self._memory.read_pointer(match_client_class + CLASS_STATIC_FIELDS)
        current_match = 0 if static_fields == 0 else self._memory.read_pointer(static_fields + MATCH_CLIENT_CURRENT)
        if current_match == 0:
            raise ObserverStateError("No match is currently running.")
        match_type = self._memory.read_object_class_name(current_match)
        if not match_type:
            raise ValueError("Could not identify the IL2CPP type of the match.")
        return current_match, match_type

    def _read_player(self, controller: int, round_number: int) -> PlayerSnapshot:
        offsets = self._layout.player
        player = self._memory.read_pointer(controller + self._layout.player_controller.player)
        if player == 0:
            raise ValueError("The Player pointer in PlayerController is null.")
        player_id = self._memory.read_uint64(player + offsets.id)
        risk_info = self._memory.read_pointer(player + offsets.risk_info)
        name = (
            f"Player {player_id}"
            if risk_info == 0
            else self._memory.read_managed_string(self._memory.read_pointer(risk_info + RISK_INFO_NAME))
            or f"Player {player_id}"
        )
        unit_manager = self._memory.read_pointer(controller + self._layout.player_controller.unit_manager)
        units_list = 0 if unit_manager == 0 else self._memory.read_pointer(unit_manager + UNIT_MANAGER_UNITS)
        unit_pointers = [] if units_list == 0 else self._memory.read_list_pointers(units_list, 256)
        units = [
            unit for index, pointer in enumerate(unit_pointers) if (unit := self._read_unit(pointer, index)) is not None
        ]
        history, previous = self._read_fight_results(player, round_number)
        return PlayerSnapshot(
            player_id=str(player_id),
            name=name,
            team=self._read_team_index(controller),
            state=_player_state(self._memory.read_int32(player + offsets.state)),
            supply=self._memory.read_int32(player + offsets.supply),
            reactor_core=self._memory.read_int32(player + offsets.reactor_core),
            max_reactor_core=self._read_optional_int32(player, offsets.max_reactor_core),
            round_supply_income=self._read_optional_int32(player, offsets.round_supply_income),
            previous_fight_result=previous,
            fight_result_history=history,
            units=units,
            active_technologies=self._read_active_technologies(player),
            equipment_inventory=None,
            commander_skills=None,
            officer_ids=None,
            buildings=None,
            contraptions=None,
            blueprint_ids=None,
            energy_tower_skill_ids=None,
            tower_strengthen_levels=None,
            unlocked_unit_ids=None,
            reinforcement_choice=None,
        )

    def _read_optional_int32(self, address: int, offset: int | None) -> int | None:
        return None if offset is None else self._memory.read_int32(address + offset)

    def _read_fight_results(
        self, player: int, round_number: int
    ) -> tuple[list[FightResult] | None, FightResult | None]:
        offsets = self._layout.player
        if offsets.fight_result_history is not None:
            values = self._memory.read_list_int32(
                self._memory.read_pointer(player + offsets.fight_result_history), MAX_ROUNDS
            )
            results = [_fight_result(value) for value in values]
            # Keep the contract's meaning (fights before this round) even if the list already holds the current one.
            completed = max(0, round_number - 1)
            if None in results or len(results) < completed:
                return None, None
            history = [result for result in results[:completed] if result is not None]
            return history, history[-1] if history else None
        if offsets.previous_fight_result is not None and round_number >= 2:
            return None, _fight_result(self._memory.read_int32(player + offsets.previous_fight_result))
        return None, None

    def _read_team_index(self, controller: int) -> int | None:
        offsets = self._layout.player_controller
        team_controller = self._memory.read_pointer(controller + offsets.team_controller)
        team_system = self._memory.read_pointer(controller + offsets.team_system)
        team_controllers_list = (
            0 if team_system == 0 else self._memory.read_pointer(team_system + TEAM_SYSTEM_CONTROLLERS)
        )
        if team_controller == 0 or team_controllers_list == 0:
            return None
        team_controllers = self._memory.read_list_pointers(team_controllers_list, 8)
        return team_controllers.index(team_controller) if team_controller in team_controllers else None

    def _read_active_technologies(self, player: int) -> list[UnitTechnologySet]:
        player_agent = self._memory.read_pointer(player + self._layout.player.player_agent)
        managers_list = (
            0
            if player_agent == 0
            else self._memory.read_pointer(player_agent + self._layout.player_agent_technology_managers)
        )
        if managers_list == 0:
            return []
        result = []
        for manager in self._memory.read_list_pointers(managers_list, 256):
            if manager == 0:
                continue
            unit_id = self._memory.read_int32(manager + TECHNOLOGY_MANAGER_UNIT_ID)
            technologies_list = self._memory.read_pointer(manager + TECHNOLOGY_MANAGER_TECHNOLOGIES)
            if technologies_list == 0:
                continue
            active_ids = []
            for technology in self._memory.read_list_pointers(technologies_list, 32):
                if technology == 0 or self._memory.read_byte(technology + ACTIVABLE_ITEM_IS_ACTIVE) == 0:
                    continue
                technology_data = self._memory.read_pointer(technology + ITEM_DATA)
                technology_id = 0 if technology_data == 0 else self._memory.read_int32(technology_data + GR_OBJECT_ID)
                if technology_id > 0:
                    active_ids.append(technology_id)
            if active_ids:
                result.append(
                    UnitTechnologySet(unit_id=unit_id, unit_name=unit_name(unit_id), technology_ids=active_ids)
                )
        return result

    def _read_unit(self, card_element: int, list_index: int) -> UnitDeployment | None:
        if card_element == 0:
            return None
        offsets = self._layout.card_element
        team_offsets = self._layout.mech_team
        card_data = self._memory.read_pointer(card_element + offsets.unit_data)
        map_element = self._memory.read_pointer(card_element + offsets.map_element)
        mech_team = self._memory.read_pointer(card_element + offsets.mech_team)
        if card_data == 0 or map_element == 0 or mech_team == 0:
            return None
        unit_id = self._memory.read_int32(card_data + GR_OBJECT_ID)
        if unit_id <= 0 or unit_id > 100_000:
            return None
        bound_x = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND)
        bound_y = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND + 0x04)
        width = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND + 0x08)
        height = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND + 0x0C)
        raw_level = self._memory.read_int32(mech_team + team_offsets.level)
        experience = max(
            0, min(2_147_483_647, int(self._memory.read_int64(mech_team + team_offsets.experience) / 4_294_967_296))
        )
        return UnitDeployment(
            unit_id=unit_id,
            unit_name=unit_name(unit_id),
            formation_index=list_index,
            raw_level=raw_level,
            display_level=raw_level + 1,
            experience=experience,
            x=bound_x + width / 2,
            y=bound_y + height / 2,
            is_rotated=self._memory.read_byte(map_element + MAP_ELEMENT_IS_ROTATE) != 0,
            sell_supply=self._memory.read_int32(card_element + offsets.sell_supply),
            round_count=self._memory.read_int32(mech_team + team_offsets.round_count),
            equipment=self._read_unit_equipment(card_element),
        )

    def _read_unit_equipment(self, card_element: int) -> list[EquipmentItem]:
        field = self._memory.read_pointer(card_element + self._layout.card_element.equipment)
        if field == 0:
            return []
        pointers = (
            self._memory.read_list_pointers(field, MAX_EQUIPMENT_PER_UNIT)
            if self._layout.equipment_is_list
            else [field]
        )
        items = []
        for equipment in pointers:
            if equipment == 0:
                continue
            equipment_data = self._memory.read_pointer(equipment + EQUIPMENT_DATA)
            equipment_id = 0 if equipment_data == 0 else self._memory.read_int32(equipment_data + GR_OBJECT_ID)
            if equipment_id > 0:
                durability = self._memory.read_int32(equipment + EQUIPMENT_DURABILITY)
                items.append(EquipmentItem(equipment_id=equipment_id, durability=durability))
        return items

    def close(self) -> None:
        self._process_memory.close()

    def __enter__(self) -> LiveMemorySource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _resolve_phase(players: list[PlayerSnapshot]) -> str:
    states = [player.state for player in players]
    if all(state == "Fighting" for state in states):
        return "battle_start"
    if all(state == "DeployOver" for state in states):
        return "deploy_over"
    if all(state == "Deploying" for state in states):
        return "deploying"
    if all(state == "FightOver" for state in states):
        return "fight_over"
    return "unknown"


def _game_mode(value: int) -> str:
    return {0: "Normal", 1: "Competition", 2: "Guider", 3: "Survive", 4: "Rift"}.get(value, f"GameMode#{value}")


def _match_mode(value: int) -> str:
    return {0: "VS_1_1", 1: "VS_2_2", 2: "VS_4_Scuffle", 3: "VS_2_2_Scuffle"}.get(value, f"MatchMode#{value}")


def _fight_result(value: int) -> FightResult | None:
    results: dict[int, FightResult] = {0: "Win", 1: "Lose", 2: "Deuce"}
    return results.get(value)


def _player_state(value: int) -> PlayerState:
    states: dict[int, PlayerState] = {0: "Deploying", 1: "DeployOver", 2: "Fighting", 3: "FightOver"}
    return states.get(value, "Unknown")
