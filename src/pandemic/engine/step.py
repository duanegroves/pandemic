"""``step(state, action)``: validate, apply, then auto-advance to the next decision.

``step`` MUTATES ``state`` IN PLACE and returns ``(state, events)`` (the same object).
Call ``state.clone()`` first if you need to keep the previous state.
"""

from __future__ import annotations

from pandemic.data.cards import EPIDEMIC, HAND_LIMIT
from pandemic.engine.actions import (
    EVENT_PLAY_TYPES,
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
    ShuttleFlight,
    TakeCard,
    TakeEventCard,
    TreatDisease,
    action_from_dict,
    action_to_dict,
)
from pandemic.engine.board import (
    build_station,
    check_eradication,
    discard_card,
    move_pawn,
    remove_cubes,
)
from pandemic.engine.endgame import LOSS_PLAYER_DECK, check_win, lose
from pandemic.engine.events import apply_forecast, has_playable, play_event
from pandemic.engine.game_events import (
    ActionsEnded,
    CardTransferred,
    ConsentGiven,
    ConsentRequested,
    CureDiscovered,
    ForecastArranged,
    InfectionsSkipped,
    PlayerCardsDrawn,
    TurnStarted,
)
from pandemic.engine.infection import epidemic_increase_infect, epidemic_intensify, infect_one
from pandemic.engine.legal import CHECKPOINT_ALLOWED, current_decision, legal_actions
from pandemic.engine.roles import behavior, notify_cure
from pandemic.engine.state import (
    ACTIONS,
    COLOR_INDEX,
    CURED,
    D_ACTIONS,
    D_CONSENT,
    D_DISCARD,
    D_EVENT_WINDOW,
    D_FORECAST,
    DRAW,
    INFECT,
    NONE,
    GameState,
    PendingDecision,
)

_MOVE_TYPES = (DriveFerry, DirectFlight, CharterFlight, ShuttleFlight, DispatcherMove)


def step(state: GameState, action: Action, validate: bool = True
         ) -> tuple[GameState, list]:
    """Apply ``action`` for the owner of the current decision. Mutates ``state`` in place.

    Raises ``IllegalActionError`` if the game is over or (when ``validate``) the action is
    not in ``legal_actions(state)``. Returns ``(state, events)``.
    """
    if state.outcome is not None:
        raise IllegalActionError("game is over")
    if validate and action not in legal_actions(state):
        raise IllegalActionError(f"illegal action {action_to_dict(action)}")
    d = current_decision(state)
    actor = d.player
    assert actor is not None
    events: list = []
    kind = d.kind

    if kind == D_CONSENT:
        assert isinstance(action, Consent)
        state.stack.pop()
        events.append(ConsentGiven(actor, action.accept))
        if action.accept:
            _perform(state, d.context["requester"], action_from_dict(d.context["request"]),
                     events)
    elif kind == D_FORECAST:
        assert isinstance(action, ForecastOrder)
        state.stack.pop()
        apply_forecast(state, actor, action.order)
        events.append(ForecastArranged(actor, action.order))
    elif kind == D_EVENT_WINDOW and isinstance(action, Pass):
        top = state.stack.pop()
        _push_window(state, top.context["checkpoint"], top.context["queue"])
    elif kind == D_DISCARD and isinstance(action, Discard):
        discard_card(state, actor, action.card, "hand_limit", events)
    elif kind == D_ACTIONS and isinstance(action, EndActions):
        _end_actions(state, events)
    else:
        _request(state, actor, action, events)

    advance(state, events)
    return state, events


# ------------------------------------------------------------------ consent
def consent_target(state: GameState, actor: int, action: Action) -> int | None:
    """Seat whose permission is needed for ``action`` (None if nobody's)."""
    if isinstance(action, GiveCard):
        return action.to_player
    if isinstance(action, TakeCard):
        return action.from_player
    if isinstance(action, (*_MOVE_TYPES, PlayAirlift)) and action.pawn != actor:  # type: ignore[union-attr]
        return action.pawn  # type: ignore[union-attr]
    return None


def _request(state: GameState, actor: int, action: Action, events: list) -> None:
    target = consent_target(state, actor, action)
    if target is not None and not state.config.auto_consent:
        req = action_to_dict(action)
        state.stack.append(PendingDecision(D_CONSENT, target,
                                           {"requester": actor, "request": req}))
        events.append(ConsentRequested(target, actor, req))
        return
    _perform(state, actor, action, events)


# ------------------------------------------------------------------ execution
def _perform(state: GameState, actor: int, action: Action, events: list) -> None:
    if isinstance(action, EVENT_PLAY_TYPES):
        play_event(state, actor, action, events)
        return
    me = state.players[actor]
    beh = behavior(me.role)
    if isinstance(action, DriveFerry):
        move_pawn(state, action.pawn, action.destination, "drive_ferry", actor, events)
    elif isinstance(action, DirectFlight):
        discard_card(state, actor, action.destination, "direct_flight", events)
        move_pawn(state, action.pawn, action.destination, "direct_flight", actor, events)
    elif isinstance(action, CharterFlight):
        discard_card(state, actor, state.players[action.pawn].location, "charter_flight",
                     events)
        move_pawn(state, action.pawn, action.destination, "charter_flight", actor, events)
    elif isinstance(action, ShuttleFlight):
        move_pawn(state, action.pawn, action.destination, "shuttle_flight", actor, events)
    elif isinstance(action, (OperationsMove, DispatcherMove, TakeEventCard)):
        beh.execute(state, actor, action, events)
    elif isinstance(action, BuildResearchStation):
        if not beh.build_free:
            discard_card(state, actor, me.location, "build_research_station", events)
        build_station(state, me.location, action.relocate_from, actor, events)
    elif isinstance(action, TreatDisease):
        ci = COLOR_INDEX[action.color]
        n = None if (beh.treat_all or state.cures[ci] != NONE) else 1
        remove_cubes(state, me.location, ci, n, actor, "treat", events)
    elif isinstance(action, GiveCard):
        _transfer(state, actor, action.to_player, action.card, events)
    elif isinstance(action, TakeCard):
        _transfer(state, action.from_player, actor, action.card, events)
    elif isinstance(action, DiscoverCure):
        ci = COLOR_INDEX[action.color]
        for c in action.cards:
            discard_card(state, actor, c, "discover_cure", events)
        state.cures[ci] = CURED
        events.append(CureDiscovered(action.color.value, actor))
        check_eradication(state, ci, events)
        notify_cure(state, ci, events)
        if check_win(state, events):
            return
    else:
        raise AssertionError(f"unhandled action {action}")
    if action.costs_action:
        state.actions_remaining -= 1
        state.actions_window_done = False


def _transfer(state: GameState, giver: int, receiver: int, card: str, events: list) -> None:
    state.players[giver].hand.remove(card)
    state.players[receiver].hand.append(card)
    events.append(CardTransferred(giver, receiver, card))
    _check_hand_limit(state, receiver)


def _check_hand_limit(state: GameState, p: int) -> None:
    if len(state.players[p].hand) > HAND_LIMIT:
        state.stack.append(PendingDecision(D_DISCARD, p, {"reason": "hand_limit",
                                                          "limit": HAND_LIMIT}))


# ------------------------------------------------------------------ event windows
def _turn_order(state: GameState, start: int) -> list[int]:
    n = state.num_players
    return [(start + i) % n for i in range(n)]


def _push_window(state: GameState, checkpoint: str, candidates: list[int]) -> None:
    allowed = CHECKPOINT_ALLOWED[checkpoint]
    for i, q in enumerate(candidates):
        if has_playable(state, q, allowed):
            state.stack.append(PendingDecision(
                D_EVENT_WINDOW, q, {"checkpoint": checkpoint, "queue": list(candidates[i + 1:])}))
            return


def _open_window(state: GameState, checkpoint: str) -> None:
    if state.config.event_windows == "off":
        return
    _push_window(state, checkpoint, _turn_order(state, state.current_player))


# ------------------------------------------------------------------ turn flow
def _end_actions(state: GameState, events: list) -> None:
    state.actions_remaining = 0
    state.phase = DRAW
    events.append(ActionsEnded(state.current_player))
    state.flow = [["window", "before_draw"], ["draw"]]


def _draw_player_card(state: GameState) -> str:
    card = state.player_deck.pop(0)
    pile = state.player_deck_piles[0]
    pile[0] -= 1
    if card == EPIDEMIC:
        pile[1] = False
    if pile[0] == 0:
        state.player_deck_piles.pop(0)
    return card


def _run_flow(state: GameState, item: list, events: list) -> None:
    name = item[0]
    cur = state.current_player
    if name == "window":
        _open_window(state, item[1])
    elif name == "draw":
        if len(state.player_deck) < 2:
            lose(state, LOSS_PLAYER_DECK, events)
            return
        cards = [_draw_player_card(state), _draw_player_card(state)]
        events.append(PlayerCardsDrawn(cur, tuple(cards)))
        eps = 0
        for c in cards:
            if c == EPIDEMIC:
                state.player_removed.append(c)
                eps += 1
            else:
                state.players[cur].hand.append(c)
        new: list[list] = []
        for i in range(eps):
            if i:
                new.append(["window", "between_epidemics"])
            new += [["epidemic"], ["window", "epidemic_intensify"], ["intensify"]]
        new += [["hand_limit"], ["window", "before_infection"], ["start_infect"]]
        state.flow[:0] = new
    elif name == "epidemic":
        epidemic_increase_infect(state, cur, events)
    elif name == "intensify":
        epidemic_intensify(state, events)
    elif name == "hand_limit":
        _check_hand_limit(state, cur)
    elif name == "start_infect":
        state.phase = INFECT
        if state.one_quiet_night:
            state.one_quiet_night = False
            events.append(InfectionsSkipped())
            state.flow.insert(0, ["end_turn"])
        else:
            steps: list[list] = [["infect"]]
            for _ in range(state.infection_rate - 1):
                steps += [["window", "before_infection"], ["infect"]]
            steps.append(["end_turn"])
            state.flow[:0] = steps
    elif name == "infect":
        infect_one(state, events)
    elif name == "end_turn":
        state.current_player = (cur + 1) % state.num_players
        state.turn += 1
        state.phase = ACTIONS
        state.actions_remaining = 4
        state.actions_window_done = False
        for p in state.players:
            p.ops_move_used = False
        events.append(TurnStarted(state.current_player, state.turn))
    else:
        raise AssertionError(f"unknown flow step {item}")


def advance(state: GameState, events: list) -> None:
    """Run automatic steps until a player decision is required or the game ends."""
    while state.outcome is None:
        if state.stack:
            top = state.stack[-1]
            assert top.player is not None
            if top.kind == D_EVENT_WINDOW:
                cp = top.context["checkpoint"]
                if not has_playable(state, top.player, CHECKPOINT_ALLOWED[cp]):
                    state.stack.pop()
                    _push_window(state, cp, top.context["queue"])
                    continue
            elif top.kind == D_DISCARD:
                if len(state.players[top.player].hand) <= HAND_LIMIT:
                    state.stack.pop()
                    continue
            return
        if state.phase == ACTIONS:
            if state.actions_remaining <= 0:
                _end_actions(state, events)
                continue
            if state.config.event_windows == "full" and not state.actions_window_done:
                state.actions_window_done = True
                others = _turn_order(state, state.current_player)[1:]
                _push_window(state, "actions", others)
                continue
            return
        if not state.flow:
            raise AssertionError("engine invariant: empty flow outside actions phase")
        _run_flow(state, state.flow.pop(0), events)
