"""Legal action enumeration for the current pending decision."""

from __future__ import annotations

from itertools import combinations, permutations

from pandemic.data.cards import MAX_RESEARCH_STATIONS
from pandemic.data.cities import CITY_INDEX, CITY_NAMES, neighbors
from pandemic.engine.actions import (
    Action,
    BuildResearchStation,
    CharterFlight,
    Consent,
    DirectFlight,
    Discard,
    DiscoverCure,
    DriveFerry,
    EndActions,
    ForecastOrder,
    GiveCard,
    Pass,
    ShuttleFlight,
    TakeCard,
    TreatDisease,
)
from pandemic.engine.event_cards import RP_ONLY, event_actions
from pandemic.engine.roles import behavior
from pandemic.engine.state import (
    ACTIONS,
    CITY_COLOR,
    COLORS,
    D_ACTIONS,
    D_CONSENT,
    D_DISCARD,
    D_EVENT_WINDOW,
    D_FORECAST,
    D_GAME_OVER,
    NONE,
    GameState,
    PendingDecision,
    is_city_card,
)

CHECKPOINT_ALLOWED: dict[str, frozenset | None] = {
    "actions": None,
    "before_draw": None,
    "epidemic_intensify": RP_ONLY,
    "between_epidemics": None,
    "before_infection": None,
}


def current_decision(state: GameState) -> PendingDecision:
    """The decision the engine is waiting on (owner, kind, context)."""
    if state.outcome is not None:
        return PendingDecision(D_GAME_OVER, None, {"outcome": dict(state.outcome)})
    if state.stack:
        return state.stack[-1]
    assert state.phase == ACTIONS, "engine invariant: no pending decision outside actions"
    return PendingDecision(D_ACTIONS, state.current_player,
                           {"actions_remaining": state.actions_remaining})


def legal_actions(state: GameState) -> list[Action]:
    """All legal actions for the owner of ``current_decision(state)`` (empty iff over)."""
    d = current_decision(state)
    k = d.kind
    if k == D_GAME_OVER:
        return []
    p = d.player
    assert p is not None
    if k == D_ACTIONS:
        return _turn_actions(state, p)
    if k == D_EVENT_WINDOW:
        out = event_actions(state, p, CHECKPOINT_ALLOWED[d.context["checkpoint"]])
        out.append(Pass())
        return out
    if k == D_DISCARD:
        out2: list[Action] = [Discard(c) for c in state.players[p].hand]
        out2.extend(event_actions(state, p, None, include_stored=False))
        return out2
    if k == D_CONSENT:
        return [Consent(True), Consent(False)]
    if k == D_FORECAST:
        return [ForecastOrder(o) for o in permutations(d.context["cards"])]
    raise AssertionError(f"unknown decision kind {k}")


def _turn_actions(state: GameState, p: int) -> list[Action]:
    me = state.players[p]
    beh = behavior(me.role)
    out: list[Action] = []
    if state.actions_remaining > 0:
        hand = me.hand
        city_cards = [c for c in hand if is_city_card(c)]
        stations = state.stations
        pawns = range(state.num_players) if beh.moves_other_pawns else (p,)
        for q in pawns:
            loc = state.players[q].location
            out.extend(DriveFerry(q, n) for n in neighbors(loc))
            out.extend(DirectFlight(q, c) for c in city_cards if c != loc)
            if loc in hand:
                out.extend(CharterFlight(q, c) for c in CITY_NAMES if c != loc)
            if loc in stations:
                out.extend(ShuttleFlight(q, s) for s in stations if s != loc)
        out.extend(beh.extra_actions(state, p))

        loc = me.location
        if loc not in stations and (beh.build_free or loc in hand):
            if len(stations) < MAX_RESEARCH_STATIONS:
                out.append(BuildResearchStation())
            else:
                out.extend(BuildResearchStation(s) for s in stations)

        cubes = state.cubes[loc]
        out.extend(TreatDisease(COLORS[ci]) for ci in range(4) if cubes[ci])

        for q, other in enumerate(state.players):
            if q == p or other.location != loc:
                continue
            for c in city_cards:
                if c == loc or beh.gives_any_city_card:
                    out.append(GiveCard(q, c))
            obeh = behavior(other.role)
            for c in other.hand:
                if is_city_card(c) and (c == loc or obeh.gives_any_city_card):
                    out.append(TakeCard(q, c))

        if loc in stations:
            need = beh.cure_cards
            for ci in range(4):
                if state.cures[ci] != NONE:
                    continue
                same = sorted((c for c in city_cards if CITY_COLOR[c] == ci),
                              key=CITY_INDEX.__getitem__)
                if len(same) >= need:
                    out.extend(DiscoverCure(COLORS[ci], combo)
                               for combo in combinations(same, need))

    out.extend(event_actions(state, p))
    out.append(EndActions())
    return out
