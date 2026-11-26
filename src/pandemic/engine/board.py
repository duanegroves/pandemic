"""Low-level board mutations shared by actions, roles and events."""

from __future__ import annotations

from pandemic.data.cards import CUBES_PER_COLOR, MAX_RESEARCH_STATIONS
from pandemic.engine.game_events import (
    CardDiscarded,
    CubesRemoved,
    DiseaseEradicated,
    PawnMoved,
    StationBuilt,
)
from pandemic.engine.state import COLORS, CURED, ERADICATED, GameState


def check_eradication(state: GameState, ci: int, events: list) -> None:
    if state.cures[ci] == CURED and state.supply[ci] == CUBES_PER_COLOR:
        state.cures[ci] = ERADICATED
        events.append(DiseaseEradicated(COLORS[ci].value))


def remove_cubes(state: GameState, city: str, ci: int, n: int | None, player: int,
                 reason: str, events: list) -> int:
    """Remove ``n`` cubes (None = all) of color ``ci`` from ``city``; checks eradication."""
    have = state.cubes[city][ci]
    k = have if n is None else min(n, have)
    if k <= 0:
        return 0
    state.cubes[city][ci] = have - k
    state.supply[ci] += k
    events.append(CubesRemoved(city, COLORS[ci].value, k, player, reason))
    check_eradication(state, ci, events)
    return k


def discard_card(state: GameState, player: int, card: str, reason: str, events: list) -> None:
    state.players[player].hand.remove(card)
    state.player_discard.append(card)
    events.append(CardDiscarded(player, card, reason))


def build_station(state: GameState, city: str, relocate_from: str | None, player: int,
                  events: list) -> None:
    if relocate_from is not None:
        state.stations.remove(relocate_from)
    assert len(state.stations) < MAX_RESEARCH_STATIONS
    state.stations.append(city)
    events.append(StationBuilt(city, relocate_from, player))


def move_pawn(state: GameState, pawn: int, dest: str, method: str, by_player: int,
              events: list) -> None:
    from pandemic.engine.roles import behavior  # local import: roles imports board

    p = state.players[pawn]
    src = p.location
    p.location = dest
    events.append(PawnMoved(pawn, src, dest, method, by_player))
    behavior(p.role).on_moved(state, pawn, events)
