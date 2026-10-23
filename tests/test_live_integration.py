import os

import pytest

from mechabellum.collector.memory import LiveMemorySource


@pytest.mark.skipif(os.name != "nt", reason="Windows integration test")
def test_live_root_matches_supported_layout() -> None:
    try:
        source = LiveMemorySource.attach()
    except RuntimeError as error:
        if "not running" in str(error):
            pytest.skip("Mechabellum is not running")
        raise
    with source:
        status = source.get_status()
        assert status.layout_replay_version == 2119
        assert status.root_class == "MatchClient"
