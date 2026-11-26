"""Action dataclasses.

Every action is performed by the owner of the current ``PendingDecision`` (the "actor");
actions therefore carry no actor field. ``pawn`` fields are seat indices of the pawn being
moved (the actor's own seat for ordinary moves; another seat for Dispatcher/Airlift).
All actions are frozen, hashable and round-trip through ``action_to_dict``/``action_from_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

from pandemic.data.cities import Color


class IllegalActionError(ValueError):
    """Raised by ``step`` when the action is not in ``legal_actions(state)``."""


class Action:
    type: ClassVar[str] = ""
    costs_action: ClassVar[bool] = False  # consumes one of the 4 turn actions

    def to_dict(self) -> dict:
        return action_to_dict(self)


# ------------------------------------------------------------------ turn actions
@dataclass(frozen=True, slots=True)
class DriveFerry(Action):
    pawn: int
    destination: str
    type: ClassVar[str] = "drive_ferry"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class DirectFlight(Action):
    """Discard the destination's city card (from the actor's hand)."""

    pawn: int
    destination: str
    type: ClassVar[str] = "direct_flight"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class CharterFlight(Action):
    """Discard the city card of the pawn's current city (from the actor's hand)."""

    pawn: int
    destination: str
    type: ClassVar[str] = "charter_flight"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class ShuttleFlight(Action):
    pawn: int
    destination: str
    type: ClassVar[str] = "shuttle_flight"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class DispatcherMove(Action):
    """Dispatcher: move any pawn to a city containing another pawn."""

    pawn: int
    destination: str
    type: ClassVar[str] = "dispatcher_move"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class OperationsMove(Action):
    """Operations Expert: once per turn, from a research station to any city, discarding
    any city card."""

    destination: str
    card: str
    type: ClassVar[str] = "operations_move"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class BuildResearchStation(Action):
    """Build in the actor's city. ``relocate_from`` is required iff 6 stations exist."""

    relocate_from: str | None = None
    type: ClassVar[str] = "build_research_station"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class TreatDisease(Action):
    color: Color
    type: ClassVar[str] = "treat_disease"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class GiveCard(Action):
    """Share Knowledge: give ``card`` to ``to_player`` (same city)."""

    to_player: int
    card: str
    type: ClassVar[str] = "give_card"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class TakeCard(Action):
    """Share Knowledge: take ``card`` from ``from_player`` (same city)."""

    from_player: int
    card: str
    type: ClassVar[str] = "take_card"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class DiscoverCure(Action):
    """``cards`` is the exact set discarded, sorted by CITY_INDEX."""

    color: Color
    cards: tuple[str, ...]
    type: ClassVar[str] = "discover_cure"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class TakeEventCard(Action):
    """Contingency Planner: store an event card from the player discard pile."""

    card: str
    type: ClassVar[str] = "take_event_card"
    costs_action: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class EndActions(Action):
    """End the actions phase early (forfeit remaining actions)."""

    type: ClassVar[str] = "end_actions"


# ------------------------------------------------------------------ other decisions
@dataclass(frozen=True, slots=True)
class Discard(Action):
    card: str
    type: ClassVar[str] = "discard"


@dataclass(frozen=True, slots=True)
class Pass(Action):
    """Decline to play an event in an event window."""

    type: ClassVar[str] = "pass"


@dataclass(frozen=True, slots=True)
class Consent(Action):
    accept: bool
    type: ClassVar[str] = "consent"


@dataclass(frozen=True, slots=True)
class ForecastOrder(Action):
    """New order for the revealed cards; ``order[0]`` becomes the top of the deck."""

    order: tuple[str, ...]
    type: ClassVar[str] = "forecast_order"


# ------------------------------------------------------------------ event cards
@dataclass(frozen=True, slots=True)
class PlayAirlift(Action):
    pawn: int
    destination: str
    type: ClassVar[str] = "play_airlift"


@dataclass(frozen=True, slots=True)
class PlayOneQuietNight(Action):
    type: ClassVar[str] = "play_one_quiet_night"


@dataclass(frozen=True, slots=True)
class PlayResilientPopulation(Action):
    card: str  # infection discard card removed from the game
    type: ClassVar[str] = "play_resilient_population"


@dataclass(frozen=True, slots=True)
class PlayGovernmentGrant(Action):
    city: str
    relocate_from: str | None = None
    type: ClassVar[str] = "play_government_grant"


@dataclass(frozen=True, slots=True)
class PlayForecast(Action):
    type: ClassVar[str] = "play_forecast"


ACTION_TYPES: dict[str, type[Action]] = {
    cls.type: cls
    for cls in (
        DriveFerry, DirectFlight, CharterFlight, ShuttleFlight, DispatcherMove,
        OperationsMove, BuildResearchStation, TreatDisease, GiveCard, TakeCard,
        DiscoverCure, TakeEventCard, EndActions, Discard, Pass, Consent, ForecastOrder,
        PlayAirlift, PlayOneQuietNight, PlayResilientPopulation, PlayGovernmentGrant,
        PlayForecast,
    )
}

EVENT_PLAY_TYPES = (PlayAirlift, PlayOneQuietNight, PlayResilientPopulation,
                    PlayGovernmentGrant, PlayForecast)


def action_to_dict(action: Action) -> dict:
    d: dict = {"type": action.type}
    for f in fields(action):  # type: ignore[arg-type]
        v = getattr(action, f.name)
        if isinstance(v, Color):
            v = v.value
        elif isinstance(v, tuple):
            v = list(v)
        d[f.name] = v
    return d


def action_from_dict(d: dict) -> Action:
    try:
        cls = ACTION_TYPES[d["type"]]
    except KeyError as e:
        raise IllegalActionError(f"unknown action type {d.get('type')!r}") from e
    kwargs = {}
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name not in d:
            continue
        v = d[f.name]
        if f.name == "color":
            v = Color(v)
        elif f.name in ("cards", "order"):
            v = tuple(v)
        kwargs[f.name] = v
    try:
        return cls(**kwargs)
    except TypeError as e:
        raise IllegalActionError(f"bad fields for {d['type']}: {e}") from e
