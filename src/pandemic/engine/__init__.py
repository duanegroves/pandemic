"""Pandemic rules engine. Public API (see docs/ENGINE_API.md).

    state = new_game(GameConfig(num_players=2), seed=1)
    while not is_over(state):
        d = current_decision(state)          # who must act and why
        acts = legal_actions(state)          # actions for d.player
        state, events = step(state, acts[0]) # mutates state in place
"""

from pandemic.data.cities import Color
from pandemic.engine.actions import (
    ACTION_TYPES,
    Action,
    BuildResearchStation,
    CharterFlight,
    Consent,
    DirectFlight,
    Discard,
    DiscoverCure,
    DispatcherMove,
    DriveFerry,
    EndActions,
    ForecastOrder,
    GiveCard,
    IllegalActionError,
    OperationsMove,
    Pass,
    PlayAirlift,
    PlayForecast,
    PlayGovernmentGrant,
    PlayOneQuietNight,
    PlayResilientPopulation,
    ShuttleFlight,
    TakeCard,
    TakeEventCard,
    TreatDisease,
    action_from_dict,
    action_to_dict,
)
from pandemic.engine.config import ROLES, GameConfig, Role
from pandemic.engine.endgame import is_over, outcome
from pandemic.engine.game_events import EVENT_TYPES, GameEvent
from pandemic.engine.legal import current_decision, legal_actions
from pandemic.engine.observe import observe, redact_event
from pandemic.engine.serialize import state_from_json, state_to_json
from pandemic.engine.setup import new_game
from pandemic.engine.state import (
    COLORS,
    EVENT_NAMES,
    GameState,
    PendingDecision,
    PlayerState,
)
from pandemic.engine.step import step

__all__ = [
    "ACTION_TYPES", "COLORS", "EVENT_NAMES", "EVENT_TYPES", "ROLES",
    "Action", "BuildResearchStation", "CharterFlight", "Color", "Consent", "DirectFlight",
    "Discard", "DiscoverCure", "DispatcherMove", "DriveFerry", "EndActions", "ForecastOrder",
    "GameConfig", "GameEvent", "GameState", "GiveCard", "IllegalActionError",
    "OperationsMove", "Pass", "PendingDecision", "PlayAirlift", "PlayForecast",
    "PlayGovernmentGrant", "PlayOneQuietNight", "PlayResilientPopulation", "PlayerState",
    "Role", "ShuttleFlight", "TakeCard", "TakeEventCard", "TreatDisease",
    "action_from_dict", "action_to_dict", "current_decision", "is_over",
    "legal_actions", "new_game", "observe", "outcome", "redact_event", "state_from_json",
    "state_to_json", "step",
]
