from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from mechabellum.collector.replay.result import result_path, write_result
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
    monkeypatch.setattr(cache_module, "SUMMARY_CACHE_KEY", "v999-0")
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
    _copy_replay(REPLAYS / WIN, replays / WIN)
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


def test_watcher_reparses_a_replay_when_its_result_file_arrives(tmp_path: Path) -> None:
    replays = tmp_path / "Replay"
    replays.mkdir()
    cup = replays / "cup.rep.grbr"
    shutil.copy2(REPLAYS / "2.0.0.4.2331" / "7699235027090934905.rep.grbr", cup)
    cache = SummaryCache(tmp_path / "v.sqlite")
    watcher = ReplayWatcher(replays, cache, lambda _: None)
    assert watcher.scan_existing() == []
    write_result(cup, 281474976711589755, 281474976711565323, "test")
    assert watcher.poll() == []
    rows = watcher.poll()
    assert len(rows) == 1 and rows[0]["winnerIndex"] in {0, 1}
    # A restart reads the labelled summary from the cache.
    assert len(ReplayWatcher(replays, cache, lambda _: None).scan_existing()) == 1
    cache.close()


def test_restart_rechecks_a_skipped_replay_whose_result_file_arrived_while_stopped(tmp_path: Path) -> None:
    """A "no known winner" entry cached before the result file existed is re-read at the next start-up, even
    when the result file keeps an older mtime than the replay (copied with its times preserved)."""
    replays = tmp_path / "Replay" / "2.0.0.4.2331"
    replays.mkdir(parents=True)
    source = REPLAYS / "2.0.0.4.2331" / "7699235027090934905.rep.grbr"
    cup = replays / source.name
    shutil.copy2(source, cup)
    cache = SummaryCache(tmp_path / "v.sqlite")
    assert ReplayWatcher(tmp_path / "Replay", cache, lambda _: None).scan_existing() == []
    assert cache.lookup(cup, *_state(cup)) == CachedSummary(None, "no known winner")

    write_result(cup, 281474976711589755, 281474976711565323, "test")
    replay_mtime_ns = cup.stat().st_mtime_ns
    os.utime(result_path(cup), ns=(replay_mtime_ns - 10**9, replay_mtime_ns - 10**9))

    rows = ReplayWatcher(tmp_path / "Replay", cache, lambda _: None).scan_existing()
    assert len(rows) == 1 and rows[0]["winnerIndex"] in {0, 1}
    assert rows[0]["gameMode"] == "Competition"
    cache.close()


def test_cache_key_follows_the_data_files() -> None:
    key = summaries_module.summary_cache_key(1, b"roles", b"names", b"versions")
    assert key.startswith("v1-") and not key.replace("-", "").isdigit()
    assert summaries_module.summary_cache_key(1, b"roles", b"names", b"versions") == key
    assert summaries_module.summary_cache_key(1, b"roles changed", b"names", b"versions") != key
    assert summaries_module.summary_cache_key(1, b"roles", b"names", b"versions 2") != key
    assert summaries_module.summary_cache_key(2, b"roles", b"names", b"versions") != key
    assert cache_module.SUMMARY_CACHE_KEY == summaries_module.SUMMARY_CACHE_KEY


def test_watcher_resends_the_full_set_when_a_replay_is_deleted(tmp_path: Path) -> None:
    replays = tmp_path / "Replay"
    replays.mkdir()
    _copy_replay(REPLAYS / WIN, replays / WIN)
    nix = "2340_20261024--67160210_[Nix]VS[Sleep Deprived].grbr"
    shutil.copy2(REPLAYS / "2.0.0.5.2340" / nix, replays / nix)
    cache = SummaryCache(tmp_path / "v.sqlite")
    upserts: list[dict] = []
    full_sets: list[list[dict]] = []
    watcher = ReplayWatcher(replays, cache, upserts.append, on_summaries=full_sets.append)
    assert len(watcher.scan_existing()) == 2
    stat = (replays / nix).stat()
    (replays / nix).unlink()
    watcher.poll()
    assert upserts == []
    assert [[row["battleId"] for row in rows] for rows in full_sets] == [["20261022--67509180"]]
    assert cache.lookup(replays / nix, stat.st_size, stat.st_mtime_ns) is None
    watcher.poll()
    assert len(full_sets) == 1
    cache.close()


def test_watcher_thread_survives_a_failing_poll(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlite3
    import threading

    cache = SummaryCache(tmp_path / "v.sqlite")
    watcher = ReplayWatcher(tmp_path, cache, lambda _: None, interval_seconds=0.01)
    calls: list[int] = []
    second = threading.Event()

    def poll() -> list:
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        second.set()
        return []

    monkeypatch.setattr(watcher, "poll", poll)
    watcher.start()
    assert second.wait(5), "the watcher stopped after a failing poll"
    watcher.stop(timeout=5)
    assert watcher._thread is not None and not watcher._thread.is_alive()
    cache.close()


def test_scan_reports_cached_rows_first_then_parsed_batches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replays = tmp_path / "Replay"
    shutil.copytree(REPLAYS, replays)
    cache = SummaryCache(tmp_path / "v.sqlite")
    # Warm the cache with one replay only.
    warm = tmp_path / "Warm"
    warm.mkdir()
    _copy_replay(replays / WIN, warm / WIN)
    ReplayWatcher(warm, cache, lambda _: None).scan_existing()
    cache.store(replays / WIN, *_state(replays / WIN), cache.lookup(warm / WIN, *_state(warm / WIN)))
    monkeypatch.setattr(watcher_module, "INDEX_BATCH_SECONDS", 0.0)

    calls: list[tuple[list[str], int, int, bool]] = []
    watcher = ReplayWatcher(replays, cache, lambda _: None)
    rows = watcher.scan_existing(
        lambda rows, done, total, replace: calls.append(([r["battleId"] for r in rows], done, total, replace))
    )

    assert calls[0] == (["20261022--67509180"], 1, 4, True)
    # Then one call per parsed file (the batch window is 0), the last one at done == total.
    assert [call[1:] for call in calls[1:]] == [(2, 4, False), (3, 4, False), (4, 4, False)]
    assert sorted(battle for call in calls for battle in call[0]) == sorted(row["battleId"] for row in rows)
    assert len(rows) == 3
    assert watcher.indexed.is_set()
    cache.close()


def _copy_replay(source: Path, target: Path) -> None:
    """Copy a replay with its result file, which names the winner of a 2331 replay that doesn't record it."""
    shutil.copy2(source, target)
    if result_path(source).is_file():
        shutil.copy2(result_path(source), result_path(target))


def _state(path: Path) -> tuple[int, int]:
    """The watcher's (size, mtime) of a replay: a result file beside it counts as a change."""
    return watcher_module.replay_state(path)
