from pandemic.engine import (
    BuildResearchStation,
    CharterFlight,
    Color,
    Consent,
    DirectFlight,
    DiscoverCure,
    DispatcherMove,
    DriveFerry,
    EndActions,
    GiveCard,
    OperationsMove,
    PlayAirlift,
    ShuttleFlight,
    TakeCard,
    TakeEventCard,
    TreatDisease,
    current_decision,
    legal_actions,
    step,
)
from pandemic.engine import Role as R
from pandemic.engine.infection import place_cubes

from helpers import check_invariants, make_state


# ---------------------------------------------------------------- Medic
def test_medic_treat_removes_all():
    s = make_state((R.MEDIC, R.SCIENTIST), cubes={"Atlanta": 3})
    step(s, TreatDisease(Color.BLUE))
    assert s.cubes["Atlanta"][0] == 0 and s.cures[0] == "none"


def test_medic_passive_on_entering_city():
    s = make_state((R.MEDIC, R.SCIENTIST), cubes={"Chicago": 2, "Miami": 2},
                   cures={"blue": "cured"})
    step(s, DriveFerry(0, "Chicago"))
    assert s.cubes["Chicago"][0] == 0 and s.cures[0] == "eradicated"
    step(s, DriveFerry(0, "Atlanta"))
    step(s, DriveFerry(0, "Miami"))  # yellow not cured: stays
    assert s.cubes["Miami"][1] == 2


def test_medic_passive_when_airlifted_off_turn():
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[["Airlift"], []], cubes={"Tokyo": 3, "Osaka": 1},
                   cures={"red": "cured"})
    step(s, PlayAirlift(1, "Tokyo"))  # auto_consent default
    assert s.players[1].location == "Tokyo" and s.cubes["Tokyo"][3] == 0
    assert s.cures[3] == "cured"  # Osaka still has a cube
    assert s.actions_remaining == 4  # events are not actions


def test_medic_clears_right_after_cure():
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[["Chicago", "Essen", "London", "Madrid"], []],
                   cubes={"Atlanta": 2})
    step(s, DiscoverCure(Color.BLUE, ("Chicago", "Essen", "London", "Madrid")))
    assert s.cubes["Atlanta"][0] == 0 and s.cures[0] == "eradicated"


def test_medic_prevents_cured_placement_only():
    s = make_state((R.MEDIC, R.SCIENTIST), locations=["Lima", "Atlanta"], cures={"yellow": "cured"})
    place_cubes(s, "Lima", 1, 3, "epidemic", [])
    assert s.cubes["Lima"][1] == 0
    place_cubes(s, "Lima", 0, 1, "outbreak", [])  # blue not cured
    assert s.cubes["Lima"][0] == 1


# ---------------------------------------------------------------- Quarantine Specialist
def test_qs_blocks_city_and_neighbors_and_outbreaks():
    s = make_state((R.QUARANTINE_SPECIALIST, R.SCIENTIST), cubes={"Atlanta": 3, "Montréal": 3})
    ev: list = []
    place_cubes(s, "Atlanta", 0, 1, "infection", ev)  # her city: no outbreak
    place_cubes(s, "Chicago", 0, 1, "infection", ev)  # neighbour
    assert s.outbreaks == 0 and s.cubes["Chicago"][0] == 0
    place_cubes(s, "Montréal", 0, 1, "infection", ev)  # outbreak next to protected cities
    assert s.outbreaks == 1
    assert s.cubes["Chicago"][0] == 0 and s.cubes["Washington"][0] == 0
    assert s.cubes["New York"][0] == 1
    check_invariants(s)


def test_qs_does_not_affect_setup():
    from pandemic.engine import GameConfig, new_game
    for seed in range(20):
        s = new_game(GameConfig(num_players=2, roles=["quarantine_specialist", "medic"]), seed)
        assert sum(sum(v) for v in s.cubes.values()) == 18


# ---------------------------------------------------------------- Operations Expert
def test_ops_free_build():
    s = make_state((R.OPERATIONS_EXPERT, R.SCIENTIST), locations=["Cairo", "Atlanta"])
    step(s, BuildResearchStation())
    assert "Cairo" in s.stations and s.player_discard == []


def test_ops_move_once_per_turn():
    s = make_state((R.OPERATIONS_EXPERT, R.SCIENTIST), hands=[["Tokyo", "Lima"], []],
                   event_windows="off")
    moves = [a for a in legal_actions(s) if isinstance(a, OperationsMove)]
    assert len(moves) == 2 * 47
    step(s, OperationsMove("Sydney", "Lima"))
    assert s.players[0].location == "Sydney" and s.player_discard == ["Lima"]
    step(s, BuildResearchStation())
    assert not any(isinstance(a, OperationsMove) for a in legal_actions(s))  # used this turn
    step(s, EndActions())  # player 1's turn
    step(s, EndActions())  # back to ops
    assert s.current_player == 0 and any(isinstance(a, OperationsMove)
                                         for a in legal_actions(s))


def test_ops_move_requires_station():
    s = make_state((R.OPERATIONS_EXPERT, R.SCIENTIST), hands=[["Tokyo"], []],
                   locations=["Chicago", "Atlanta"])
    assert not any(isinstance(a, OperationsMove) for a in legal_actions(s))


# ---------------------------------------------------------------- Dispatcher
def test_dispatcher_moves_pawn_to_pawn():
    s = make_state((R.DISPATCHER, R.SCIENTIST, R.MEDIC), locations=["Atlanta", "Tokyo", "Lima"])
    acts = legal_actions(s)
    assert DispatcherMove(1, "Lima") in acts and DispatcherMove(0, "Tokyo") in acts
    assert DispatcherMove(1, "Tokyo") not in acts
    step(s, DispatcherMove(2, "Tokyo"))
    assert s.players[2].location == "Tokyo"


def test_dispatcher_moves_other_as_own_with_own_cards():
    s = make_state((R.DISPATCHER, R.SCIENTIST), hands=[["Tokyo", "Lima"], ["Paris"]],
                   locations=["Atlanta", "Lima"], stations=["Atlanta", "Lima", "Cairo"])
    acts = legal_actions(s)
    assert DriveFerry(1, "Santiago") in acts
    assert DirectFlight(1, "Tokyo") in acts
    assert CharterFlight(1, "Sydney") in acts  # Dispatcher's Lima card matches *from* city
    assert ShuttleFlight(1, "Cairo") in acts
    assert DirectFlight(1, "Paris") not in acts  # not the Dispatcher's card
    step(s, CharterFlight(1, "Sydney"))
    assert s.players[1].location == "Sydney" and s.players[0].hand == ["Tokyo"]
    assert s.players[1].hand == ["Paris"]
    # charter for the other pawn needs the card of the pawn's city, not the Dispatcher's
    s = make_state((R.DISPATCHER, R.SCIENTIST), hands=[["Atlanta"], []],
                   locations=["Atlanta", "Lima"])
    acts = legal_actions(s)
    assert not any(isinstance(a, CharterFlight) and a.pawn == 1 for a in acts)
    assert any(isinstance(a, CharterFlight) and a.pawn == 0 for a in acts)


def test_dispatcher_cannot_use_ops_move_for_ops():
    s = make_state((R.DISPATCHER, R.OPERATIONS_EXPERT), hands=[["Tokyo"], ["Lima"]])
    assert not any(isinstance(a, OperationsMove) for a in legal_actions(s))


def test_dispatcher_needs_consent():
    s = make_state((R.DISPATCHER, R.SCIENTIST), auto_consent=False)
    step(s, DriveFerry(1, "Chicago"))
    d = current_decision(s)
    assert d.kind == "consent" and d.player == 1
    assert legal_actions(s) == [Consent(True), Consent(False)]
    step(s, Consent(False))
    assert s.players[1].location == "Atlanta" and s.actions_remaining == 4
    step(s, DriveFerry(1, "Chicago"))
    step(s, Consent(True))
    assert s.players[1].location == "Chicago" and s.actions_remaining == 3
    step(s, DriveFerry(0, "Chicago"))  # own pawn: no consent
    assert current_decision(s).kind == "actions"


# ---------------------------------------------------------------- Researcher
def test_researcher_gives_any_city_card():
    s = make_state((R.RESEARCHER, R.SCIENTIST), hands=[["Tokyo", "Airlift"], ["Lima"]])
    acts = legal_actions(s)
    assert GiveCard(1, "Tokyo") in acts and GiveCard(1, "Airlift") not in acts
    assert TakeCard(1, "Lima") not in acts  # she takes by the normal rule
    step(s, GiveCard(1, "Tokyo"))
    assert "Tokyo" in s.players[1].hand


def test_others_take_any_city_card_from_researcher():
    s = make_state((R.SCIENTIST, R.RESEARCHER), hands=[[], ["Tokyo", "Lima"]],
                   locations=["Cairo", "Cairo"])
    acts = legal_actions(s)
    assert TakeCard(1, "Tokyo") in acts and TakeCard(1, "Lima") in acts
    step(s, TakeCard(1, "Lima"))
    assert s.players[0].hand == ["Lima"]


# ---------------------------------------------------------------- Contingency Planner
def test_contingency_planner_store_and_play_removes_from_game():
    s = make_state((R.CONTINGENCY_PLANNER, R.SCIENTIST), player_discard=["Airlift", "Essen"],
                   hands=[["Paris"], []])
    acts = legal_actions(s)
    assert TakeEventCard("Airlift") in acts and TakeEventCard("Essen") not in acts
    step(s, TakeEventCard("Airlift"))
    assert s.players[0].stored_event == "Airlift" and "Airlift" not in s.player_discard
    assert s.players[0].hand == ["Paris"]  # stored card is outside the hand
    assert s.actions_remaining == 3
    assert not any(isinstance(a, TakeEventCard) for a in legal_actions(s))  # max 1
    step(s, PlayAirlift(0, "Tokyo"))
    assert s.players[0].location == "Tokyo" and s.players[0].stored_event is None
    assert "Airlift" in s.player_removed and "Airlift" not in s.player_discard
    check_invariants(s)


def test_contingency_planner_stored_event_outside_hand_limit():
    hand = ["Chicago", "Essen", "London", "Madrid", "Milan"]
    s = make_state((R.CONTINGENCY_PLANNER, R.SCIENTIST), hands=[hand, []],
                   player_deck=["Paris", "Tokyo", "Lima", "Cairo"], event_windows="off")
    s.players[0].stored_event = "Forecast"
    s.player_removed.remove("Forecast")
    step(s, EndActions())
    assert len(s.players[0].hand) == 7 and s.current_player == 1  # no discard decision
    check_invariants(s)
