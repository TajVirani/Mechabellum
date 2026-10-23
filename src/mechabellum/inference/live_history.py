from __future__ import annotations

from ..contracts import MODEL_SNAPSHOT_PHASE, MatchSnapshot


class FightOverHistory:
    """Builds per-fight core and supply histories from the live fight_over frames of one match.

    Live memory only shows the current values. A fight_over frame of round r holds exactly what a replay records
    after fight r, so collecting one frame per round reproduces the replay's histories. The histories are only
    filled when every fight from round 1 was observed; otherwise they stay null, as for a replay with missing
    records.
    """

    def __init__(self) -> None:
        self._battle_id: str | None = None
        self._values: dict[int, dict[str, tuple[int | None, int | None]]] = {}

    def update(self, snapshot: MatchSnapshot) -> MatchSnapshot:
        if snapshot.match.battle_id != self._battle_id:
            self._battle_id = snapshot.match.battle_id
            self._values = {}
        if snapshot.match.phase != MODEL_SNAPSHOT_PHASE:
            return snapshot
        round_number = snapshot.match.round
        self._values.setdefault(
            round_number,
            {
                _key(index, player): (player.reactor_core, player.supply)
                for index, player in enumerate(snapshot.players)
            },
        )
        players = []
        for index, player in enumerate(snapshot.players):
            key = _key(index, player)
            rounds = [self._values.get(number, {}).get(key) for number in range(1, round_number + 1)]
            cores = [None if item is None else item[0] for item in rounds]
            supplies = [None if item is None else item[1] for item in rounds]
            players.append(
                player.model_copy(
                    update={
                        "reactor_core_history": player.reactor_core_history
                        if None in cores
                        else [value for value in cores if value is not None],
                        "supply_history": player.supply_history
                        if None in supplies
                        else [value for value in supplies if value is not None],
                    }
                )
            )
        return snapshot.model_copy(update={"players": players})


def _key(index: int, player: object) -> str:
    player_id = getattr(player, "player_id", None)
    return str(player_id) if player_id is not None else f"#{index}"
