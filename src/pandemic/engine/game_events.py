"""Domain events returned by ``step`` (for animation/logging; RL may ignore them).

Each event is a dataclass with a ``type`` class attribute; ``event.to_dict()`` gives a
JSON-friendly dict including ``type``. Some events carry hidden information; use
``pandemic.engine.observe.redact_event`` before sending them to a given player.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar


class GameEvent:
    type: ClassVar[str] = ""

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        for f in fields(self):  # type: ignore[arg-type]
            v = getattr(self, f.name)
            d[f.name] = list(v) if isinstance(v, tuple) else v
        return d


@dataclass(frozen=True, slots=True)
class CubesPlaced(GameEvent):
    type: ClassVar[str] = "cubes_placed"
    city: str
    color: str
    count: int
    source: str  # setup | infection | epidemic | outbreak


@dataclass(frozen=True, slots=True)
class CubesRemoved(GameEvent):
    type: ClassVar[str] = "cubes_removed"
    city: str
    color: str
    count: int
    player: int
    reason: str  # treat | medic


@dataclass(frozen=True, slots=True)
class PlacementPrevented(GameEvent):
    type: ClassVar[str] = "placement_prevented"
    city: str
    color: str
    reason: str  # eradicated | medic | quarantine_specialist


@dataclass(frozen=True, slots=True)
class Outbreak(GameEvent):
    type: ClassVar[str] = "outbreak"
    city: str
    color: str
    total: int


@dataclass(frozen=True, slots=True)
class InfectionCardDrawn(GameEvent):
    type: ClassVar[str] = "infection_card_drawn"
    card: str
    source: str  # setup | infection | epidemic


@dataclass(frozen=True, slots=True)
class EpidemicDrawn(GameEvent):
    type: ClassVar[str] = "epidemic"
    player: int
    infection_rate_index: int
    infection_rate: int


@dataclass(frozen=True, slots=True)
class Intensified(GameEvent):
    type: ClassVar[str] = "intensify"
    count: int  # cards shuffled back on top of the infection deck


@dataclass(frozen=True, slots=True)
class PlayerCardsDrawn(GameEvent):
    """``cards`` is private to ``player`` (except Epidemic) unless hands are open."""

    type: ClassVar[str] = "player_cards_drawn"

    player: int
    cards: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PawnMoved(GameEvent):
    type: ClassVar[str] = "pawn_moved"
    pawn: int
    from_city: str
    to_city: str
    method: str
    by_player: int


@dataclass(frozen=True, slots=True)
class StationBuilt(GameEvent):
    type: ClassVar[str] = "station_built"
    city: str
    relocated_from: str | None
    player: int


@dataclass(frozen=True, slots=True)
class CardDiscarded(GameEvent):
    type: ClassVar[str] = "card_discarded"
    player: int
    card: str
    reason: str


@dataclass(frozen=True, slots=True)
class CardTransferred(GameEvent):
    type: ClassVar[str] = "card_transferred"
    from_player: int
    to_player: int
    card: str


@dataclass(frozen=True, slots=True)
class CureDiscovered(GameEvent):
    type: ClassVar[str] = "cure_discovered"
    color: str
    player: int


@dataclass(frozen=True, slots=True)
class DiseaseEradicated(GameEvent):
    type: ClassVar[str] = "disease_eradicated"
    color: str


@dataclass(frozen=True, slots=True)
class EventPlayed(GameEvent):
    type: ClassVar[str] = "event_played"
    player: int
    card: str
    from_stored: bool  # Contingency Planner's stored card (removed from game)


@dataclass(frozen=True, slots=True)
class EventStored(GameEvent):
    type: ClassVar[str] = "event_stored"
    player: int
    card: str


@dataclass(frozen=True, slots=True)
class InfectionCardRemoved(GameEvent):
    type: ClassVar[str] = "infection_card_removed"
    card: str


@dataclass(frozen=True, slots=True)
class InfectionsSkipped(GameEvent):
    """One Quiet Night consumed."""

    type: ClassVar[str] = "infections_skipped"


@dataclass(frozen=True, slots=True)
class ForecastArranged(GameEvent):
    """``order`` is private to ``player``."""

    type: ClassVar[str] = "forecast_arranged"

    player: int
    order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConsentRequested(GameEvent):
    type: ClassVar[str] = "consent_requested"
    player: int
    requester: int
    request: dict


@dataclass(frozen=True, slots=True)
class ConsentGiven(GameEvent):
    type: ClassVar[str] = "consent_given"
    player: int
    accepted: bool


@dataclass(frozen=True, slots=True)
class ActionsEnded(GameEvent):
    type: ClassVar[str] = "actions_ended"
    player: int


@dataclass(frozen=True, slots=True)
class TurnStarted(GameEvent):
    type: ClassVar[str] = "turn_started"
    player: int
    turn: int


@dataclass(frozen=True, slots=True)
class GameOver(GameEvent):
    type: ClassVar[str] = "game_over"
    result: str  # win | loss
    reason: str


EVENT_TYPES: dict[str, type] = {
    c.type: c
    for c in (
        CubesPlaced, CubesRemoved, PlacementPrevented, Outbreak, InfectionCardDrawn,
        EpidemicDrawn, Intensified, PlayerCardsDrawn, PawnMoved, StationBuilt,
        CardDiscarded, CardTransferred, CureDiscovered, DiseaseEradicated, EventPlayed,
        EventStored, InfectionCardRemoved, InfectionsSkipped, ForecastArranged,
        ConsentRequested, ConsentGiven, ActionsEnded, TurnStarted, GameOver,
    )
}
