from mechabellum.collector.unit_catalog import (
    advance_team_name,
    card_name,
    equipment_name,
    officer_name,
    technology_name,
)


def test_names_confirmed_in_a_spectated_match() -> None:
    assert officer_name(10010) == "Quick Supply Specialist"
    assert officer_name(20021) == "Aerial Specialist"


def test_tables_cover_each_kind_and_mark_unknown_ids() -> None:
    assert equipment_name(1305001) == "Charged Ammo"
    assert technology_name(201) == "Energy Shield"
    assert advance_team_name(9871) == "3 Marksman + 2 Sledgehammer"
    assert card_name(10010) == "Quick Supply Specialist"
    assert card_name(28) == "Hound"
    assert officer_name(99999999) == "Unknown specialist (99999999)"
    assert card_name(99999999) == "Unknown card (99999999)"
