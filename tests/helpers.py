"""Helpers for building hand-crafted game states and checking invariants."""

from __future__ import annotations

import random

from pandemic.data.cards import CUBES_PER_COLOR, MAX_RESEARCH_STATIONS
from pandemic.data.cities import CITY_NAMES
from pandemic.engine import (
    GameConfig,
    GameState,
    PlayerState,
    Role,
    current_decision,
    is_over,
    legal_actions,
)
from pandemic.engine.state import CITY_COLOR, EVENT_NAMES, PendingDecision
from pandemic.engine.step import advance

FILLER = "Epidemic"


def make_state(
    roles=(Role.SCIENTIST, Role.RESEARCHER),
    hands=None,
    locations=None,
    cubes=None,
    stations=("Atlanta",),
    cures=None,
    player_deck=None,
    infection_deck=None,
    infection_discard=None,
    player_discard=(),
    current_player=0,
    difficulty="standard",
    seed=0,
    advance_state=True,
    **config_kw,
) -> GameState:
    """Build a consistent state. Cards not placed explicitly go to the decks so that card
    conservation holds: remaining city/event cards go to the player deck (after any given
    ``player_deck`` cards) unless ``player_deck`` is given, in which case leftovers are put
    in ``player_removed``. Infection cards not in deck/discard go to the infection deck."""
    config = GameConfig(num_players=len(roles), difficulty=difficulty, roles=list(roles),
                        **config_kw)
    players = [PlayerState(Role(r)) for r in roles]
    hands = hands or [[] for _ in roles]
    for p, h in zip(players, hands, strict=True):
        p.hand = list(h)
    if locations:
        for p, loc in zip(players, locations, strict=True):
            p.location = loc
    s = GameState(config=config, rng=random.Random(seed), players=players)
    for city, spec in (cubes or {}).items():
        if isinstance(spec, int):
            spec = {CITY_COLOR[city]: spec}
        for ci, n in spec.items():
            ci = ci if isinstance(ci, int) else ["blue", "yellow", "black", "red"].index(ci)
            s.cubes[city][ci] = n
            s.supply[ci] -= n
    s.stations = list(stations)
    if cures:
        for color, status in cures.items():
            s.cures[["blue", "yellow", "black", "red"].index(color)] = status
    used = {c for h in hands for c in h} | set(player_discard)
    s.player_discard = list(player_discard)
    rest = [c for c in list(CITY_NAMES) + list(EVENT_NAMES) if c not in used]
    if player_deck is None:
        s.player_deck = rest
        s.player_removed = ["Epidemic"] * config.num_epidemics
    else:
        s.player_deck = list(player_deck)
        given = set(player_deck)
        s.player_removed = [c for c in rest if c not in given]
        n_epi = sum(1 for c in player_deck if c == "Epidemic")
        s.player_removed += ["Epidemic"] * (config.num_epidemics - n_epi)
    s.player_deck_piles = [[len(s.player_deck), "Epidemic" in s.player_deck]]
    if not s.player_deck:
        s.player_deck_piles = []
    idisc = list(infection_discard or [])
    if infection_deck is None:
        ideck = [c for c in CITY_NAMES if c not in idisc]
    else:
        ideck = [c for c in infection_deck if c not in idisc]
        rest_inf = [c for c in CITY_NAMES if c not in set(ideck) | set(idisc)]
        ideck += rest_inf
    s.infection_deck = ideck
    s.infection_discard = idisc
    s.current_player = current_player
    if advance_state:
        advance(s, [])
    return s


def push_decision(s: GameState, kind: str, player: int, **ctx) -> None:
    s.stack.append(PendingDecision(kind, player, ctx))


def check_invariants(s: GameState) -> None:
    for ci in range(4):
        on_board = sum(v[ci] for v in s.cubes.values())
        assert on_board + s.supply[ci] == CUBES_PER_COLOR, ("cubes", ci)
        assert s.supply[ci] >= 0
    for city, v in s.cubes.items():
        assert all(0 <= n <= 3 for n in v), city
    assert s.total_player_cards() == s.expected_player_cards()
    assert (len(s.infection_deck) + len(s.infection_discard) + len(s.infection_removed)
            == len(CITY_NAMES))
    assert len(set(s.infection_deck) | set(s.infection_discard) | set(s.infection_removed)) == 48
    assert len(s.stations) <= MAX_RESEARCH_STATIONS
    assert len(set(s.stations)) == len(s.stations)
    assert sum(size for size, _ in s.player_deck_piles) == len(s.player_deck)
    assert s.outbreaks <= 8
    # Public infection-deck knowledge must be true.
    pos = 0
    for known_set in s.infection_known:
        assert known_set
        assert set(s.infection_deck[pos:pos + len(known_set)]) == set(known_set)
        pos += len(known_set)
    fk = s.forecast_known
    if fk is not None:
        a = fk["above"]
        assert s.infection_deck[a:a + len(fk["order"])] == fk["order"]
    for p in s.players:
        if p.stored_event is not None:
            assert p.role is Role.CONTINGENCY_PLANNER
    if is_over(s):
        assert legal_actions(s) == []
    else:
        assert legal_actions(s), current_decision(s)


def hand_of(s: GameState, p: int) -> list[str]:
    return s.players[p].hand
