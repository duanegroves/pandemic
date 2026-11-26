import pytest

from pandemic.engine import (
    BuildResearchStation,
    CharterFlight,
    Color,
    DirectFlight,
    Discard,
    DiscoverCure,
    DriveFerry,
    EndActions,
    GiveCard,
    IllegalActionError,
    ShuttleFlight,
    TakeCard,
    TreatDisease,
    current_decision,
    legal_actions,
    step,
)
from pandemic.engine import Role as R

from helpers import check_invariants, make_state

BASIC = (R.CONTINGENCY_PLANNER, R.SCIENTIST)  # roles that don't alter basic actions
BLUE5 = ["Chicago", "Essen", "London", "Madrid", "Milan"]


def test_drive_ferry():
    s = make_state(BASIC, event_windows="off")
    step(s, DriveFerry(0, "Chicago"))
    assert s.players[0].location == "Chicago"
    assert s.actions_remaining == 3
    with pytest.raises(IllegalActionError):
        step(s, DriveFerry(0, "Tokyo"))
    check_invariants(s)


def test_pacific_wrap_drive():
    s = make_state(BASIC, locations=["Los Angeles", "Atlanta"])
    assert DriveFerry(0, "Sydney") in legal_actions(s)


def test_direct_flight_discards_destination_card():
    s = make_state(BASIC, hands=[["Tokyo"], []])
    step(s, DirectFlight(0, "Tokyo"))
    assert s.players[0].location == "Tokyo"
    assert s.players[0].hand == [] and s.player_discard == ["Tokyo"]


def test_charter_flight_discards_current_city_card():
    s = make_state(BASIC, hands=[["Atlanta"], []])
    acts = legal_actions(s)
    assert sum(isinstance(a, CharterFlight) for a in acts) == 47
    step(s, CharterFlight(0, "Sydney"))
    assert s.players[0].location == "Sydney" and s.player_discard == ["Atlanta"]


def test_shuttle_flight():
    s = make_state(BASIC, stations=["Atlanta", "Cairo"])
    step(s, ShuttleFlight(0, "Cairo"))
    assert s.players[0].location == "Cairo"
    assert ShuttleFlight(0, "Atlanta") in legal_actions(s)
    step(s, DriveFerry(0, "Istanbul"))
    assert not any(isinstance(a, ShuttleFlight) for a in legal_actions(s))


def test_four_actions_then_draw():
    s = make_state(BASIC, event_windows="off")
    for dest in ["Chicago", "Atlanta", "Chicago", "Atlanta"]:
        step(s, DriveFerry(0, dest))
    # turn passed to player 1 after drawing and infecting
    assert s.current_player == 1 and s.actions_remaining == 4 and s.turn == 2
    assert len(s.players[0].hand) == 2
    check_invariants(s)


def test_end_actions_early():
    s = make_state(BASIC, event_windows="off")
    step(s, EndActions())
    assert s.current_player == 1
    assert len(s.infection_discard) == 2


def test_build_and_relocate():
    s = make_state(BASIC, hands=[["Atlanta", "Chicago"], []], locations=["Chicago", "Atlanta"])
    assert BuildResearchStation() in legal_actions(s)
    step(s, BuildResearchStation())
    assert "Chicago" in s.stations and "Chicago" not in s.players[0].hand
    assert BuildResearchStation() not in legal_actions(s)  # already has one

    six = ["Atlanta", "Cairo", "Tokyo", "Lima", "Paris", "Delhi"]
    s = make_state(BASIC, hands=[["Chicago"], []], locations=["Chicago", "Atlanta"],
                   stations=six)
    builds = [a for a in legal_actions(s) if isinstance(a, BuildResearchStation)]
    assert builds == [BuildResearchStation(x) for x in six]
    step(s, BuildResearchStation("Tokyo"))
    assert sorted(s.stations) == sorted(["Atlanta", "Cairo", "Lima", "Paris", "Delhi",
                                         "Chicago"])
    check_invariants(s)


def test_treat_uncured_and_cured_and_eradication():
    s = make_state(BASIC, cubes={"Atlanta": 3, "Chicago": 1})
    step(s, TreatDisease(Color.BLUE))
    assert s.cubes["Atlanta"][0] == 2
    s.cures[0] = "cured"
    step(s, TreatDisease(Color.BLUE))
    assert s.cubes["Atlanta"][0] == 0
    assert s.cures[0] == "cured"  # Chicago still has a cube
    step(s, DriveFerry(0, "Chicago"))
    step(s, TreatDisease(Color.BLUE))
    assert s.cures[0] == "eradicated"
    check_invariants(s)


def test_treat_last_uncured_cube_no_eradication():
    s = make_state(BASIC, cubes={"Atlanta": 1})
    step(s, TreatDisease(Color.BLUE))
    assert s.cures[0] == "none" and s.supply[0] == 24


def test_treat_one_color_at_a_time():
    s = make_state(BASIC, cubes={"Atlanta": {"blue": 2, "red": 2}},
                   cures={"blue": "cured", "red": "cured"})
    treats = [a for a in legal_actions(s) if isinstance(a, TreatDisease)]
    assert treats == [TreatDisease(Color.BLUE), TreatDisease(Color.RED)]
    step(s, TreatDisease(Color.RED))
    assert s.cubes["Atlanta"] == [2, 0, 0, 0]


def test_share_knowledge_give_and_take():
    s = make_state(BASIC, hands=[["Atlanta", "Chicago"], ["Essen"]])
    acts = legal_actions(s)
    assert GiveCard(1, "Atlanta") in acts and GiveCard(1, "Chicago") not in acts
    assert TakeCard(1, "Essen") not in acts
    step(s, GiveCard(1, "Atlanta"))
    assert s.players[1].hand == ["Essen", "Atlanta"]
    step(s, TakeCard(1, "Atlanta"))
    assert s.players[0].hand == ["Chicago", "Atlanta"]
    # different cities: no sharing
    step(s, DriveFerry(0, "Chicago"))
    assert not any(isinstance(a, (GiveCard, TakeCard)) for a in legal_actions(s))


def test_share_knowledge_receiver_hand_limit():
    full = ["Chicago", "Essen", "London", "Madrid", "Milan", "Paris", "Tokyo"]
    s = make_state(BASIC, hands=[["Atlanta"], full], event_windows="off")
    step(s, GiveCard(1, "Atlanta"))
    d = current_decision(s)
    assert d.kind == "discard" and d.player == 1
    acts = legal_actions(s)
    assert all(isinstance(a, Discard) for a in acts) and len(acts) == 8
    step(s, Discard("Tokyo"))
    d = current_decision(s)
    assert d.kind == "actions" and d.player == 0 and s.actions_remaining == 3
    assert len(s.players[1].hand) == 7 and s.player_discard == ["Tokyo"]
    check_invariants(s)


def test_discover_cure_chooses_cards_and_eradicates_when_no_cubes():
    hand = BLUE5 + ["Paris", "Tokyo"]
    s = make_state(BASIC, hands=[hand, []], cubes={"Tokyo": 1})
    cures = [a for a in legal_actions(s) if isinstance(a, DiscoverCure)]
    assert len(cures) == 6  # C(6,5)
    chosen = ("Chicago", "Essen", "London", "Madrid", "Paris")
    assert DiscoverCure(Color.BLUE, chosen) in cures
    step(s, DiscoverCure(Color.BLUE, chosen))
    assert s.cures[0] == "eradicated"  # no blue cubes on the board
    assert sorted(s.players[0].hand) == ["Milan", "Tokyo"]
    assert set(chosen) <= set(s.player_discard)
    check_invariants(s)


def test_discover_cure_needs_station_and_leaves_cubes():
    s = make_state(BASIC, hands=[BLUE5, []], locations=["Chicago", "Atlanta"])
    assert not any(isinstance(a, DiscoverCure) for a in legal_actions(s))
    s = make_state(BASIC, hands=[BLUE5, []], cubes={"Paris": 2}, stations=["Atlanta", "Cairo"],
                   locations=["Cairo", "Atlanta"])
    step(s, DiscoverCure(Color.BLUE, tuple(BLUE5)))  # station colour need not match
    assert s.cures[0] == "cured" and s.cubes["Paris"][0] == 2


def test_scientist_cures_with_four():
    s = make_state((R.SCIENTIST, R.CONTINGENCY_PLANNER), hands=[BLUE5[:4], []])
    step(s, DiscoverCure(Color.BLUE, tuple(BLUE5[:4])))
    assert s.cures[0] in ("cured", "eradicated")
    s = make_state(BASIC, hands=[BLUE5[:4], []])
    assert not any(isinstance(a, DiscoverCure) for a in legal_actions(s))


def test_immediate_win():
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[["Bangkok", "Beijing", "Manila", "Osaka"], []],
                   cures={"blue": "cured", "yellow": "eradicated", "black": "cured"},
                   cubes={"Tokyo": 3, "Paris": 3})
    step(s, DiscoverCure(Color.RED, ("Bangkok", "Beijing", "Manila", "Osaka")))
    assert s.outcome == {"result": "win", "reason": "all_diseases_cured"}
    assert legal_actions(s) == []
    assert current_decision(s).kind == "game_over"
    with pytest.raises(IllegalActionError):
        step(s, EndActions())
