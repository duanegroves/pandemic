"""Game configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pandemic.data.cards import EPIDEMICS_BY_DIFFICULTY


class Role(str, Enum):
    CONTINGENCY_PLANNER = "contingency_planner"
    DISPATCHER = "dispatcher"
    MEDIC = "medic"
    OPERATIONS_EXPERT = "operations_expert"
    QUARANTINE_SPECIALIST = "quarantine_specialist"
    RESEARCHER = "researcher"
    SCIENTIST = "scientist"


ROLES: tuple[Role, ...] = tuple(Role)
EVENT_WINDOW_MODES = ("full", "checkpoints", "off")


@dataclass
class GameConfig:
    """Static options for one game.

    - ``num_players``: 2-4.
    - ``difficulty``: ``"introductory"`` (4 epidemics), ``"standard"`` (5), ``"heroic"`` (6).
    - ``roles``: one role per seat (``Role`` or its string value), or ``None`` to deal
      random roles from the seeded RNG.
    - ``open_hands``: ``None`` means the rulebook default (open for introductory only).
    - ``auto_consent``: when True, Share Knowledge and moving another player's pawn never
      ask the other player; when False a ``consent`` decision is created.
    - ``event_windows``: ``"full"``, ``"checkpoints"`` or ``"off"`` (see docs/ENGINE_API.md).
    """

    num_players: int = 2
    difficulty: str = "standard"
    roles: list[Role] | None = None
    open_hands: bool | None = None
    auto_consent: bool = True
    event_windows: str = "checkpoints"

    def __post_init__(self) -> None:
        if self.num_players not in (2, 3, 4):
            raise ValueError("num_players must be 2, 3 or 4")
        if self.difficulty not in EPIDEMICS_BY_DIFFICULTY:
            raise ValueError(f"difficulty must be one of {list(EPIDEMICS_BY_DIFFICULTY)}")
        if self.event_windows not in EVENT_WINDOW_MODES:
            raise ValueError(f"event_windows must be one of {EVENT_WINDOW_MODES}")
        if self.roles is not None:
            roles = [Role(r) for r in self.roles]
            if len(roles) != self.num_players:
                raise ValueError("roles must have exactly num_players entries")
            if len(set(roles)) != len(roles):
                raise ValueError("roles must be distinct")
            self.roles = roles

    @property
    def num_epidemics(self) -> int:
        return EPIDEMICS_BY_DIFFICULTY[self.difficulty]

    @property
    def hands_open(self) -> bool:
        if self.open_hands is None:
            return self.difficulty == "introductory"
        return self.open_hands

    def to_dict(self) -> dict:
        return {
            "num_players": self.num_players,
            "difficulty": self.difficulty,
            "roles": None if self.roles is None else [r.value for r in self.roles],
            "open_hands": self.open_hands,
            "auto_consent": self.auto_consent,
            "event_windows": self.event_windows,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GameConfig:
        return cls(
            num_players=d["num_players"],
            difficulty=d["difficulty"],
            roles=d.get("roles"),
            open_hands=d.get("open_hands"),
            auto_consent=d.get("auto_consent", True),
            event_windows=d.get("event_windows", "checkpoints"),
        )
