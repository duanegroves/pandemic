"""Event cards: Airlift, One Quiet Night, Resilient Population, Government Grant, Forecast."""

from __future__ import annotations

from pandemic.data.cards import MAX_RESEARCH_STATIONS, EventCard
from pandemic.data.cities import CITY_NAMES
from pandemic.engine.actions import (
    Action,
    PlayAirlift,
    PlayForecast,
    PlayGovernmentGrant,
    PlayOneQuietNight,
    PlayResilientPopulation,
)
from pandemic.engine.board import build_station, move_pawn
from pandemic.engine.game_events import EventPlayed, InfectionCardRemoved
from pandemic.engine.infection import forecast_merge_known
from pandemic.engine.state import D_FORECAST, GameState, PendingDecision, is_event_card

FORECAST_DEPTH = 6

ACTION_CARD: dict[type, str] = {
    PlayAirlift: EventCard.AIRLIFT.value,
    PlayOneQuietNight: EventCard.ONE_QUIET_NIGHT.value,
    PlayResilientPopulation: EventCard.RESILIENT_POPULATION.value,
    PlayGovernmentGrant: EventCard.GOVERNMENT_GRANT.value,
    PlayForecast: EventCard.FORECAST.value,
}

# Checkpoint name -> allowed event cards (None = all).
RP_ONLY = frozenset({EventCard.RESILIENT_POPULATION.value})


def held_events(state: GameState, p: int, include_stored: bool = True) -> list[str]:
    pl = state.players[p]
    out = [c for c in pl.hand if is_event_card(c)]
    if include_stored and pl.stored_event is not None:
        out.append(pl.stored_event)
    return out


def card_playable(state: GameState, card: str) -> bool:
    if card == EventCard.ONE_QUIET_NIGHT.value:
        return not state.one_quiet_night  # a second copy would be a no-op
    if card == EventCard.RESILIENT_POPULATION.value:
        return bool(state.infection_discard)
    if card == EventCard.FORECAST.value:
        return bool(state.infection_deck)
    return True  # Airlift, Government Grant


def has_playable(state: GameState, p: int, allowed: frozenset | None = None,
                 include_stored: bool = True) -> bool:
    for c in held_events(state, p, include_stored):
        if (allowed is None or c in allowed) and card_playable(state, c):
            return True
    return False


def event_actions(state: GameState, p: int, allowed: frozenset | None = None,
                  include_stored: bool = True) -> list[Action]:
    out: list[Action] = []
    for card in held_events(state, p, include_stored):
        if (allowed is not None and card not in allowed) or not card_playable(state, card):
            continue
        if card == EventCard.AIRLIFT.value:
            for q, pl in enumerate(state.players):
                out.extend(PlayAirlift(q, c) for c in CITY_NAMES if c != pl.location)
        elif card == EventCard.ONE_QUIET_NIGHT.value:
            out.append(PlayOneQuietNight())
        elif card == EventCard.RESILIENT_POPULATION.value:
            out.extend(PlayResilientPopulation(c) for c in state.infection_discard)
        elif card == EventCard.GOVERNMENT_GRANT.value:
            full = len(state.stations) >= MAX_RESEARCH_STATIONS
            for c in CITY_NAMES:
                if c in state.stations:
                    continue
                if full:
                    out.extend(PlayGovernmentGrant(c, s) for s in state.stations)
                else:
                    out.append(PlayGovernmentGrant(c))
        elif card == EventCard.FORECAST.value:
            out.append(PlayForecast())
    return out


def consent_needed(state: GameState, actor: int, action: Action) -> int | None:
    if isinstance(action, PlayAirlift) and action.pawn != actor:
        return action.pawn
    return None


def play_event(state: GameState, actor: int, action: Action, events: list) -> None:
    card = ACTION_CARD[type(action)]
    pl = state.players[actor]
    if card in pl.hand:
        pl.hand.remove(card)
        state.player_discard.append(card)
        from_stored = False
    else:
        assert pl.stored_event == card
        pl.stored_event = None
        state.player_removed.append(card)
        from_stored = True
    events.append(EventPlayed(actor, card, from_stored))

    if isinstance(action, PlayAirlift):
        move_pawn(state, action.pawn, action.destination, "airlift", actor, events)
    elif isinstance(action, PlayOneQuietNight):
        state.one_quiet_night = True
    elif isinstance(action, PlayResilientPopulation):
        state.infection_discard.remove(action.card)
        state.infection_removed.append(action.card)
        events.append(InfectionCardRemoved(action.card))
    elif isinstance(action, PlayGovernmentGrant):
        build_station(state, action.city, action.relocate_from, actor, events)
    elif isinstance(action, PlayForecast):
        cards = state.infection_deck[:FORECAST_DEPTH]
        state.stack.append(PendingDecision(D_FORECAST, actor, {"cards": list(cards)}))


def apply_forecast(state: GameState, actor: int, order: tuple[str, ...]) -> None:
    n = len(order)
    state.infection_deck[:n] = list(order)
    forecast_merge_known(state, n)
    state.forecast_known = {"player": actor, "above": 0, "order": list(order)}
