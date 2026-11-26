"""Win / loss bookkeeping."""

from __future__ import annotations

from pandemic.engine.game_events import GameOver
from pandemic.engine.state import NONE, OVER, GameState

LOSS_OUTBREAKS = "outbreaks"
LOSS_CUBES = "cube_shortage"
LOSS_PLAYER_DECK = "player_deck_exhausted"
WIN_CURES = "all_diseases_cured"


def is_over(state: GameState) -> bool:
    return state.outcome is not None


def outcome(state: GameState) -> dict | None:
    """``None`` while running, else ``{"result": "win"|"loss", "reason": str}``."""
    return None if state.outcome is None else dict(state.outcome)


def _finish(state: GameState, result: str, reason: str, events: list) -> None:
    if state.outcome is not None:
        return
    state.outcome = {"result": result, "reason": reason}
    state.phase = OVER
    state.stack.clear()
    state.flow.clear()
    events.append(GameOver(result, reason))


def lose(state: GameState, reason: str, events: list) -> None:
    _finish(state, "loss", reason, events)


def check_win(state: GameState, events: list) -> bool:
    if all(c != NONE for c in state.cures):
        _finish(state, "win", WIN_CURES, events)
        return True
    return False
