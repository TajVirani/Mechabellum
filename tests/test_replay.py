from pathlib import Path

from mechabellum.collector.replay import parse_replay, select_round
from mechabellum.contracts import snapshot_to_dict, validate_snapshot
from mechabellum.datasets import export_replay_directory, load_snapshots


def _write_replay(path: Path) -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<BattleRecord>
  <playerRecords>
    <PlayerRecord><id>1</id><name>A</name><data><team>0</team></data><playerRoundRecords>
      <PlayerRoundRecord><round>1</round><playerData><reactorCore>4500</reactorCore><supply>100</supply><preRoundFightResult>Win</preRoundFightResult><units>
        <NewUnitData><id>3</id><Index>0</Index><RoundCount>0</RoundCount><Durability>0</Durability><Exp>12</Exp><Level>0</Level><Position><x>-20</x><y>-150</y></Position><EquipmentID>0</EquipmentID><IsRotate>false</IsRotate><SellSupply>400</SellSupply></NewUnitData>
      </units><activeTechnologies><UnitData><id>3</id><techs><tech data="30101" /></techs></UnitData></activeTechnologies></playerData></PlayerRoundRecord>
    </playerRoundRecords></PlayerRecord>
    <PlayerRecord><id>2</id><name>B</name><data><team>1</team></data><playerRoundRecords>
      <PlayerRoundRecord><round>1</round><playerData><reactorCore>4300</reactorCore><supply>50</supply><preRoundFightResult>Lose</preRoundFightResult><units /><activeTechnologies /></playerData></PlayerRoundRecord>
    </playerRoundRecords></PlayerRecord>
  </playerRecords>
  <matchDatas><MatchSnapshotData><lastFightResult><Reports><FightReport><Score>500</Score></FightReport><FightReport><Score>0</Score></FightReport></Reports></lastFightResult></MatchSnapshotData></matchDatas>
  <Version>2119</Version>
  <BattleInfo><BattleID>fixture-battle</BattleID><MapID>1001</MapID><GameMode>Normal</GameMode><MatchMode>VS_1_1</MatchMode></BattleInfo>
</BattleRecord>"""
    path.write_bytes(b"binary-prefix" + xml.encode("utf-8") + b"binary-suffix")


def test_replay_parser_outputs_contract(tmp_path: Path) -> None:
    replay_path = tmp_path / "fixture.grbr"
    _write_replay(replay_path)
    replay = parse_replay(replay_path)
    snapshot = select_round(replay, 1)
    assert replay.winner_index == 0
    assert snapshot.players[0].units[0].unit_id == 3
    assert snapshot.outcome is not None and snapshot.outcome.winner_name == "A"
    validate_snapshot(snapshot_to_dict(snapshot))


def test_dataset_export_uses_replay_parser(tmp_path: Path) -> None:
    _write_replay(tmp_path / "fixture.grbr")
    output = tmp_path / "snapshots.jsonl"
    summary = export_replay_directory(tmp_path, output)
    snapshots = load_snapshots(output)
    assert summary.snapshot_count == 1
    assert summary.failure_count == 0
    assert snapshots[0].match.battle_id == "fixture-battle"


def _round_record(round_number: int, extra: str = "", actions: str = "") -> str:
    return (
        f"<PlayerRoundRecord><round>{round_number}</round><actionRecords>{actions}</actionRecords>"
        f"<playerData><reactorCore>4000</reactorCore><supply>0</supply>{extra}<units /><activeTechnologies />"
        "</playerData></PlayerRoundRecord>"
    )


def _write_v2340_replay(path: Path) -> None:
    full_history_a = "".join(f"<FightResultType>{value}</FightResultType>" for value in ("Win", "Lose", "Win"))
    full_history_b = "".join(f"<FightResultType>{value}</FightResultType>" for value in ("Lose", "Win", "Lose"))
    choose = (
        '<MatchActionData xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="PAD_ChooseReinforceItem">'
        "<ID>{item}</ID><Index>{index}</Index></MatchActionData>"
    )
    unit = (
        "<units><NewUnitData><id>7</id><Index>0</Index><Exp>0</Exp><Level>0</Level>"
        "<Position><x>0</x><y>-100</y></Position><EquipmentID>0</EquipmentID><Durability>0</Durability>"
        "<SellSupply>200</SellSupply><equipments><equipment data=\"13030009\" /><equipment data=\"13030521\" />"
        "</equipments></NewUnitData></units>"
    )

    def records(history: str, choice: str) -> str:
        extra = (
            f"<roundFightResult>{history}</roundFightResult><preRoundFightResult>Win</preRoundFightResult>"
            "<officers><int>20032</int></officers><bluepints><int>2</int></bluepints>"
            "<commanderSkills><CommanderSkillData><index>1</index><id>300001</id><isActive>false</isActive>"
            "<coolingRound>2</coolingRound><getRound>2</getRound></CommanderSkillData></commanderSkills>"
            "<equipmentDatas><EquipmentData><id>13030009</id><durability>-1</durability></EquipmentData></equipmentDatas>"
        )
        rounds = [_round_record(number, extra) for number in (1, 2)]
        rounds.append(_round_record(3, extra, choice).replace("<units />", unit))
        return "".join(rounds)

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<BattleRecord>
  <playerRecords>
    <PlayerRecord><id>1</id><name>A</name><data><team>0</team></data><playerRoundRecords>{records(full_history_a, choose.format(item=300001, index=1))}</playerRoundRecords></PlayerRecord>
    <PlayerRecord><id>2</id><name>B</name><data><team>0</team></data><playerRoundRecords>{records(full_history_b, choose.format(item=0, index=-1))}</playerRoundRecords></PlayerRecord>
  </playerRecords>
  <matchDatas>
    <MatchSnapshotData><round>3</round><reinforceItems><ArrayOfInt><int>1200002</int><int>300001</int><int>10008</int><int>1200003</int></ArrayOfInt></reinforceItems>
      <lastFightResult><Reports><FightReport><Score>500</Score></FightReport><FightReport><Score>0</Score></FightReport></Reports></lastFightResult></MatchSnapshotData>
  </matchDatas>
  <Version>2340</Version>
  <BattleInfo><BattleID>fixture-2340</BattleID><MapID>1001</MapID><GameMode>Normal</GameMode><MatchMode>VS_1_1</MatchMode></BattleInfo>
</BattleRecord>"""
    path.write_bytes(b"binary-prefix" + xml.encode("utf-8") + b"binary-suffix")


def test_full_history_is_truncated_to_completed_fights(tmp_path: Path) -> None:
    _write_v2340_replay(tmp_path / "fixture.grbr")
    replay = parse_replay(tmp_path / "fixture.grbr")
    first = select_round(replay, 1).players[0]
    assert first.fight_result_history == []
    assert first.previous_fight_result is None
    third = select_round(replay, 3)
    assert third.players[0].fight_result_history == ["Win", "Lose"]
    # preRoundFightResult is "Win" for everyone in 2340 replays and must not be used.
    assert third.players[0].previous_fight_result == "Lose"
    assert third.players[1].previous_fight_result == "Win"
    assert third.players[1].fight_result_history == ["Lose", "Win"]


def test_v2_replay_fields(tmp_path: Path) -> None:
    _write_v2340_replay(tmp_path / "fixture.grbr")
    snapshot = select_round(parse_replay(tmp_path / "fixture.grbr"), 3)
    player_a, player_b = snapshot.players
    assert [item.equipment_id for item in player_a.units[0].equipment] == [13030009, 13030521]
    assert all(item.durability is None for item in player_a.units[0].equipment)
    assert player_a.equipment_inventory is not None and player_a.equipment_inventory[0].durability == -1
    assert player_a.team is None and player_b.team is None
    assert player_a.state == "Fighting"
    assert snapshot.match.reinforcement_offer == [1200002, 300001, 10008, 1200003]
    assert player_a.reinforcement_choice is not None
    assert (player_a.reinforcement_choice.status, player_a.reinforcement_choice.item_id) == ("chosen", 300001)
    assert player_b.reinforcement_choice is not None and player_b.reinforcement_choice.status == "declined"
    assert player_a.officer_ids == [20032]
    assert player_a.blueprint_ids == [2]
    assert player_a.commander_skills is not None and player_a.commander_skills[0].skill_id == 300001
    # Sections absent from the XML are unknown, not empty.
    assert player_a.buildings is None and player_a.unlocked_unit_ids is None
    validate_snapshot(snapshot_to_dict(snapshot))


def test_legacy_history_and_equipment(tmp_path: Path) -> None:
    replay_path = tmp_path / "fixture.grbr"
    _write_replay(replay_path)
    xml = replay_path.read_bytes().replace(b"<EquipmentID>0</EquipmentID>", b"<EquipmentID>13010001</EquipmentID>")
    xml = xml.replace(b"<Durability>0</Durability>", b"<Durability>3</Durability>")
    replay_path.write_bytes(xml)
    snapshot = select_round(parse_replay(replay_path), 1)
    assert [(item.equipment_id, item.durability) for item in snapshot.players[0].units[0].equipment] == [(13010001, 3)]
    assert snapshot.players[0].team == 0 and snapshot.players[1].team == 1
    assert snapshot.players[0].previous_fight_result is None
    assert snapshot.match.reinforcement_offer is None
