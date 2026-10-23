from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from ...contracts import (
    GameBuild,
    MatchInfo,
    MatchSnapshot,
    PlayerSnapshot,
    SnapshotSource,
    UnitDeployment,
    UnitTechnologySet,
)
from ..unit_catalog import unit_name
from .il2cpp_reader import Il2CppReader
from .layouts import SUPPORTED_LAYOUT, MemoryLayout
from .windows_process import WindowsProcessMemory, find_module, find_process_id


class ObserverStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryStatus:
    layout_replay_version: int
    root_class: str
    current_match_type: str | None
    deployment_read_available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "layoutReplayVersion": self.layout_replay_version,
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
        layout = SUPPORTED_LAYOUT
        if digest != layout.game_assembly_sha256:
            raise RuntimeError(f"GameAssembly.dll build is not supported (SHA256={digest}).")
        return cls(process_id, WindowsProcessMemory(process_id), module.base_address, layout)

    def get_status(self) -> MemoryStatus:
        match_client_class = self._memory.read_pointer(
            self._game_assembly_base + self._layout.match_client_class_global_rva
        )
        if match_client_class == 0:
            return MemoryStatus(self._layout.replay_version, "MatchClient", None, False)
        root_class_name = self._memory.read_class_name(match_client_class)
        static_fields = self._memory.read_pointer(match_client_class + 0xB8)
        current_match = 0 if static_fields == 0 else self._memory.read_pointer(static_fields + 0x08)
        current_type = None if current_match == 0 else self._memory.read_object_class_name(current_match)
        return MemoryStatus(self._layout.replay_version, root_class_name, current_type, current_match != 0)

    def read_snapshot(self) -> MatchSnapshot:
        match, match_type = self._current_match()
        battle_info = self._memory.read_pointer(match + 0x30)
        player_manager = self._memory.read_pointer(match + 0x70)
        if player_manager == 0:
            raise ObserverStateError("The match has not finished initializing player data.")
        controllers_list = self._memory.read_pointer(player_manager + 0x18)
        controllers = self._memory.read_list_pointers(controllers_list, 8)
        if len(controllers) < 2:
            raise ObserverStateError(f"Only found {len(controllers)} player(s); the match snapshot is still loading.")
        players = [self._read_player(controller) for controller in controllers if controller != 0]
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
                else self._memory.read_managed_string(self._memory.read_pointer(battle_info + 0x18)),
                map_id=None if battle_info == 0 else self._memory.read_int32(battle_info + 0x34),
                game_mode=None if battle_info == 0 else _game_mode(self._memory.read_int32(battle_info + 0x58)),
                match_mode=match_type if battle_info == 0 else _match_mode(self._memory.read_int32(battle_info + 0x5C)),
                round=self._memory.read_int32(match + 0x64),
                phase=_resolve_phase(players),
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
        static_fields = self._memory.read_pointer(match_client_class + 0xB8)
        current_match = 0 if static_fields == 0 else self._memory.read_pointer(static_fields + 0x08)
        if current_match == 0:
            raise ObserverStateError("No match is currently running.")
        match_type = self._memory.read_object_class_name(current_match)
        if not match_type:
            raise ValueError("Could not identify the IL2CPP type of the match.")
        return current_match, match_type

    def _read_player(self, controller: int) -> PlayerSnapshot:
        player = self._memory.read_pointer(controller + 0x128)
        if player == 0:
            raise ValueError("The Player pointer in PlayerController is null.")
        player_id = self._memory.read_uint64(player + 0x18)
        risk_info = self._memory.read_pointer(player + 0x28)
        name = (
            f"Player {player_id}"
            if risk_info == 0
            else self._memory.read_managed_string(self._memory.read_pointer(risk_info + 0x10)) or f"Player {player_id}"
        )
        unit_manager = self._memory.read_pointer(controller + 0x20)
        units_list = 0 if unit_manager == 0 else self._memory.read_pointer(unit_manager + 0x38)
        unit_pointers = [] if units_list == 0 else self._memory.read_list_pointers(units_list, 256)
        units = [
            unit for index, pointer in enumerate(unit_pointers) if (unit := self._read_unit(pointer, index)) is not None
        ]
        return PlayerSnapshot(
            player_id=str(player_id),
            name=name,
            team=self._read_team_index(controller),
            state=_player_state(self._memory.read_int32(player + 0x108)),
            supply=self._memory.read_int32(player + 0xEC),
            reactor_core=self._memory.read_int32(player + 0x134),
            previous_fight_result=_fight_result(self._memory.read_int32(player + 0x158)),
            units=units,
            active_technologies=self._read_active_technologies(player),
        )

    def _read_team_index(self, controller: int) -> int | None:
        team_controller = self._memory.read_pointer(controller + 0x130)
        team_system = self._memory.read_pointer(controller + 0x148)
        team_controllers_list = 0 if team_system == 0 else self._memory.read_pointer(team_system + 0x28)
        if team_controller == 0 or team_controllers_list == 0:
            return None
        team_controllers = self._memory.read_list_pointers(team_controllers_list, 8)
        return team_controllers.index(team_controller) if team_controller in team_controllers else None

    def _read_active_technologies(self, player: int) -> list[UnitTechnologySet]:
        player_agent = self._memory.read_pointer(player + 0xE0)
        managers_list = 0 if player_agent == 0 else self._memory.read_pointer(player_agent + 0x100)
        if managers_list == 0:
            return []
        result = []
        for manager in self._memory.read_list_pointers(managers_list, 256):
            if manager == 0:
                continue
            unit_id = self._memory.read_int32(manager + 0x18)
            technologies_list = self._memory.read_pointer(manager + 0x10)
            if technologies_list == 0:
                continue
            active_ids = []
            for technology in self._memory.read_list_pointers(technologies_list, 32):
                if technology == 0 or self._memory.read_byte(technology + 0x18) == 0:
                    continue
                technology_data = self._memory.read_pointer(technology + 0x10)
                technology_id = 0 if technology_data == 0 else self._memory.read_int32(technology_data + 0x10)
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
        card_data = self._memory.read_pointer(card_element + 0x10)
        map_element = self._memory.read_pointer(card_element + 0x38)
        mech_team = self._memory.read_pointer(card_element + 0x48)
        if card_data == 0 or map_element == 0 or mech_team == 0:
            return None
        unit_id = self._memory.read_int32(card_data + 0x10)
        if unit_id <= 0 or unit_id > 100_000:
            return None
        bound_x = self._memory.read_int32(map_element + 0x18)
        bound_y = self._memory.read_int32(map_element + 0x1C)
        width = self._memory.read_int32(map_element + 0x20)
        height = self._memory.read_int32(map_element + 0x24)
        raw_level = self._memory.read_int32(mech_team + 0x2C)
        experience = max(0, min(2_147_483_647, int(self._memory.read_int64(mech_team + 0x38) / 4_294_967_296)))
        equipment = self._memory.read_pointer(card_element + 0x28)
        equipment_data = 0 if equipment == 0 else self._memory.read_pointer(equipment + 0x20)
        return UnitDeployment(
            unit_id=unit_id,
            unit_name=unit_name(unit_id),
            formation_index=list_index,
            raw_level=raw_level,
            display_level=raw_level + 1,
            experience=experience,
            x=bound_x + width / 2,
            y=bound_y + height / 2,
            is_rotated=self._memory.read_byte(map_element + 0x2C) != 0,
            equipment_id=0 if equipment_data == 0 else self._memory.read_int32(equipment_data + 0x10),
            sell_supply=self._memory.read_int32(card_element + 0x60),
            round_count=self._memory.read_int32(mech_team + 0x50),
            durability=0 if equipment == 0 else self._memory.read_int32(equipment + 0x30),
        )

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


def _fight_result(value: int) -> str:
    return {0: "Win", 1: "Lose", 2: "Deuce"}.get(value, f"FightResult#{value}")


def _player_state(value: int) -> str:
    return {0: "Deploying", 1: "DeployOver", 2: "Fighting", 3: "FightOver"}.get(value, f"PlayerState#{value}")
