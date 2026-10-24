from mechabellum.collector.memory.layouts import SUPPORTED_LAYOUTS
from mechabellum.collector.versions import application_version, application_version_key, split_application_version


def test_application_version_splits_into_game_version_and_replay_format() -> None:
    assert split_application_version("2.0.0.5.2340") == ("2.0.0.5", 2340)
    assert split_application_version("1.11.0.2a.2119") == ("1.11.0.2a", 2119)
    assert split_application_version("2.0.0.5") is None
    assert split_application_version("latest") is None


def test_application_version_key_orders_numeric_versions_only() -> None:
    assert application_version_key("2.0.0.4.2331") < application_version_key("2.0.0.5.2340")
    assert application_version_key("1.11.0.2a.2119") is None


def test_memory_layouts_round_trip_through_the_application_version() -> None:
    for layout in SUPPORTED_LAYOUTS:
        full = application_version(layout.game_version, layout.replay_version)
        assert split_application_version(full) == (layout.game_version, layout.replay_version)
