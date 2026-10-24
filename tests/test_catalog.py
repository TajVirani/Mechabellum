from mechabellum.collector.unit_catalog import (
    TECHNOLOGY_SUPPLY,
    UNIT_NAMES,
    UNIT_PRICES,
    advance_team_name,
    blueprint_name,
    card_name,
    commander_skill_name,
    energy_tower_skill_name,
    equipment_name,
    map_name,
    officer_name,
    technology_name,
)


def test_names_confirmed_in_a_spectated_match() -> None:
    assert officer_name(10010) == "Quick Supply Specialist"
    assert officer_name(20021) == "Aerial Specialist"
    assert map_name(1031) == "Railway Town - Dusk"


def test_tables_cover_each_kind() -> None:
    assert equipment_name(13030521) == "Secondary Laser Sight"
    assert technology_name(1001) == "Barrier"
    assert commander_skill_name(300001) == "Missile Strike"
    assert blueprint_name(401) == "Attack Enhancement II"
    assert energy_tower_skill_name(1) == "Rapid Resupply"
    assert advance_team_name(9871) == "3 Marksman + 2 Sledgehammer"
    assert advance_team_name(10010) == "Quick Supply Specialist"
    assert card_name(102212) == "2 Marksman (level 1)"
    assert card_name(28) == "Hound"


def test_prices_cover_every_unit() -> None:
    assert set(UNIT_PRICES) == set(UNIT_NAMES)
    assert UNIT_PRICES[28]["supply"] == 100
    assert TECHNOLOGY_SUPPLY[1001] == 500


def test_unknown_ids_are_marked() -> None:
    assert officer_name(99999999) == "Unknown specialist (99999999)"
    assert card_name(99999999) == "Unknown card (99999999)"
