from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from ...contracts import (
    Building,
    CommanderSkill,
    Contraption,
    EquipmentItem,
    FightResult,
    GameBuild,
    MatchInfo,
    MatchSnapshot,
    PlayerSnapshot,
    PlayerState,
    ReinforcementChoice,
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
    TECHNOLOGY_MANAGER_MAP,
    TECHNOLOGY_MANAGER_TECHNOLOGIES,
    TECHNOLOGY_MANAGER_UNIT_ID,
    UNIT_MANAGER_UNITS,
    MemoryLayout,
    PlayerModuleOffsets,
    find_layout,
)
from .windows_process import WindowsProcessMemory, find_module, find_process_id

MAX_EQUIPMENT_PER_UNIT = 8
MAX_ROUNDS = 128
MAX_MODULE_ITEMS = 256


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
        controllers = [controller for controller in controllers if controller != 0]
        # Every player is dealt the same offer; a disagreement means the read is not trustworthy.
        offers = [self._read_reinforcement_offer(controller) for controller in controllers]
        offer = offers[0] if all(item == offers[0] for item in offers) else None
        players = [self._read_player(controller, round_number, offer) for controller in controllers]
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
                reinforcement_offer=offer,
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

    def _read_player(self, controller: int, round_number: int, offer: list[int] | None) -> PlayerSnapshot:
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
        state = _player_state(self._memory.read_int32(player + offsets.state))
        history, previous = self._read_fight_results(player, round_number, state)
        modules = self._layout.player_modules
        return PlayerSnapshot(
            player_id=str(player_id),
            name=name,
            team=self._read_team_index(controller),
            rating=self._read_optional_int32(player, offsets.elo_score),
            state=state,
            supply=self._memory.read_int32(player + offsets.supply),
            reactor_core=self._memory.read_int32(player + offsets.reactor_core),
            max_reactor_core=self._read_optional_int32(player, offsets.max_reactor_core),
            round_supply_income=self._read_optional_int32(player, offsets.round_supply_income),
            previous_fight_result=previous,
            fight_result_history=history,
            units=units,
            active_technologies=self._read_active_technologies(controller, player),
            equipment_inventory=None if modules is None else self._read_equipment_inventory(controller, modules),
            commander_skills=None if modules is None else self._read_commander_skills(controller, modules),
            officer_ids=None if modules is None else self._read_officer_ids(controller, modules),
            buildings=None if modules is None else self._read_buildings(controller, modules),
            contraptions=None if modules is None else self._read_contraptions(controller, modules),
            # Memory holds every blueprint and energy tower skill with an active flag, but neither the full lists
            # nor the active subsets match what replays record, so these stay unknown.
            blueprint_ids=None,
            energy_tower_skill_ids=None,
            tower_strengthen_levels=None
            if modules is None
            else self._read_tower_strengthen_levels(controller, modules),
            unlocked_unit_ids=None if modules is None else self._read_unlocked_unit_ids(controller, modules),
            reinforcement_choice=None if modules is None else self._read_reinforcement_choice(controller, offer),
        )

    def _read_optional_int32(self, address: int, offset: int | None) -> int | None:
        return None if offset is None else self._memory.read_int32(address + offset)

    def _module_items(self, controller: int, manager_offset: int, list_offset: int | None = None) -> list[int]:
        """Pointers in a PlayerController manager's item list (by default the list at `manager_items`)."""
        modules = self._layout.player_modules
        manager = self._memory.read_pointer(controller + manager_offset)
        if modules is None or manager == 0:
            return []
        offset = modules.manager_items if list_offset is None else list_offset
        items = self._memory.read_list_pointers(self._memory.read_pointer(manager + offset), MAX_MODULE_ITEMS)
        return [item for item in items if item != 0]

    def _item_id(self, item: int) -> int:
        item_data = self._memory.read_pointer(item + ITEM_DATA)
        return 0 if item_data == 0 else self._memory.read_int32(item_data + GR_OBJECT_ID)

    def _read_officer_ids(self, controller: int, modules: PlayerModuleOffsets) -> list[int]:
        # Replays list the hidden officers first, then the visible ones; keep that order.
        officers = self._module_items(controller, modules.officer_manager, modules.officer_invisible_items)
        officers += self._module_items(controller, modules.officer_manager)
        return [officer_id for officer in officers if (officer_id := self._item_id(officer)) > 0]

    def _read_tower_strengthen_levels(self, controller: int, modules: PlayerModuleOffsets) -> list[int]:
        # A tower's strengthen data id is its level; towers that were never strengthened have none.
        levels = []
        for tower in self._module_items(controller, modules.building_manager, modules.building_manager_towers):
            strengthen = self._memory.read_pointer(tower + modules.tower_strengthen_data)
            levels.append(0 if strengthen == 0 else self._memory.read_int32(strengthen + GR_OBJECT_ID))
        return levels

    def _read_equipment_inventory(self, controller: int, modules: PlayerModuleOffsets) -> list[EquipmentItem]:
        return [
            EquipmentItem(equipment_id=item_id, durability=self._memory.read_int32(item + EQUIPMENT_DURABILITY))
            for item in self._module_items(controller, modules.equipment_manager)
            if (item_id := self._item_id(item)) > 0
        ]

    def _read_commander_skills(self, controller: int, modules: PlayerModuleOffsets) -> list[CommanderSkill]:
        return [
            CommanderSkill(
                skill_id=skill_id,
                slot_index=slot,
                acquired_round=self._memory.read_int32(skill + modules.commander_skill_get_round),
                cooldown_rounds=self._memory.read_int32(skill + modules.commander_skill_cooling_round),
                is_active=self._memory.read_byte(skill + modules.commander_skill_is_active) != 0,
            )
            for slot, skill in enumerate(self._module_items(controller, modules.commander_skill_manager))
            if (skill_id := self._item_id(skill)) > 0
        ]

    def _read_buildings(self, controller: int, modules: PlayerModuleOffsets) -> list[Building]:
        manager = self._memory.read_pointer(controller + modules.construction_manager)
        constructions = 0 if manager == 0 else self._memory.read_pointer(manager + modules.construction_map)
        if constructions == 0:
            return []
        elements = self._memory.read_list_pointers(
            self._memory.read_pointer(constructions + modules.sync_dictionary_values), MAX_MODULE_ITEMS
        )
        buildings = []
        for element in elements:
            data = 0 if element == 0 else self._memory.read_pointer(element + modules.construction_data)
            map_element = 0 if element == 0 else self._memory.read_pointer(element + modules.construction_map_element)
            building_id = 0 if data == 0 else self._memory.read_int32(data + GR_OBJECT_ID)
            if building_id <= 0 or map_element == 0:
                continue
            x, y = self._read_bound_center(map_element)
            buildings.append(
                Building(
                    building_id=building_id,
                    index=self._memory.read_int32(element + modules.construction_combination_index),
                    x=x,
                    y=y,
                    durability=self._memory.read_list_int32(
                        self._memory.read_pointer(element + modules.construction_durabilities), MAX_MODULE_ITEMS
                    ),
                )
            )
        return buildings

    def _read_contraptions(self, controller: int, modules: PlayerModuleOffsets) -> list[Contraption]:
        manager = self._memory.read_pointer(controller + modules.contraption_manager)
        recorder = 0 if manager == 0 else self._memory.read_pointer(manager + modules.contraption_recorder)
        if recorder == 0:
            return []
        records = [
            record
            for offset in (modules.recorder_history, modules.recorder_current)
            for record in self._memory.read_list_pointers(
                self._memory.read_pointer(recorder + offset), MAX_MODULE_ITEMS
            )
            if record != 0
        ]
        contraptions = []
        for record in records:
            source = self._memory.read_pointer(record + modules.record_source)
            data = 0 if source == 0 else self._memory.read_pointer(source + modules.contraption_data)
            contraption_id = 0 if data == 0 else self._memory.read_int32(data + GR_OBJECT_ID)
            # Positions is a List<Vector2Int>; each 8-byte element packs x then y.
            positions = self._memory.read_list_pointers(
                self._memory.read_pointer(record + modules.record_positions), MAX_MODULE_ITEMS
            )
            if contraption_id <= 0 or not positions:
                continue
            x, y = (_signed_int32(positions[0] & 0xFFFF_FFFF), _signed_int32(positions[0] >> 32))
            contraptions.append(
                Contraption(
                    contraption_id=contraption_id,
                    index=self._memory.read_int32(record + modules.record_index),
                    x=float(x),
                    y=float(y),
                )
            )
        return contraptions

    def _read_unlocked_unit_ids(self, controller: int, modules: PlayerModuleOffsets) -> list[int]:
        manager = self._memory.read_pointer(controller + modules.shop_manager)
        shop = 0 if manager == 0 else self._memory.read_pointer(manager + modules.shop)
        if shop == 0:
            return []
        unit_ids = []
        for card in self._memory.read_list_pointers(
            self._memory.read_pointer(shop + modules.shop_unlocked_units), MAX_MODULE_ITEMS
        ):
            card_data = 0 if card == 0 else self._memory.read_pointer(card + self._layout.card_element.unit_data)
            unit_id = 0 if card_data == 0 else self._memory.read_int32(card_data + GR_OBJECT_ID)
            if unit_id > 0:
                unit_ids.append(unit_id)
        return unit_ids

    def _read_reinforcement_offer(self, controller: int) -> list[int] | None:
        """The card offer dealt this round: the last list in roundReinforceItems; [] when there is none."""
        modules = self._layout.player_modules
        manager = 0 if modules is None else self._memory.read_pointer(controller + modules.reinforcement_manager)
        if modules is None or manager == 0:
            return None
        rounds = self._memory.read_list_pointers(
            self._memory.read_pointer(manager + modules.reinforcement_round_items), MAX_ROUNDS
        )
        if not rounds or rounds[-1] == 0:
            return []
        return [self._item_id(item) for item in self._memory.read_list_pointers(rounds[-1], MAX_MODULE_ITEMS) if item]

    def _read_reinforcement_choice(self, controller: int, offer: list[int] | None) -> ReinforcementChoice | None:
        """This round's pick from the shared offer; null while nothing is picked or the pick is not in the offer."""
        modules = self._layout.player_modules
        manager = 0 if modules is None else self._memory.read_pointer(controller + modules.reinforcement_manager)
        if modules is None or manager == 0 or not offer:
            return None
        chosen = [
            self._item_id(item)
            for item in self._memory.read_list_pointers(
                self._memory.read_pointer(manager + modules.reinforcement_chosen_items), MAX_MODULE_ITEMS
            )
            if item
        ]
        if not chosen or chosen[-1] not in offer:
            return None
        return ReinforcementChoice(status="chosen", item_id=chosen[-1], offer_index=offer.index(chosen[-1]))

    def _read_bound_center(self, map_element: int) -> tuple[float, float]:
        bound_x = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND)
        bound_y = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND + 0x04)
        width = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND + 0x08)
        height = self._memory.read_int32(map_element + MAP_ELEMENT_BOUND + 0x0C)
        return bound_x + width / 2, bound_y + height / 2

    def _read_fight_results(
        self, player: int, round_number: int, state: PlayerState
    ) -> tuple[list[FightResult] | None, FightResult | None]:
        offsets = self._layout.player
        if offsets.fight_result_history is not None:
            values = self._memory.read_list_int32(
                self._memory.read_pointer(player + offsets.fight_result_history), MAX_ROUNDS
            )
            results = [_fight_result(value) for value in values]
            # The list holds the current round's result as soon as the fight starts; only count finished fights.
            completed = round_number if state == "FightOver" else max(0, round_number - 1)
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

    def _technology_managers(self, controller: int, player: int) -> list[int]:
        technology_manager_offset = self._layout.player_controller.technology_manager
        if technology_manager_offset is not None:
            technology_manager = self._memory.read_pointer(controller + technology_manager_offset)
            return (
                []
                if technology_manager == 0
                else self._memory.read_dictionary_int_key_pointer_values(
                    self._memory.read_pointer(technology_manager + TECHNOLOGY_MANAGER_MAP), 256
                )
            )
        player_agent = self._memory.read_pointer(player + self._layout.player.player_agent)
        managers_list = (
            0
            if player_agent == 0
            else self._memory.read_pointer(player_agent + self._layout.player_agent_technology_managers)
        )
        return [] if managers_list == 0 else self._memory.read_list_pointers(managers_list, 256)

    def _read_active_technologies(self, controller: int, player: int) -> list[UnitTechnologySet]:
        result = []
        for manager in self._technology_managers(controller, player):
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
        x, y = self._read_bound_center(map_element)
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
            x=x,
            y=y,
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


def _signed_int32(value: int) -> int:
    return value - (1 << 32) if value >= 1 << 31 else value


def _fight_result(value: int) -> FightResult | None:
    results: dict[int, FightResult] = {0: "Win", 1: "Lose", 2: "Deuce"}
    return results.get(value)


def _player_state(value: int) -> PlayerState:
    states: dict[int, PlayerState] = {0: "Deploying", 1: "DeployOver", 2: "Fighting", 3: "FightOver"}
    return states.get(value, "Unknown")
