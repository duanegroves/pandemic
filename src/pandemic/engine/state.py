"""Mutable game state, pending decisions and shared constants.

Conventions:
- Colors are indexed 0..3 in ``COLORS`` order (blue, yellow, black, red) for internal arrays.
- Player cards are strings: a city name, an event name (``EventCard`` value) or ``"Epidemic"``.
- Infection cards are city names.
- Decks are lists with index 0 = TOP of the deck.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from pandemic.data.cards import EPIDEMIC, INFECTION_RATE_TRACK, EventCard
from pandemic.data.cities import CITIES, CITY_NAMES, Color
from pandemic.engine.config import GameConfig, Role

__all__ = [
    "COLORS",
    "COLOR_INDEX",
    "CITY_COLOR",
    "EVENT_NAMES",
    "GameState",
    "PendingDecision",
    "PlayerState",
    "Role",
    "is_city_card",
    "is_event_card",
]

COLORS: tuple[Color, ...] = tuple(Color)
COLOR_INDEX: dict[Color, int] = {c: i for i, c in enumerate(COLORS)}
CITY_COLOR: dict[str, int] = {n: COLOR_INDEX[c.color] for n, c in CITIES.items()}
EVENT_NAMES: tuple[str, ...] = tuple(e.value for e in EventCard)
_EVENT_SET = frozenset(EVENT_NAMES)

# Cure status values.
NONE, CURED, ERADICATED = "none", "cured", "eradicated"

# Phases.
ACTIONS, DRAW, INFECT, OVER = "actions", "draw", "infect", "over"

# Decision kinds.
D_ACTIONS = "actions"
D_EVENT_WINDOW = "event_window"
D_DISCARD = "discard"
D_CONSENT = "consent"
D_FORECAST = "forecast_order"
D_GAME_OVER = "game_over"


def is_city_card(card: str) -> bool:
    return card in CITIES


def is_event_card(card: str) -> bool:
    return card in _EVENT_SET


@dataclass
class PlayerState:
    role: Role
    location: str = "Atlanta"
    hand: list[str] = field(default_factory=list)
    stored_event: str | None = None  # Contingency Planner only
    ops_move_used: bool = False  # Operations Expert once-per-turn special move

    def clone(self) -> PlayerState:
        return PlayerState(self.role, self.location, list(self.hand), self.stored_event,
                           self.ops_move_used)

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "location": self.location,
            "hand": list(self.hand),
            "stored_event": self.stored_event,
            "ops_move_used": self.ops_move_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PlayerState:
        return cls(Role(d["role"]), d["location"], list(d["hand"]), d["stored_event"],
                   d["ops_move_used"])


@dataclass
class PendingDecision:
    """A point where a specific player must choose an action.

    ``kind`` is one of: ``actions``, ``event_window``, ``discard``, ``consent``,
    ``forecast_order``, ``game_over``. ``player`` is the seat index (None when game over).
    ``context`` is a JSON-friendly dict whose keys depend on ``kind``.
    """

    kind: str
    player: int | None
    context: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> PendingDecision:
        return PendingDecision(self.kind, self.player, _copy_json(self.context))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "player": self.player, "context": _copy_json(self.context)}

    @classmethod
    def from_dict(cls, d: dict) -> PendingDecision:
        return cls(d["kind"], d["player"], _copy_json(d["context"]))


def _copy_json(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _copy_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_copy_json(v) for v in x]
    return x


@dataclass
class GameState:
    """Complete authoritative game state. Mutated in place by ``step``; use ``clone()``."""

    config: GameConfig
    rng: random.Random
    players: list[PlayerState]
    cubes: dict[str, list[int]] = field(
        default_factory=lambda: {n: [0, 0, 0, 0] for n in CITY_NAMES})
    supply: list[int] = field(default_factory=lambda: [24, 24, 24, 24])
    stations: list[str] = field(default_factory=lambda: ["Atlanta"])
    cures: list[str] = field(default_factory=lambda: [NONE] * 4)
    outbreaks: int = 0
    infection_rate_index: int = 0
    player_deck: list[str] = field(default_factory=list)
    # Remaining epidemic-pile structure, top first: [cards_left, epidemic_still_in_pile].
    player_deck_piles: list[list] = field(default_factory=list)
    player_discard: list[str] = field(default_factory=list)
    player_removed: list[str] = field(default_factory=list)
    infection_deck: list[str] = field(default_factory=list)
    infection_discard: list[str] = field(default_factory=list)
    infection_removed: list[str] = field(default_factory=list)
    # Publicly known top of the infection deck: stack of card sets, top first.
    infection_known: list[list[str]] = field(default_factory=list)
    # Private Forecast knowledge: {"player", "above", "order"} or None.
    forecast_known: dict | None = None
    current_player: int = 0
    turn: int = 1
    phase: str = ACTIONS
    actions_remaining: int = 4
    actions_window_done: bool = False
    one_quiet_night: bool = False
    stack: list[PendingDecision] = field(default_factory=list)
    flow: list[list] = field(default_factory=list)
    outcome: dict | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def infection_rate(self) -> int:
        return INFECTION_RATE_TRACK[self.infection_rate_index]

    @property
    def num_players(self) -> int:
        return len(self.players)

    def is_over(self) -> bool:
        return self.outcome is not None

    def total_player_cards(self) -> int:
        n = len(self.player_deck) + len(self.player_discard) + len(self.player_removed)
        for p in self.players:
            n += len(p.hand) + (1 if p.stored_event else 0)
        return n

    def expected_player_cards(self) -> int:
        return len(CITIES) + len(EVENT_NAMES) + self.config.num_epidemics

    def role_index(self, role: Role) -> int | None:
        for i, p in enumerate(self.players):
            if p.role is role:
                return i
        return None

    # ------------------------------------------------------------------ copying
    def clone(self) -> GameState:
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        return GameState(
            config=self.config,
            rng=rng,
            players=[p.clone() for p in self.players],
            cubes={k: list(v) for k, v in self.cubes.items()},
            supply=list(self.supply),
            stations=list(self.stations),
            cures=list(self.cures),
            outbreaks=self.outbreaks,
            infection_rate_index=self.infection_rate_index,
            player_deck=list(self.player_deck),
            player_deck_piles=[list(p) for p in self.player_deck_piles],
            player_discard=list(self.player_discard),
            player_removed=list(self.player_removed),
            infection_deck=list(self.infection_deck),
            infection_discard=list(self.infection_discard),
            infection_removed=list(self.infection_removed),
            infection_known=[list(s) for s in self.infection_known],
            forecast_known=_copy_json(self.forecast_known),
            current_player=self.current_player,
            turn=self.turn,
            phase=self.phase,
            actions_remaining=self.actions_remaining,
            actions_window_done=self.actions_window_done,
            one_quiet_night=self.one_quiet_night,
            stack=[d.clone() for d in self.stack],
            flow=_copy_json(self.flow),
            outcome=_copy_json(self.outcome),
        )

    # ------------------------------------------------------------ serialization
    def to_dict(self) -> dict:
        version, internal, gauss = self.rng.getstate()
        return {
            "format": 1,
            "config": self.config.to_dict(),
            "rng": [version, list(internal), gauss],
            "players": [p.to_dict() for p in self.players],
            "cubes": {k: list(v) for k, v in self.cubes.items() if any(v)},
            "supply": list(self.supply),
            "stations": list(self.stations),
            "cures": list(self.cures),
            "outbreaks": self.outbreaks,
            "infection_rate_index": self.infection_rate_index,
            "player_deck": list(self.player_deck),
            "player_deck_piles": [list(p) for p in self.player_deck_piles],
            "player_discard": list(self.player_discard),
            "player_removed": list(self.player_removed),
            "infection_deck": list(self.infection_deck),
            "infection_discard": list(self.infection_discard),
            "infection_removed": list(self.infection_removed),
            "infection_known": [list(s) for s in self.infection_known],
            "forecast_known": _copy_json(self.forecast_known),
            "current_player": self.current_player,
            "turn": self.turn,
            "phase": self.phase,
            "actions_remaining": self.actions_remaining,
            "actions_window_done": self.actions_window_done,
            "one_quiet_night": self.one_quiet_night,
            "stack": [d.to_dict() for d in self.stack],
            "flow": _copy_json(self.flow),
            "outcome": _copy_json(self.outcome),
        }

    @classmethod
    def from_dict(cls, d: dict) -> GameState:
        rng = random.Random()
        version, internal, gauss = d["rng"]
        rng.setstate((version, tuple(internal), gauss))
        cubes = {n: [0, 0, 0, 0] for n in CITY_NAMES}
        for k, v in d["cubes"].items():
            cubes[k] = list(v)
        return cls(
            config=GameConfig.from_dict(d["config"]),
            rng=rng,
            players=[PlayerState.from_dict(p) for p in d["players"]],
            cubes=cubes,
            supply=list(d["supply"]),
            stations=list(d["stations"]),
            cures=list(d["cures"]),
            outbreaks=d["outbreaks"],
            infection_rate_index=d["infection_rate_index"],
            player_deck=list(d["player_deck"]),
            player_deck_piles=[list(p) for p in d["player_deck_piles"]],
            player_discard=list(d["player_discard"]),
            player_removed=list(d["player_removed"]),
            infection_deck=list(d["infection_deck"]),
            infection_discard=list(d["infection_discard"]),
            infection_removed=list(d["infection_removed"]),
            infection_known=[list(s) for s in d["infection_known"]],
            forecast_known=_copy_json(d["forecast_known"]),
            current_player=d["current_player"],
            turn=d["turn"],
            phase=d["phase"],
            actions_remaining=d["actions_remaining"],
            actions_window_done=d["actions_window_done"],
            one_quiet_night=d["one_quiet_night"],
            stack=[PendingDecision.from_dict(x) for x in d["stack"]],
            flow=_copy_json(d["flow"]),
            outcome=_copy_json(d["outcome"]),
        )


__all__ += ["EPIDEMIC"]
