"""JSON helpers (thin wrappers; the real work lives on the classes)."""

from __future__ import annotations

import json

from pandemic.engine.actions import action_from_dict, action_to_dict
from pandemic.engine.state import GameState

__all__ = ["action_from_dict", "action_to_dict", "event_to_dict", "state_from_json",
           "state_to_json"]


def event_to_dict(event) -> dict:
    return event.to_dict()


def state_to_json(state: GameState) -> str:
    return json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))


def state_from_json(s: str) -> GameState:
    return GameState.from_dict(json.loads(s))
