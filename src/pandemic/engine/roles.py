"""Role behavior hooks.

Each role is a ``RoleBehavior`` subclass. The engine calls these hooks instead of
branching on role names:

- ``cure_cards``            cards needed to Discover a Cure
- ``treat_all``             Treat Disease removes all cubes of the color
- ``build_free``            Build a Research Station without a card
- ``gives_any_city_card``   Share Knowledge: may give / be taken any city card
- ``moves_other_pawns``     may move other pawns as own (Dispatcher)
- ``protects(...)``         prevent cube placement / outbreaks in a city
- ``on_moved(...)``         after this player's pawn moves (any reason, any turn)
- ``on_cure(...)``          after any cure is discovered
- ``extra_actions(...)``    role-only action enumeration
- ``execute(...)``          perform a role-only action
"""

from __future__ import annotations

from pandemic.data.cities import CITY_NAMES, neighbors
from pandemic.engine.actions import Action, DispatcherMove, OperationsMove, TakeEventCard
from pandemic.engine.board import discard_card, move_pawn, remove_cubes
from pandemic.engine.game_events import EventStored
from pandemic.engine.state import NONE, GameState, Role, is_city_card, is_event_card


class RoleBehavior:
    role: Role
    cure_cards = 5
    treat_all = False
    build_free = False
    gives_any_city_card = False
    moves_other_pawns = False

    def protects(self, state: GameState, me: int, city: str, ci: int) -> bool:
        return False

    def on_moved(self, state: GameState, me: int, events: list) -> None:
        pass

    def on_cure(self, state: GameState, me: int, ci: int, events: list) -> None:
        pass

    def extra_actions(self, state: GameState, me: int) -> list[Action]:
        return []

    def execute(self, state: GameState, me: int, action: Action, events: list) -> None:
        raise NotImplementedError(type(action).__name__)


class Medic(RoleBehavior):
    role = Role.MEDIC
    treat_all = True

    def protects(self, state, me, city, ci):
        return state.cures[ci] != NONE and state.players[me].location == city

    def _clear(self, state: GameState, me: int, events: list) -> None:
        city = state.players[me].location
        cubes = state.cubes[city]
        for ci in range(4):
            if cubes[ci] and state.cures[ci] != NONE:
                remove_cubes(state, city, ci, None, me, "medic", events)

    def on_moved(self, state, me, events):
        self._clear(state, me, events)

    def on_cure(self, state, me, ci, events):
        self._clear(state, me, events)


class QuarantineSpecialist(RoleBehavior):
    role = Role.QUARANTINE_SPECIALIST

    def protects(self, state, me, city, ci):
        loc = state.players[me].location
        return city == loc or city in neighbors(loc)


class OperationsExpert(RoleBehavior):
    role = Role.OPERATIONS_EXPERT
    build_free = True

    def extra_actions(self, state, me):
        p = state.players[me]
        if p.ops_move_used or p.location not in state.stations:
            return []
        cards = [c for c in p.hand if is_city_card(c)]
        if not cards:
            return []
        return [OperationsMove(dest, card) for card in cards for dest in CITY_NAMES
                if dest != p.location]

    def execute(self, state, me, action, events):
        assert isinstance(action, OperationsMove)
        state.players[me].ops_move_used = True
        discard_card(state, me, action.card, "operations_move", events)
        move_pawn(state, me, action.destination, "operations_move", me, events)


class Dispatcher(RoleBehavior):
    role = Role.DISPATCHER
    moves_other_pawns = True

    def extra_actions(self, state, me):
        out: list[Action] = []
        locs = [p.location for p in state.players]
        for q, loc in enumerate(locs):
            seen: set[str] = set()
            for r, dest in enumerate(locs):
                if r != q and dest != loc and dest not in seen:
                    seen.add(dest)
                    out.append(DispatcherMove(q, dest))
        return out

    def execute(self, state, me, action, events):
        assert isinstance(action, DispatcherMove)
        move_pawn(state, action.pawn, action.destination, "dispatcher_move", me, events)


class Researcher(RoleBehavior):
    role = Role.RESEARCHER
    gives_any_city_card = True


class Scientist(RoleBehavior):
    role = Role.SCIENTIST
    cure_cards = 4


class ContingencyPlanner(RoleBehavior):
    role = Role.CONTINGENCY_PLANNER

    def extra_actions(self, state, me):
        if state.players[me].stored_event is not None:
            return []
        seen: list[Action] = []
        for c in state.player_discard:
            if is_event_card(c):
                seen.append(TakeEventCard(c))
        return seen

    def execute(self, state, me, action, events):
        assert isinstance(action, TakeEventCard)
        state.player_discard.remove(action.card)
        state.players[me].stored_event = action.card
        events.append(EventStored(me, action.card))


_BEHAVIORS: dict[Role, RoleBehavior] = {
    b.role: b
    for b in (Medic(), QuarantineSpecialist(), OperationsExpert(), Dispatcher(),
              Researcher(), Scientist(), ContingencyPlanner())
}

ROLE_ACTION_TYPES = (OperationsMove, DispatcherMove, TakeEventCard)


def behavior(role: Role) -> RoleBehavior:
    return _BEHAVIORS[role]


def placement_blocker(state: GameState, city: str, ci: int) -> Role | None:
    """Role that prevents placing cubes of color ``ci`` (and outbreaks) in ``city``."""
    for i, p in enumerate(state.players):
        if _BEHAVIORS[p.role].protects(state, i, city, ci):
            return p.role
    return None


def notify_cure(state: GameState, ci: int, events: list) -> None:
    for i, p in enumerate(state.players):
        _BEHAVIORS[p.role].on_cure(state, i, ci, events)
