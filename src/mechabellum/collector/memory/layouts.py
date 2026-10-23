from dataclasses import dataclass


@dataclass(frozen=True)
class MatchOffsets:
    battle_info: int
    round_count: int
    player_manager: int


@dataclass(frozen=True)
class BattleInfoOffsets:
    battle_id: int
    map_id: int
    game_mode: int
    match_mode: int


@dataclass(frozen=True)
class PlayerControllerOffsets:
    unit_manager: int
    player: int
    team_controller: int
    team_system: int


@dataclass(frozen=True)
class PlayerOffsets:
    id: int
    risk_info: int
    player_agent: int
    supply: int
    state: int
    reactor_core: int
    max_reactor_core: int | None
    round_supply_income: int | None
    # Exactly one of these is set: older builds keep the previous result, newer ones a List<FightResult>.
    previous_fight_result: int | None
    fight_result_history: int | None


@dataclass(frozen=True)
class CardElementOffsets:
    unit_data: int
    # A single Equipment before 2.0, a List<Equipment> from 2.0 on; see `equipment_is_list`.
    equipment: int
    map_element: int
    mech_team: int
    sell_supply: int


@dataclass(frozen=True)
class MechTeamOffsets:
    level: int
    experience: int
    round_count: int


@dataclass(frozen=True)
class MemoryLayout:
    replay_version: int
    game_version: str
    game_assembly_sha256: str
    match_client_class_global_rva: int
    match: MatchOffsets
    battle_info: BattleInfoOffsets
    player_controller: PlayerControllerOffsets
    player: PlayerOffsets
    player_agent_technology_managers: int
    card_element: CardElementOffsets
    equipment_is_list: bool
    mech_team: MechTeamOffsets


# Offsets shared by every supported build.
CLASS_STATIC_FIELDS = 0xB8
MATCH_CLIENT_CURRENT = 0x08
PLAYER_MANAGER_CONTROLLERS = 0x18
RISK_INFO_NAME = 0x10
TEAM_SYSTEM_CONTROLLERS = 0x28
UNIT_MANAGER_UNITS = 0x38
TECHNOLOGY_MANAGER_TECHNOLOGIES = 0x10
TECHNOLOGY_MANAGER_UNIT_ID = 0x18
ITEM_DATA = 0x10
ACTIVABLE_ITEM_IS_ACTIVE = 0x18
GR_OBJECT_ID = 0x10
MAP_ELEMENT_BOUND = 0x18
MAP_ELEMENT_IS_ROTATE = 0x2C
EQUIPMENT_DATA = 0x20
EQUIPMENT_DURABILITY = 0x30

_BATTLE_INFO = BattleInfoOffsets(battle_id=0x18, map_id=0x34, game_mode=0x58, match_mode=0x5C)
_MATCH = MatchOffsets(battle_info=0x30, round_count=0x64, player_manager=0x70)

LAYOUT_1_11_0_2A = MemoryLayout(
    replay_version=2119,
    game_version="1.11.0.2a",
    game_assembly_sha256="0FE278BC3A1DD6FF55A51DB2807CCD73ED16A1FE390FE72FFA013F0AEFF495F1",
    match_client_class_global_rva=0x3C799F8,
    match=_MATCH,
    battle_info=_BATTLE_INFO,
    player_controller=PlayerControllerOffsets(
        unit_manager=0x20, player=0x128, team_controller=0x130, team_system=0x148
    ),
    player=PlayerOffsets(
        id=0x18,
        risk_info=0x28,
        player_agent=0xE0,
        supply=0xEC,
        state=0x108,
        reactor_core=0x134,
        max_reactor_core=None,
        round_supply_income=None,
        previous_fight_result=0x158,
        fight_result_history=None,
    ),
    player_agent_technology_managers=0x100,
    card_element=CardElementOffsets(unit_data=0x10, equipment=0x28, map_element=0x38, mech_team=0x48, sell_supply=0x60),
    equipment_is_list=False,
    mech_team=MechTeamOffsets(level=0x2C, experience=0x38, round_count=0x50),
)

LAYOUT_2_0_0_5 = MemoryLayout(
    replay_version=2340,
    game_version="2.0.0.5",
    game_assembly_sha256="0BC9CE7237E81ACB0A4B7D0819F3E05C8D4E5C299FFC2CDFCF12A3E8E5B8B493",
    match_client_class_global_rva=0x3E1C948,
    match=_MATCH,
    battle_info=_BATTLE_INFO,
    player_controller=PlayerControllerOffsets(
        unit_manager=0x30, player=0x138, team_controller=0x140, team_system=0x158
    ),
    player=PlayerOffsets(
        id=0x18,
        risk_info=0x28,
        player_agent=0xE8,
        supply=0xF4,
        state=0x110,
        reactor_core=0x13C,
        max_reactor_core=0x144,
        round_supply_income=0x14C,
        previous_fight_result=None,
        fight_result_history=0x160,
    ),
    player_agent_technology_managers=0x108,
    card_element=CardElementOffsets(unit_data=0x10, equipment=0x28, map_element=0x38, mech_team=0x48, sell_supply=0x60),
    equipment_is_list=True,
    mech_team=MechTeamOffsets(level=0x2C, experience=0x38, round_count=0x58),
)

SUPPORTED_LAYOUTS = (LAYOUT_1_11_0_2A, LAYOUT_2_0_0_5)


def find_layout(game_assembly_sha256: str) -> MemoryLayout | None:
    digest = game_assembly_sha256.upper()
    return next((layout for layout in SUPPORTED_LAYOUTS if layout.game_assembly_sha256 == digest), None)
