from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mechabellum.visualizer import cache as cache_module
from mechabellum.visualizer import summaries as summaries_module
from mechabellum.visualizer import watcher as watcher_module
from mechabellum.visualizer.cache import CachedSummary, SummaryCache, VisualizerConfig
from mechabellum.visualizer.watcher import ReplayWatcher, replay_paths

REPLAYS = Path(__file__).parent / "fixtures" / "replays"
WIN = "2331_20261022--67509180_[Sleep Deprived]VS[miro].grbr"


def test_cache_hits_only_the_same_file_state_and_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = SummaryCache(tmp_path / "v.sqlite")
    path = tmp_path / "a.grbr"
    cache.store(path, 10, 100, CachedSummary({"battleId": "b"}, None))

    assert cache.lookup(path, 10, 100) == CachedSummary({"battleId": "b"}, None)
    assert cache.lookup(path, 11, 100) is None
    assert cache.lookup(path, 10, 101) is None
    assert cache.lookup(tmp_path / "other.grbr", 10, 100) is None
    monkeypatch.setattr(cache_module, "SUMMARY_VERSION", 999)
    assert cache.lookup(path, 10, 100) is None
    cache.close()


def test_cache_keeps_skipped_replays_and_survives_reopening(tmp_path: Path) -> None:
    cache = SummaryCache(tmp_path / "v.sqlite")
    cache.store(tmp_path / "a.grbr", 1, 2, CachedSummary(None, "no known winner"))
    cache.close()
    reopened = SummaryCache(tmp_path / "v.sqlite")
    assert reopened.lookup(tmp_path / "a.grbr", 1, 2) == CachedSummary(None, "no known winner")
    reopened.close()


def test_first_rating_per_battle_and_player_wins(tmp_path: Path) -> None:
    cache = SummaryCache(tmp_path / "v.sqlite")
    assert cache.store_rating("b1", "p1", 1500) is True
    assert cache.store_rating("b1", "p1", 1520) is False
    assert cache.store_rating("b1", "p2", 1400) is True
    assert cache.ratings() == {"b1": {"p1": 1500, "p2": 1400}}
    cache.close()


def test_config_persists_the_local_player(tmp_path: Path) -> None:
    config = VisualizerConfig(tmp_path / "visualizer.json")
    assert config.local_player_id is None
    config.set_local_player_id("281474976710829150")
    assert VisualizerConfig(tmp_path / "visualizer.json").local_player_id == "281474976710829150"
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert VisualizerConfig(tmp_path / "broken.json").local_player_id is None


def test_replay_scan_is_recursive() -> None:
    names = [path.relative_to(REPLAYS).as_posix() for path in replay_paths(REPLAYS)]
    assert "2.0.0.5.2340/2340_20261024--67160210_[Nix]VS[Sleep Deprived].grbr" in names
    assert "2.0.0.4.2331/7699235027090934905.rep.grbr" in names
    assert len(names) == 4


def test_watcher_uses_the_cache_and_waits_for_stable_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replays = tmp_path / "Replay"
    replays.mkdir()
    shutil.copy2(REPLAYS / WIN, replays / WIN)
    parsed: list[Path] = []
    real = summaries_module.summarize_replay

    def counting(path: Path, root: Path | None = None) -> dict:
        parsed.append(path)
        return real(path, root)

    monkeypatch.setattr(watcher_module, "summarize_replay", counting)
    cache = SummaryCache(tmp_path / "v.sqlite")
    seen: list[dict] = []

    first = ReplayWatcher(replays, cache, seen.append)
    assert [row["battleId"] for row in first.scan_existing()] == ["20261022--67509180"]
    assert len(parsed) == 1
    # A second start-up reads the summary from the cache.
    assert len(ReplayWatcher(replays, cache, seen.append).scan_existing()) == 1
    assert len(parsed) == 1

    # A new file is only parsed once it is unchanged over two polls.
    target = replays / "2.0.0.5.2340" / "new.grbr"
    target.parent.mkdir()
    source = (REPLAYS / "2.0.0.5.2340" / "2340_20261024--67160210_[Nix]VS[Sleep Deprived].grbr").read_bytes()
    target.write_bytes(source[:1000])
    assert first.poll() == []
    target.write_bytes(source)
    assert first.poll() == []
    rows = first.poll()
    assert [row["battleId"] for row in rows] == ["20261024--67160210"]
    assert rows[0]["gameVersion"] == "2.0.0.5.2340"
    assert seen == rows
    assert first.poll() == []
    assert len(parsed) == 2
    cache.close()


def test_watcher_records_unreadable_replays_as_skipped(tmp_path: Path) -> None:
    replays = tmp_path / "Replay"
    replays.mkdir()
    (replays / "broken.grbr").write_bytes(b"not a replay")
    shutil.copy2(REPLAYS / "2.0.0.4.2331" / "7699235027090934905.rep.grbr", replays / "cup.rep.grbr")
    cache = SummaryCache(tmp_path / "v.sqlite")
    assert ReplayWatcher(replays, cache, lambda _: None).scan_existing() == []
    stat = (replays / "cup.rep.grbr").stat()
    assert cache.lookup(replays / "cup.rep.grbr", stat.st_size, stat.st_mtime_ns) == CachedSummary(
        None, "no known winner"
    )
    broken = cache.lookup(replays / "broken.grbr", 12, (replays / "broken.grbr").stat().st_mtime_ns)
    assert broken is not None and broken.summary is None and broken.skipped_reason.startswith("unreadable")
    cache.close()
