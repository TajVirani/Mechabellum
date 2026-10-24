import shutil
from pathlib import Path

from test_replay import _write_replay, _write_v2340_replay

from mechabellum.datasets.hygiene import scan_replays


def test_scan_drops_duplicates_and_flags_abnormal_matches(tmp_path: Path) -> None:
    _write_v2340_replay(tmp_path / "a.grbr")
    shutil.copy(tmp_path / "a.grbr", tmp_path / "b.grbr")  # The same match saved twice.
    _write_replay(tmp_path / "c.grbr")  # One fight_over snapshot only.
    stats = scan_replays(tmp_path)
    report = stats.to_dict()
    assert report["replayFiles"] == 3
    assert report["duplicates"] == 1
    assert report["usableMatches"] == 1
    assert stats.abnormal == {"c.grbr": ["fewer than 2 fight_over snapshots"]}
    assert report["versionIndex"] == {"2119/Normal": 1, "2340/Normal": 2}
