import os
import struct

import pytest

from mechabellum.collector.memory import LiveMemorySource
from mechabellum.collector.memory.il2cpp_reader import Il2CppReader
from mechabellum.collector.memory.layouts import LAYOUT_2_0_0_5, SUPPORTED_LAYOUTS, MemoryLayout, find_layout
from mechabellum.collector.memory.windows_process import find_module, find_process_id
from mechabellum.contracts import snapshot_to_dict, validate_snapshot


class FakeMemory:
    def __init__(self, base: int = 0x1000, size: int = 0x1000) -> None:
        self.base = base
        self.data = bytearray(size)

    def write(self, address: int, value: bytes) -> None:
        offset = address - self.base
        self.data[offset : offset + len(value)] = value

    def read(self, address: int, size: int) -> bytes:
        offset = address - self.base
        return bytes(self.data[offset : offset + size])


def test_il2cpp_list_and_string_layout() -> None:
    memory = FakeMemory()
    reader = Il2CppReader(memory)  # type: ignore[arg-type]
    list_address = 0x1100
    array_address = 0x1200
    memory.write(list_address + 0x10, struct.pack("<Q", array_address))
    memory.write(list_address + 0x18, struct.pack("<i", 2))
    memory.write(array_address + 0x18, struct.pack("<Q", 4))
    memory.write(array_address + 0x20, struct.pack("<QQ", 0xABC, 0xDEF))
    assert reader.read_list_pointers(list_address, 8) == [0xABC, 0xDEF]

    string_address = 0x1300
    value = "观战"
    memory.write(string_address + 0x10, struct.pack("<i", len(value)))
    memory.write(string_address + 0x14, value.encode("utf-16-le"))
    assert reader.read_managed_string(string_address) == value


@pytest.mark.skipif(os.name != "nt", reason="Windows integration test")
def test_running_game_module_can_be_enumerated() -> None:
    process_id = find_process_id("Mechabellum.exe")
    if process_id is None:
        pytest.skip("Mechabellum is not running")
    module = find_module(process_id, "GameAssembly.dll")
    assert module is not None
    assert module.base_address > 0
    assert module.path.is_file()


class SparseMemory:
    """Byte-addressed fake process memory that allocates objects on demand."""

    def __init__(self) -> None:
        self.bytes: dict[int, int] = {}
        self.next_address = 0x10_0000

    def write(self, address: int, value: bytes) -> None:
        for offset, byte in enumerate(value):
            self.bytes[address + offset] = byte

    def read(self, address: int, size: int) -> bytes:
        return bytes(self.bytes.get(address + offset, 0) for offset in range(size))

    def allocate(self, size: int = 0x400) -> int:
        address = self.next_address
        self.next_address += size
        return address

    def pointer(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<Q", value))

    def int32(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<i", value))

    def int64(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<q", value))

    def c_string(self, value: str) -> int:
        address = self.allocate(len(value) + 1)
        self.write(address, value.encode("utf-8") + b"\0")
        return address

    def managed_string(self, value: str) -> int:
        address = self.allocate()
        self.int32(address + 0x10, len(value))
        self.write(address + 0x14, value.encode("utf-16-le"))
        return address

    def object(self, class_name: str) -> int:
        klass = self.allocate()
        self.pointer(klass + 0x10, self.c_string(class_name))
        address = self.allocate()
        self.pointer(address, klass)
        return address

    def list(self, items: list[int], *, int32: bool = False) -> int:
        item_format = "i" if int32 else "Q"
        array = self.allocate(0x20 + 8 * max(1, len(items)))
        self.write(array + 0x18, struct.pack("<Q", max(4, len(items))))
        self.write(array + 0x20, struct.pack(f"<{len(items)}{item_format}", *items))
        address = self.allocate()
        self.pointer(address + 0x10, array)
        self.int32(address + 0x18, len(items))
        return address


def _build_match(memory: SparseMemory, layout: MemoryLayout, base: int) -> None:
    match = memory.object("WatchMatch")
    match_client = memory.allocate()
    memory.pointer(match_client + 0x10, memory.c_string("MatchClient"))
    static_fields = memory.allocate()
    memory.pointer(match_client + 0xB8, static_fields)
    memory.pointer(static_fields + 0x08, match)
    memory.pointer(base + layout.match_client_class_global_rva, match_client)

    battle_info = memory.allocate()
    memory.pointer(match + layout.match.battle_info, battle_info)
    memory.pointer(battle_info + layout.battle_info.battle_id, memory.managed_string("battle-1"))
    memory.int32(battle_info + layout.battle_info.map_id, 1001)
    memory.int32(match + layout.match.round_count, 3)

    controllers = []
    for index, (name, results) in enumerate((("Alpha", [0, 1, 0]), ("Beta", [1, 0, 1]))):
        controller = memory.allocate()
        controllers.append(controller)
        player = memory.allocate()
        memory.pointer(controller + layout.player_controller.player, player)
        memory.int64(player + layout.player.id, 100 + index)
        risk_info = memory.allocate()
        memory.pointer(player + layout.player.risk_info, risk_info)
        memory.pointer(risk_info + 0x10, memory.managed_string(name))
        memory.int32(player + layout.player.state, 2)
        memory.int32(player + layout.player.supply, 50)
        memory.int32(player + layout.player.reactor_core, 3000 + index)
        if layout.player.max_reactor_core is not None:
            memory.int32(player + layout.player.max_reactor_core, 4500)
        if layout.player.round_supply_income is not None:
            memory.int32(player + layout.player.round_supply_income, 1700)
        if layout.player.fight_result_history is not None:
            # The list already holds the current round's result; the reader must drop it.
            memory.pointer(player + layout.player.fight_result_history, memory.list(results, int32=True))
        if layout.player.previous_fight_result is not None:
            memory.int32(player + layout.player.previous_fight_result, results[1])

        unit_manager = memory.allocate()
        memory.pointer(controller + layout.player_controller.unit_manager, unit_manager)
        card = memory.allocate()
        card_data = memory.allocate()
        memory.int32(card_data + 0x10, 24)
        map_element = memory.allocate()
        memory.write(map_element + 0x18, struct.pack("<iiii", -10, 100, 20, 10))
        mech_team = memory.allocate()
        memory.int32(mech_team + layout.mech_team.level, 1)
        memory.int64(mech_team + layout.mech_team.experience, 650 << 32)
        memory.int32(mech_team + layout.mech_team.round_count, 2)
        memory.pointer(card + layout.card_element.unit_data, card_data)
        memory.pointer(card + layout.card_element.map_element, map_element)
        memory.pointer(card + layout.card_element.mech_team, mech_team)
        memory.int32(card + layout.card_element.sell_supply, 300)
        equipment = []
        for equipment_id in (13030009, 13030521):
            item = memory.allocate()
            item_data = memory.allocate()
            memory.int32(item_data + 0x10, equipment_id)
            memory.pointer(item + 0x20, item_data)
            memory.int32(item + 0x30, 3)
            equipment.append(item)
        equipment_field = memory.list(equipment) if layout.equipment_is_list else equipment[0]
        memory.pointer(card + layout.card_element.equipment, equipment_field)
        memory.pointer(unit_manager + 0x38, memory.list([card]))
        if layout.player_controller.technology_manager is not None:
            _build_technology_manager(memory, controller + layout.player_controller.technology_manager)
        if layout.player_modules is not None:
            _build_player_modules(memory, layout, controller, card, equipment, chosen_id=(1071326, 107226)[index])

    player_manager = memory.allocate()
    memory.pointer(match + layout.match.player_manager, player_manager)
    memory.pointer(player_manager + 0x18, memory.list(controllers))


def _build_technology_manager(memory: SparseMemory, field: int) -> None:
    """TechnologyManager whose Dictionary<int, UnitTechnologyManager> has one unit with one active technology."""
    unit_managers = []
    for unit_id, active in ((24, True), (25, False)):
        technology = _item(memory, 10224 if active else 10225)
        memory.write(technology + 0x18, b"\x01" if active else b"\x00")
        unit_manager = memory.allocate()
        memory.pointer(unit_manager + 0x10, memory.list([technology]))
        memory.int32(unit_manager + 0x18, unit_id)
        unit_managers.append((unit_id, unit_manager))
    entries = memory.allocate()
    for index, (unit_id, unit_manager) in enumerate(unit_managers):
        entry = entries + 0x20 + index * 0x18
        memory.int32(entry + 0x08, unit_id)
        memory.pointer(entry + 0x10, unit_manager)
    dictionary = memory.allocate()
    memory.pointer(dictionary + 0x18, entries)
    memory.int32(dictionary + 0x20, len(unit_managers))
    technology_manager = memory.allocate()
    memory.pointer(technology_manager + 0x28, dictionary)
    memory.pointer(field, technology_manager)


def _item(memory: SparseMemory, item_id: int) -> int:
    item = memory.allocate()
    data = memory.allocate()
    memory.int32(data + 0x10, item_id)
    memory.pointer(item + 0x10, data)
    return item


def _build_player_modules(
    memory: SparseMemory, layout: MemoryLayout, controller: int, card: int, equipment: list[int], chosen_id: int
) -> None:
    modules = layout.player_modules
    assert modules is not None

    def manager(offset: int, items: list[int]) -> int:
        address = memory.allocate()
        memory.pointer(controller + offset, address)
        memory.pointer(address + modules.manager_items, memory.list(items))
        return address

    reinforcement = memory.allocate()
    memory.pointer(controller + modules.reinforcement_manager, reinforcement)
    offer = memory.list([_item(memory, item_id) for item_id in (107226, 1072221, 1071326, 1072119)])
    memory.pointer(reinforcement + modules.reinforcement_round_items, memory.list([offer]))
    memory.pointer(reinforcement + modules.reinforcement_chosen_items, memory.list([_item(memory, chosen_id)]))

    for item_id in (13030009,):
        inventory_item = _item(memory, item_id)
        memory.int32(inventory_item + 0x30, -1)
        manager(modules.equipment_manager, [inventory_item])
    skill = _item(memory, 900001)
    memory.int32(skill + modules.commander_skill_cooling_round, 2)
    memory.int32(skill + modules.commander_skill_get_round, 1)
    memory.write(skill + modules.commander_skill_is_active, b"\x01")
    manager(modules.commander_skill_manager, [skill])
    officers = manager(modules.officer_manager, [_item(memory, 20035)])
    memory.pointer(officers + modules.officer_invisible_items, memory.list([_item(memory, 20301)]))
    strengthened, plain = memory.allocate(), memory.allocate()
    strengthen_data = memory.allocate()
    memory.int32(strengthen_data + 0x10, 2)
    memory.pointer(strengthened + modules.tower_strengthen_data, strengthen_data)
    building_manager = memory.allocate()
    memory.pointer(controller + modules.building_manager, building_manager)
    memory.pointer(building_manager + modules.building_manager_towers, memory.list([strengthened, plain]))

    construction_manager = memory.allocate()
    memory.pointer(controller + modules.construction_manager, construction_manager)
    constructions = memory.allocate()
    memory.pointer(construction_manager + modules.construction_map, constructions)
    element = memory.allocate()
    construction_data = memory.allocate()
    memory.int32(construction_data + 0x10, 1)
    memory.pointer(element + modules.construction_data, construction_data)
    building_map_element = memory.allocate()
    memory.write(building_map_element + 0x18, struct.pack("<iiii", 110, 50, 60, 10))
    memory.pointer(element + modules.construction_map_element, building_map_element)
    memory.pointer(element + modules.construction_durabilities, memory.list([-1, -1], int32=True))
    memory.pointer(constructions + modules.sync_dictionary_values, memory.list([element]))

    contraption_manager = memory.allocate()
    memory.pointer(controller + modules.contraption_manager, contraption_manager)
    recorder = memory.allocate()
    memory.pointer(contraption_manager + modules.contraption_recorder, recorder)
    source = memory.allocate()
    contraption_data = memory.allocate()
    memory.int32(contraption_data + 0x10, 10001)
    memory.pointer(source + modules.contraption_data, contraption_data)
    record = memory.allocate()
    memory.int32(record + modules.record_index, 3)
    memory.pointer(record + modules.record_source, source)
    position = struct.unpack("<Q", struct.pack("<ii", -114, -122))[0]
    memory.pointer(record + modules.record_positions, memory.list([position]))
    memory.pointer(recorder + modules.recorder_history, memory.list([record]))

    shop_manager = memory.allocate()
    memory.pointer(controller + modules.shop_manager, shop_manager)
    shop = memory.allocate()
    memory.pointer(shop_manager + modules.shop, shop)
    memory.pointer(shop + modules.shop_unlocked_units, memory.list([card]))


@pytest.mark.parametrize("layout", SUPPORTED_LAYOUTS, ids=lambda layout: layout.game_version)
def test_live_snapshot_reads_each_layout(layout: MemoryLayout) -> None:
    memory = SparseMemory()
    base = 0x1_0000_0000
    _build_match(memory, layout, base)
    source = LiveMemorySource(1, memory, base, layout)  # type: ignore[arg-type]
    snapshot = source.read_snapshot()
    validate_snapshot(snapshot_to_dict(snapshot))

    assert snapshot.match.battle_id == "battle-1"
    assert snapshot.match.round == 3
    assert snapshot.match.phase == "battle_start"
    alpha, beta = snapshot.players
    assert (alpha.name, beta.name) == ("Alpha", "Beta")
    assert (alpha.reactor_core, alpha.supply, alpha.state) == (3000, 50, "Fighting")
    unit = alpha.units[0]
    assert (unit.unit_id, unit.display_level, unit.experience, unit.round_count) == (24, 2, 650, 2)
    assert (unit.x, unit.y, unit.sell_supply) == (0.0, 105.0, 300)
    if layout.equipment_is_list:
        assert [item.equipment_id for item in unit.equipment] == [13030009, 13030521]
        assert (alpha.max_reactor_core, alpha.round_supply_income) == (4500, 1700)
        assert alpha.fight_result_history == ["Win", "Lose"]
        assert beta.fight_result_history == ["Lose", "Win"]
    else:
        assert [(item.equipment_id, item.durability) for item in unit.equipment] == [(13030009, 3)]
        assert (alpha.max_reactor_core, alpha.round_supply_income, alpha.fight_result_history) == (None, None, None)
    if layout.player_controller.technology_manager is not None:
        assert [(t.unit_id, t.technology_ids) for t in alpha.active_technologies] == [(24, [10224])]
    if layout.player_modules is None:
        assert snapshot.match.reinforcement_offer is None
        assert (alpha.commander_skills, alpha.buildings, alpha.reinforcement_choice) == (None, None, None)
    else:
        assert snapshot.match.reinforcement_offer == [107226, 1072221, 1071326, 1072119]
        assert alpha.reinforcement_choice is not None
        assert (alpha.reinforcement_choice.item_id, alpha.reinforcement_choice.offer_index) == (1071326, 2)
        assert beta.reinforcement_choice is not None and beta.reinforcement_choice.offer_index == 0
        assert [(item.equipment_id, item.durability) for item in alpha.equipment_inventory or []] == [(13030009, -1)]
        assert [
            (s.skill_id, s.slot_index, s.acquired_round, s.cooldown_rounds, s.is_active)
            for s in alpha.commander_skills or []
        ] == [(900001, 0, 1, 2, True)]
        assert (alpha.officer_ids, alpha.blueprint_ids, alpha.energy_tower_skill_ids) == ([20301, 20035], None, None)
        assert [(b.building_id, b.x, b.y, b.durability) for b in alpha.buildings or []] == [(1, 140.0, 55.0, [-1, -1])]
        assert [(c.contraption_id, c.index, c.x, c.y) for c in alpha.contraptions or []] == [(10001, 3, -114.0, -122.0)]
        assert alpha.unlocked_unit_ids == [24]
        assert alpha.tower_strengthen_levels == [2, 0]
    assert alpha.previous_fight_result == "Lose"
    assert beta.previous_fight_result == "Win"


def test_layouts_are_selected_by_hash() -> None:
    assert find_layout(LAYOUT_2_0_0_5.game_assembly_sha256.lower()) is LAYOUT_2_0_0_5
    assert find_layout("0" * 64) is None
