"""Infection, outbreaks, epidemics and infection-deck knowledge tracking."""

from __future__ import annotations

from collections import deque

from pandemic.data.cards import INFECTION_RATE_TRACK, MAX_OUTBREAKS
from pandemic.data.cities import CITY_INDEX, neighbors
from pandemic.engine.endgame import LOSS_CUBES, LOSS_OUTBREAKS, lose
from pandemic.engine.game_events import (
    CubesPlaced,
    EpidemicDrawn,
    InfectionCardDrawn,
    Intensified,
    Outbreak,
    PlacementPrevented,
)
from pandemic.engine.roles import placement_blocker
from pandemic.engine.state import CITY_COLOR, COLORS, ERADICATED, GameState


def place_cubes(state: GameState, city: str, ci: int, n: int, source: str, events: list,
                setup: bool = False) -> None:
    """The single chokepoint for adding cubes to the board.

    Places ``n`` cubes of color ``ci`` in ``city``. If that would exceed 3, the city is
    filled to 3 and outbreaks; chain reactions are resolved breadth-first and skip cities
    that already outbroke while resolving this card. Checks eradication, role prevention
    (Medic / Quarantine Specialist, not during setup), cube supply and the outbreak track.
    """
    color = COLORS[ci].value
    if state.cures[ci] == ERADICATED:
        events.append(PlacementPrevented(city, color, "eradicated"))
        return
    outbroken: set[str] = set()
    queue: deque[tuple[str, int, str]] = deque([(city, n, source)])
    while queue:
        c, k, src = queue.popleft()
        if c in outbroken:
            continue
        if not setup:
            blocker = placement_blocker(state, c, ci)
            if blocker is not None:
                events.append(PlacementPrevented(c, color, blocker.value))
                continue
        have = state.cubes[c][ci]
        add = min(k, 3 - have)
        if add > 0:
            if state.supply[ci] < add:
                lose(state, LOSS_CUBES, events)
                return
            state.supply[ci] -= add
            state.cubes[c][ci] = have + add
            events.append(CubesPlaced(c, color, add, src))
        if have + k > 3:
            outbroken.add(c)
            state.outbreaks += 1
            events.append(Outbreak(c, color, state.outbreaks))
            if state.outbreaks >= MAX_OUTBREAKS:
                lose(state, LOSS_OUTBREAKS, events)
                return
            for nb in neighbors(c):
                if nb not in outbroken:
                    queue.append((nb, 1, "outbreak"))


# ------------------------------------------------------------- deck knowledge
def _forget_card(state: GameState, card: str, from_top: bool) -> None:
    known = state.infection_known
    for i, s in enumerate(known):
        if card in s:
            s.remove(card)
            if not s:
                del known[i]
            break
    fk = state.forecast_known
    if fk is not None:
        if from_top and fk["above"] > 0:
            fk["above"] -= 1
        elif card in fk["order"]:
            fk["order"].remove(card)
        if not fk["order"]:
            state.forecast_known = None


def draw_infection_top(state: GameState) -> str | None:
    if not state.infection_deck:
        return None
    card = state.infection_deck.pop(0)
    _forget_card(state, card, True)
    return card


def draw_infection_bottom(state: GameState) -> str | None:
    if not state.infection_deck:
        return None
    card = state.infection_deck.pop()
    _forget_card(state, card, False)
    return card


def infect_one(state: GameState, events: list) -> None:
    """Infect Cities: flip one card, place 1 cube."""
    card = draw_infection_top(state)
    if card is None:  # empty deck (not covered by the rules): nothing to flip
        return
    events.append(InfectionCardDrawn(card, "infection"))
    place_cubes(state, card, CITY_COLOR[card], 1, "infection", events)
    state.infection_discard.append(card)


def epidemic_increase_infect(state: GameState, player: int, events: list) -> None:
    state.infection_rate_index = min(state.infection_rate_index + 1,
                                     len(INFECTION_RATE_TRACK) - 1)
    events.append(EpidemicDrawn(player, state.infection_rate_index, state.infection_rate))
    card = draw_infection_bottom(state)
    if card is None:
        return
    events.append(InfectionCardDrawn(card, "epidemic"))
    place_cubes(state, card, CITY_COLOR[card], 3, "epidemic", events)
    state.infection_discard.append(card)


def epidemic_intensify(state: GameState, events: list) -> None:
    pile = state.infection_discard
    state.rng.shuffle(pile)
    n = len(pile)
    state.infection_deck[:0] = pile
    state.infection_discard = []
    if n:
        state.infection_known.insert(0, sorted(pile, key=CITY_INDEX.__getitem__))
        if state.forecast_known is not None:
            state.forecast_known["above"] += n
    events.append(Intensified(n))


def forecast_merge_known(state: GameState, depth: int) -> None:
    """After the top ``depth`` cards were rearranged, keep only public knowledge that is
    still true: known sets overlapping the top ``depth`` merge into one set; if the known
    region does not cover the top ``depth`` cards, knowledge of that region is dropped."""
    known = state.infection_known
    total = 0
    k = 0
    while k < len(known) and total < depth:
        total += len(known[k])
        k += 1
    if total < depth:
        del known[:k]
    elif k > 1:
        merged = sorted((c for s in known[:k] for c in s), key=CITY_INDEX.__getitem__)
        known[:k] = [merged]
