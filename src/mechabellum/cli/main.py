from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from ..collector import locate_game
from ..collector.replay import parse_replay, select_round
from ..contracts import MODEL_SNAPSHOT_PHASE, MatchSnapshot, snapshot_to_dict, snapshot_to_json, validate_snapshot


def main() -> int:
    _configure_console()
    parser = _parser()
    args = parser.parse_args()
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    try:
        return int(args.handler(args) or 0)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mecha", description="Mechabellum data collection, training, and win probability inference."
    )
    commands = parser.add_subparsers(dest="command")

    _command(commands, "probe", "Locate the game, replays, and logs.", _probe)
    latest = _command(commands, "latest", "Read a snapshot from the latest replay.", _latest)
    latest.add_argument("--replay-dir", type=Path)
    latest.add_argument("--round", type=int)
    latest.add_argument("--json", action="store_true")

    parse = _command(commands, "parse", "Read a snapshot from the given replay.", _parse)
    parse.add_argument("replay", type=Path)
    parse.add_argument("--round", type=int)
    parse.add_argument("--json", action="store_true")

    dump = _command(commands, "dump", "Output all standard snapshots from the given replay.", _dump)
    dump.add_argument("replay", type=Path)

    export = _command(
        commands, "export-dataset", "Export a replay directory as MatchSnapshot v2 JSONL.", _export_dataset
    )
    export.add_argument("replay_directory", type=Path, nargs="?")
    export.add_argument("--output", type=Path, required=True)

    stats = _command(
        commands,
        "dataset-stats",
        "Index a replay folder by version, drop duplicates, list abnormal matches and report distributions.",
        _dataset_stats,
    )
    stats.add_argument("replay_directory", type=Path, nargs="?")
    stats.add_argument("--list-abnormal", action="store_true", help="Also list each abnormal replay and why.")

    _command(commands, "live-probe", "Report the live memory layout and match state.", _live_probe)
    live = _command(commands, "live", "Read one live match snapshot.", _live)
    live.add_argument("--json", action="store_true")
    watch = _command(commands, "live-watch", "Continuously output live match snapshots when they change.", _live_watch)
    watch.add_argument("--interval", type=int, default=1000, help="Polling interval in milliseconds, range 250-30000.")
    watch.add_argument("--json", action="store_true")
    live_record = _command(
        commands, "live-record", "Append every distinct live snapshot to a JSONL file.", _live_record
    )
    live_record.add_argument("--output", type=Path, required=True, help="JSONL file; new snapshots are appended.")
    live_record.add_argument(
        "--interval", type=int, default=1000, help="Polling interval in milliseconds, range 250-30000."
    )
    live_record.add_argument(
        "--stop-after-idle",
        type=int,
        metavar="SECONDS",
        help="Stop once no match has been readable for this long after recording started.",
    )
    live_predict = _command(
        commands, "live-predict", "Output final win probabilities when each round's fight ends.", _live_predict
    )
    live_predict.add_argument("--interval", type=int, default=500)
    live_predict.add_argument("--model", type=Path, default=Path("artifacts/win_model.joblib"))

    fetch = _command(
        commands, "fetch-replays", "Download tournament replays through the MechaBridge mod, newest first.", _fetch_replays
    )
    fetch.add_argument(
        "--versions",
        nargs="+",
        help="Game version and replay format, such as 2.0.0.5.2340; defaults to the running game's version.",
    )
    fetch.add_argument("--stop-after", type=int, default=10, help="Stop after this many already downloaded replays in a row.")
    fetch.add_argument(
        "--full",
        action="store_true",
        help="Walk to the oldest requested version even past downloaded replays, to resume an interrupted backfill.",
    )
    fetch.add_argument("--port", type=int, help="MechaBridge WebSocket port, default 17615.")

    train = _command(commands, "train", "Train a final win probability model from MatchSnapshot JSONL.", _train)
    train.add_argument("--dataset", type=Path, required=True)
    train.add_argument("--output", type=Path, default=Path("artifacts/win_model.joblib"))
    train.add_argument("--test-size", type=float, default=0.25)
    train.add_argument("--seed", type=int, default=20260711)
    train.add_argument("--regularization", type=float)
    train.add_argument(
        "--split", choices=("group", "time"), default="group", help="Hold out random matches, or the newest ones."
    )
    train.add_argument("--calibration", choices=("none", "sigmoid", "isotonic"), default="none")
    train.add_argument(
        "--calibration-size", type=float, default=0.2, help="Share of training matches used for calibration."
    )

    deep = _command(
        commands,
        "train-deep",
        "Train a token model (Deep Sets, Transformer or GNN) over unit formations; needs the deep extra.",
        _train_deep,
    )
    deep.add_argument("--dataset", type=Path, required=True)
    deep.add_argument("--architecture", choices=("deepsets", "transformer", "gnn"), default="transformer")
    deep.add_argument("--output", type=Path, help="Defaults to artifacts/win_model_<architecture>.pt.")
    deep.add_argument("--split", choices=("group", "time"), default="group")
    deep.add_argument("--epochs", type=int, default=300)
    deep.add_argument("--seed", type=int, default=20260711)
    deep.add_argument(
        "--advantage-weight",
        type=float,
        default=0.0,
        help="Weight of the auxiliary next-fight advantage loss; 0 trains on the final result only.",
    )

    recommend = _command(
        commands,
        "recommend",
        "Rank candidate buys, upgrades, technologies, moves and cards for one player of a fight_over position.",
        _recommend,
    )
    recommend.add_argument("--input", type=Path, help="MatchSnapshot JSON; reads standard input when omitted.")
    recommend.add_argument("--player", type=int, choices=(0, 1), default=0)
    recommend.add_argument(
        "--dataset",
        type=Path,
        help="Replay dataset that fills in prices, technologies and card effects the game's tables lack.",
    )
    recommend.add_argument("--model", type=Path, default=Path("artifacts/win_model.joblib"))
    recommend.add_argument(
        "--cards",
        type=lambda text: [int(item) for item in text.split(",") if item],
        default=[],
        help="Comma-separated offered card ids.",
    )
    recommend.add_argument(
        "--round-weight", type=float, default=0.0, help="Weight of a multi-task model's predicted next-fight advantage."
    )
    recommend.add_argument("--top", type=int, default=10)

    ablate = _command(
        commands,
        "ablate",
        "Compare final-result-only and multi-task token models on calibration and card ranking.",
        _ablate,
    )
    ablate.add_argument("--dataset", type=Path, required=True)
    ablate.add_argument("--architecture", choices=("deepsets", "transformer", "gnn"), default="deepsets")
    ablate.add_argument(
        "--weights", type=lambda text: [float(item) for item in text.split(",")], default=[0.0, 0.1, 0.3, 1.0]
    )
    ablate.add_argument(
        "--round-weights", type=lambda text: [float(item) for item in text.split(",")], default=[0.0, 0.3]
    )
    ablate.add_argument("--split", choices=("group", "time"), default="group")
    ablate.add_argument("--output-directory", type=Path, default=Path("artifacts/ablation"))

    evaluate = _command(
        commands,
        "evaluate",
        "Report a saved model's accuracy and calibration on a dataset, by round, map, version, mode and rating tier.",
        _evaluate,
    )
    evaluate.add_argument("dataset", type=Path)
    evaluate.add_argument("--model", type=Path, default=Path("artifacts/win_model.joblib"))

    predict = _command(commands, "predict", "Compute final win probabilities for one MatchSnapshot.", _predict)
    predict.add_argument("--input", type=Path, help="JSON file; reads standard input when omitted.")
    predict.add_argument("--model", type=Path, default=Path("artifacts/win_model.joblib"))

    timeline = _command(commands, "timeline", "Output round-by-round win probabilities for one match.", _timeline)
    timeline.add_argument("dataset", type=Path)
    timeline.add_argument("--battle-id")
    timeline.add_argument("--model", type=Path, default=Path("artifacts/win_model.joblib"))
    return parser


def _command(subparsers: Any, name: str, help_text: str, handler: Any) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text, description=help_text)
    command.set_defaults(handler=handler)
    return command


def _configure_console() -> None:
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _probe(_: argparse.Namespace) -> None:
    locations = locate_game()
    print(f"Game directory: {locations.install_directory or 'not found'}")
    print(f"Replay directory: {locations.replay_directory or 'not found'}")
    print(f"Player log: {locations.player_log or 'not found'}")


def _latest(args: argparse.Namespace) -> None:
    directory = args.replay_dir or _require_replay_directory()
    paths = sorted(directory.glob("*.grbr"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if not paths:
        raise FileNotFoundError(f"No .grbr files in replay directory: {directory}")
    _render(select_round(parse_replay(paths[0]), args.round), args.json)


def _parse(args: argparse.Namespace) -> None:
    _render(select_round(parse_replay(args.replay), args.round), args.json)


def _dump(args: argparse.Namespace) -> None:
    replay = parse_replay(args.replay)
    snapshots = [snapshot_to_dict(select_round(replay, round_number)) for round_number in replay.snapshot_rounds]
    print(json.dumps(snapshots, ensure_ascii=False, indent=2))


def _export_dataset(args: argparse.Namespace) -> None:
    from ..datasets import export_replay_directory

    summary = export_replay_directory(args.replay_directory or _require_replay_directory(), args.output)
    for failure in summary.failures:
        print(f"Skipped: {failure}", file=sys.stderr)
    print(
        f"Export complete: replays {summary.replay_file_count}, 1v1 {summary.match_count}, "
        f"1v1 without a winner {summary.no_winner_count}, snapshots {summary.snapshot_count}, "
        f"failures {summary.failure_count}, output {args.output.resolve()}",
        file=sys.stderr,
    )


def _dataset_stats(args: argparse.Namespace) -> None:
    from ..datasets.hygiene import scan_replays

    stats = scan_replays(args.replay_directory or _require_replay_directory())
    report = stats.to_dict()
    if args.list_abnormal:
        report["abnormal"] = stats.abnormal
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _live_probe(_: argparse.Namespace) -> None:
    from ..collector.memory import LiveMemorySource

    with LiveMemorySource.attach() as source:
        print(json.dumps(source.get_status().to_dict(), ensure_ascii=False, indent=2))


def _live(args: argparse.Namespace) -> None:
    from ..collector.memory import LiveMemorySource

    with LiveMemorySource.attach() as source:
        _render(source.read_snapshot(), args.json)


def _live_watch(args: argparse.Namespace) -> None:
    from ..collector.memory import LiveMemorySource, ObserverStateError

    interval = _interval(args.interval)
    previous: str | None = None
    with LiveMemorySource.attach() as source:
        while True:
            try:
                snapshot = source.read_snapshot()
                stable = snapshot.model_copy(
                    update={"source": snapshot.source.model_copy(update={"captured_at_utc": None})}
                )
                fingerprint = snapshot_to_json(stable)
                if fingerprint != previous:
                    _render(snapshot, args.json)
                    previous = fingerprint
            except ObserverStateError as error:
                message = str(error)
                if message != previous:
                    print(message, file=sys.stderr)
                    previous = message
            time.sleep(interval)


def _live_record(args: argparse.Namespace) -> None:
    from ..collector.memory import LiveMemorySource, RecorderStats, record_live_snapshots

    interval = _interval(args.interval)
    idle_limit = args.stop_after_idle

    def should_stop(stats: RecorderStats) -> bool:
        return (
            idle_limit is not None
            and stats.last_read_at is not None
            and time.monotonic() - stats.last_read_at > idle_limit
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with LiveMemorySource.attach() as source, args.output.open("a", encoding="utf-8", newline="\n") as stream:
        try:
            stats = record_live_snapshots(
                source,
                stream,
                interval_seconds=interval,
                should_stop=should_stop,
                on_message=lambda message: print(message, file=sys.stderr, flush=True),
            )
        except KeyboardInterrupt:
            print("Recording stopped.", file=sys.stderr)
            return
    print(
        f"Recorded {stats.written} snapshots from {len(stats.matches)} match(es); "
        f"{stats.skipped_unchanged} unchanged polls skipped, {stats.read_errors} read errors retried.",
        file=sys.stderr,
    )


def _live_predict(args: argparse.Namespace) -> None:
    from ..collector.memory import LiveMemorySource, ObserverStateError
    from ..features import feature_names
    from ..inference import predict_snapshot
    from ..inference.live_history import FightOverHistory
    from ..models import load_artifact

    artifact = load_artifact(args.model, feature_names())
    history = FightOverHistory()
    emitted: set[tuple[str | None, int]] = set()
    interval = _interval(args.interval)
    with LiveMemorySource.attach() as source:
        while True:
            try:
                snapshot = source.read_snapshot()
                key = (snapshot.match.battle_id, snapshot.match.round)
                # The board is cleared when the match ends, so skip fight_over frames without units.
                ready = snapshot.match.phase == MODEL_SNAPSHOT_PHASE and all(
                    player.units for player in snapshot.players
                )
                if ready and key not in emitted:
                    emitted.add(key)
                    snapshot = history.update(snapshot)
                    print(json.dumps(predict_snapshot(artifact, snapshot, args.model), ensure_ascii=False), flush=True)
            except ObserverStateError as error:
                print(str(error), file=sys.stderr)
            time.sleep(interval)


def _fetch_replays(args: argparse.Namespace) -> int:
    from ..bridge import DEFAULT_PORT, BridgeClient
    from ..collector.tournament import fetch_replays

    if args.stop_after < 1:
        raise ValueError("--stop-after must be at least 1.")
    with BridgeClient.connect(args.port or DEFAULT_PORT) as bridge:
        status = bridge.status()
        if not status.online:
            raise RuntimeError("the game is not online; wait for it to log in at the main menu.")
        versions = args.versions or [status.game_version]
        print(f"Versions: {', '.join(versions)}  Replay directory: {status.replay_directory}", file=sys.stderr)
        summary = fetch_replays(
            bridge,
            Path(status.replay_directory),
            versions,
            None if args.full else args.stop_after,
            log=lambda line: print(line, flush=True),
        )
    print(
        f"Fetch {'failed' if summary.failed else 'complete'}: downloaded {summary.downloaded}, "
        f"already present {summary.present}, other versions {summary.skipped_version}. Stopped: {summary.stop_reason}",
        file=sys.stderr,
    )
    return 1 if summary.failed else 0


def _train(args: argparse.Namespace) -> None:
    from ..training import train_model

    metadata = train_model(
        args.dataset,
        args.output,
        test_size=args.test_size,
        seed=args.seed,
        regularization=args.regularization,
        split=args.split,
        calibration=args.calibration,
        calibration_size=args.calibration_size,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


def _train_deep(args: argparse.Namespace) -> None:
    from ..training.deep import train_token_model

    output = args.output or Path(f"artifacts/win_model_{args.architecture}.pt")
    metadata = train_token_model(
        args.dataset,
        output,
        architecture=args.architecture,
        split=args.split,
        epochs=args.epochs,
        seed=args.seed,
        advantage_weight=args.advantage_weight,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


def _recommend(args: argparse.Namespace) -> None:
    from ..datasets import load_training_snapshots
    from ..features import feature_names
    from ..inference.actions import ActionCatalog, candidate_actions, rank_actions
    from ..models import load_artifact

    data = json.load(sys.stdin) if args.input is None else json.loads(args.input.read_text(encoding="utf-8-sig"))
    snapshot = validate_snapshot(data)
    catalog = (
        ActionCatalog.from_game_data()
        if args.dataset is None
        else ActionCatalog.from_snapshots(load_training_snapshots(args.dataset))
    )
    artifact = load_artifact(args.model, feature_names())
    candidates = candidate_actions(snapshot, args.player, catalog, args.cards)
    baseline, ranked = rank_actions(artifact, snapshot, args.player, candidates, args.round_weight)
    result = {
        "player": snapshot.players[args.player].name,
        "round": snapshot.match.round,
        "baselineWinProbability": baseline,
        "candidates": len(ranked),
        "ranking": [
            {
                "kind": item.action.kind,
                "description": item.action.description,
                "parameters": item.action.parameters,
                "estimatedCost": item.action.estimated_cost,
                "winProbability": item.win_probability,
                "gain": item.gain,
            }
            for item in ranked[: args.top]
        ],
        "note": "Static model judgement of the changed board; no fight is simulated.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _ablate(args: argparse.Namespace) -> None:
    from ..training.ablation import run_ablation

    report = run_ablation(
        args.dataset,
        args.output_directory,
        architecture=args.architecture,
        advantage_weights=args.weights,
        round_weights=args.round_weights,
        split=args.split,
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "ablation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _evaluate(args: argparse.Namespace) -> None:
    from ..training import evaluate_model

    print(json.dumps(evaluate_model(args.dataset, args.model), ensure_ascii=False, indent=2))


def _predict(args: argparse.Namespace) -> None:
    from ..features import feature_names
    from ..inference import predict_snapshot
    from ..models import load_artifact

    data = json.load(sys.stdin) if args.input is None else json.loads(args.input.read_text(encoding="utf-8-sig"))
    snapshot = validate_snapshot(data)
    print(
        json.dumps(
            predict_snapshot(load_artifact(args.model, feature_names()), snapshot, args.model),
            ensure_ascii=False,
            indent=2,
        )
    )


def _timeline(args: argparse.Namespace) -> None:
    from ..inference import render_timeline

    print(json.dumps(render_timeline(args.dataset, args.model, args.battle_id), ensure_ascii=False, indent=2))


def _render(snapshot: MatchSnapshot, as_json: bool) -> None:
    if as_json:
        print(snapshot_to_json(snapshot, indent=2))
        return
    print(f"Source: {snapshot.source.uri}")
    print(
        f"Match: {snapshot.match.battle_id or 'unknown'}  Version: {snapshot.game_build.replay_version or 'unknown'}  "
        f"Map: {snapshot.match.map_id or 'unknown'}"
    )
    print(
        f"Mode: {snapshot.match.game_mode or 'unknown'}/{snapshot.match.match_mode or 'unknown'}  "
        f"Round: {snapshot.match.round}  Phase: {snapshot.match.phase}"
    )
    for player in snapshot.players:
        print(
            f"\n[{player.name}] Team={player.team if player.team is not None else '?'}  "
            f"State={player.state or '?'}  Formations={len(player.units)}  "
            f"Supply={player.supply if player.supply is not None else '?'}  "
            f"Core={player.reactor_core if player.reactor_core is not None else '?'}"
        )
        counts: dict[tuple[int, str, int], int] = {}
        for unit in player.units:
            key = (unit.unit_id, unit.unit_name, unit.display_level)
            counts[key] = counts.get(key, 0) + 1
        for (unit_id, name, level), count in sorted(counts.items()):
            print(f"  {name} [ID {unit_id}]: Lv{level} x {count}")


def _require_replay_directory() -> Path:
    replay = locate_game().replay_directory
    if replay is None:
        raise FileNotFoundError("Mechabellum replay directory not found.")
    return replay


def _interval(milliseconds: int) -> float:
    if milliseconds < 250 or milliseconds > 30_000:
        raise ValueError("interval must be between 250 and 30000 milliseconds.")
    return milliseconds / 1000
