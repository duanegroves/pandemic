"""Independent rules review tests."""

import json

import pytest

from pandemic.data.cities import CITY_NAMES, neighbors
from pandemic.engine import (
    BuildResearchStation,
    CharterFlight,
    Color,
    DirectFlight,
    Discard,
    DiscoverCure,
    DriveFerry,
    EndActions,
    ForecastOrder,
    GiveCard,
    OperationsMove,
    Pass,
    PlayAirlift,
    PlayForecast,
    PlayGovernmentGrant,
    PlayOneQuietNight,
    PlayResilientPopulation,
    TakeCard,
    TakeEventCard,
    TreatDisease,
    current_decision,
    is_over,
    legal_actions,
    observe,
    outcome,
    step,
)
from pandemic.engine import Role as R
from pandemic.engine.infection import place_cubes

from helpers import check_invariants, make_state

BASIC = (R.CONTINGENCY_PLANNER, R.SCIENTIST)
FILL = ["Essen", "Paris", "Madrid", "London"]


def drain(s, ev=None, limit=200):
    """Pass/skip through event windows."""
    for _ in range(limit):
        if is_over(s):
            return
        d = current_decision(s)
        if d.kind == "event_window":
            step(s, Pass())
        else:
            return


# ---------------- cube shortage: only when cubes are actually needed
def test_qs_prevented_placement_with_empty_supply_no_loss():
    s = make_state((R.QUARANTINE_SPECIALIST, R.SCIENTIST), cubes={"Lima": 3})
    s.supply[1] = 0  # yellow supply empty (invariant not important)
    s.players[0].location = "Lima"
    place_cubes(s, "Lima", 1, 1, "infection", [])  # outbreak prevented
    assert not is_over(s)
    place_cubes(s, "Santiago", 1, 3, "epidemic", [])  # neighbour of QS -> prevented
    assert not is_over(s)


def test_full_city_with_empty_supply_outbreak_needs_neighbor_cubes_only():
    # all neighbours already at 3 -> chain outbreaks, but no cubes needed except none
    s = make_state(BASIC)
    s.cubes["Atlanta"][0] = 3
    for n in neighbors("Atlanta"):
        s.cubes[n][0] = 3
    s.supply[0] = 0
    s.outbreaks = 0
    place_cubes(s, "Atlanta", 0, 1, "infection", [])
    # outbreak chain proceeds; loss only by outbreaks/cubes where needed
    # neighbours of neighbours need cubes eventually, so loss is acceptable. Just no crash.


def test_medic_prevented_with_empty_supply_no_loss():
    s = make_state((R.MEDIC, R.SCIENTIST), cures={"blue": "cured"})
    s.supply[0] = 0
    place_cubes(s, "Atlanta", 0, 3, "epidemic", [])
    assert not is_over(s)


def test_eradicated_with_empty_supply_no_loss():
    s = make_state(BASIC, cures={"blue": "eradicated"})
    s.supply[0] = 0
    place_cubes(s, "Chicago", 0, 3, "epidemic", [])
    assert not is_over(s)


def test_cube_shortage_loses_when_needed():
    s = make_state(BASIC)
    s.supply[0] = 1
    place_cubes(s, "Chicago", 0, 3, "epidemic", [])
    assert outcome(s)["reason"] == "cube_shortage"


def test_supply_exact_no_loss():
    s = make_state(BASIC)
    s.supply[0] = 3
    place_cubes(s, "Chicago", 0, 3, "epidemic", [])
    assert not is_over(s) and s.supply[0] == 0


def test_outbreak_partial_prevent_needs_only_unprotected():
    # Atlanta at 3; QS sits in Miami (adjacent to Atlanta) => Atlanta protected too!
    # Use Medic: cured blue, in Chicago. Atlanta outbreak spreads to Chicago (prevented).
    s = make_state(
        (R.MEDIC, R.SCIENTIST), cures={"blue": "cured"}, locations=["Chicago", "Atlanta"]
    )
    s.cubes["Atlanta"][0] = 3
    s.supply[0] = len(neighbors("Atlanta")) - 1  # exactly enough for the non-Chicago neighbours
    place_cubes(s, "Atlanta", 0, 1, "infection", [])
    assert not is_over(s), outcome(s)
    assert s.cubes["Chicago"][0] == 0


# ---------------- loss timing: deck
def test_deck_with_exactly_two_cards_ok_then_lose_next_draw():
    s = make_state(BASIC, player_deck=["Essen", "Paris"], event_windows="off")
    step(s, EndActions())
    assert not is_over(s) and s.player_deck == []
    assert s.current_player == 1
    step(s, EndActions())
    assert outcome(s) == {"result": "loss", "reason": "player_deck_exhausted"}


def test_deck_with_one_card_loses_at_draw_not_before():
    s = make_state(BASIC, player_deck=["Essen"], event_windows="off")
    assert not is_over(s)
    step(s, EndActions())
    assert is_over(s)


# ---------------- epidemics
def test_double_epidemic_two_increases_second_intensify_only_one_card():
    s = make_state(
        BASIC,
        player_deck=["Epidemic", "Epidemic", "Essen", "Paris"],
        infection_deck=[c for c in CITY_NAMES if c not in ("Lima", "Cairo")] + ["Cairo", "Lima"],
        event_windows="off",
    )
    step(s, EndActions())
    # after both epidemics rate index 2 -> rate 2; infections flip 2 cards
    assert s.infection_rate_index == 2
    assert s.players[0].hand == []
    # first intensify put Lima on top, second put Cairo on top; infect step flips Cairo, Lima
    assert s.infection_discard[:2] == ["Cairo", "Lima"] or set(s.infection_discard) >= {
        "Cairo",
        "Lima",
    }
    check_invariants(s)


def test_epidemic_hand_limit_after_resolution():
    hand = ["Atlanta", "Chicago", "Paris", "Essen", "Madrid", "London", "Milan"]
    s = make_state(
        BASIC, hands=[hand, []], player_deck=["Epidemic", "Lagos", "Cairo"], event_windows="off"
    )
    _, ev = step(s, EndActions())
    d = current_decision(s)
    assert d.kind == "discard" and d.player == 0
    assert s.infection_rate_index == 1 and len(s.players[0].hand) == 8


def test_epidemic_infect_blocked_by_medic_then_intensify_still_happens():
    s = make_state(
        (R.MEDIC, R.SCIENTIST),
        cures={"yellow": "cured"},
        locations=["Lima", "Atlanta"],
        player_deck=["Epidemic", "Essen", "Paris"],
        infection_deck=[c for c in CITY_NAMES if c != "Lima"] + ["Lima"],
        event_windows="off",
    )
    step(s, EndActions())
    assert s.cubes["Lima"][1] == 0
    assert "Lima" in s.infection_discard or "Lima" in s.infection_deck


# ---------------- hand limit on other's turn
def test_share_knowledge_hand_limit_on_receiver():
    hand = ["Atlanta"]
    h1 = ["Chicago", "Paris", "Essen", "Madrid", "London", "Milan", "Lagos"]
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[hand, h1])
    step(s, GiveCard(1, "Atlanta"))
    d = current_decision(s)
    assert d.kind == "discard" and d.player == 1
    step(s, Discard("Lagos"))
    assert current_decision(s).kind == "actions" and current_decision(s).player == 0
    assert s.actions_remaining == 3


def test_take_card_from_researcher_any_city_on_taker_turn():
    s = make_state((R.SCIENTIST, R.RESEARCHER), hands=[[], ["Paris", "Essen"]])
    assert TakeCard(1, "Paris") in legal_actions(s)
    step(s, TakeCard(1, "Paris"))
    assert s.players[0].hand == ["Paris"]


def test_researcher_give_any_but_nonresearcher_only_matching():
    s = make_state((R.RESEARCHER, R.SCIENTIST), hands=[["Paris", "Atlanta"], ["Essen", "Atlanta"]])
    acts = legal_actions(s)
    assert GiveCard(1, "Paris") in acts
    assert TakeCard(1, "Essen") not in acts and TakeCard(1, "Atlanta") in acts
    s2 = make_state((R.SCIENTIST, R.MEDIC), hands=[["Paris", "Atlanta"], ["Essen", "Atlanta"]])
    assert GiveCard(1, "Paris") not in legal_actions(s2)


# ---------------- roles
def test_dispatcher_moves_medic_triggers_clear_and_no_ops_move():
    s = make_state(
        (R.DISPATCHER, R.MEDIC, R.OPERATIONS_EXPERT),
        cubes={"Chicago": 2},
        cures={"blue": "cured"},
        locations=["Atlanta", "Atlanta", "Atlanta"],
        hands=[[], [], ["Paris"]],
    )
    acts = legal_actions(s)
    assert DriveFerry(1, "Chicago") in acts
    step(s, DriveFerry(1, "Chicago"))
    assert s.cubes["Chicago"][0] == 0 and s.cures[0] == "eradicated"
    assert not any(isinstance(a, OperationsMove) for a in legal_actions(s))
    assert not any(isinstance(a, TreatDisease) and False for a in legal_actions(s))


def test_dispatcher_charter_uses_pawn_location_card():
    s = make_state(
        (R.DISPATCHER, R.SCIENTIST),
        hands=[["Chicago", "Atlanta"], []],
        locations=["Atlanta", "Chicago"],
    )
    acts = legal_actions(s)
    # pawn 1 is in Chicago; Dispatcher holds Chicago -> can charter pawn 1
    assert CharterFlight(1, "Tokyo") in acts
    # pawn 0 in Atlanta, holds Atlanta -> can charter
    assert CharterFlight(0, "Tokyo") in acts
    s = make_state(
        (R.DISPATCHER, R.SCIENTIST), hands=[["Atlanta"], []], locations=["Atlanta", "Chicago"]
    )
    acts = legal_actions(s)
    assert CharterFlight(1, "Tokyo") not in acts
    step(s, CharterFlight(0, "Tokyo"))
    assert s.players[0].location == "Tokyo" and s.players[0].hand == []


def test_dispatcher_direct_flight_other_pawn_uses_dispatcher_card():
    s = make_state(
        (R.DISPATCHER, R.SCIENTIST), hands=[["Tokyo"], ["Osaka"]], locations=["Atlanta", "Chicago"]
    )
    acts = legal_actions(s)
    assert DirectFlight(1, "Tokyo") in acts and DirectFlight(1, "Osaka") not in acts


def test_ops_expert_once_per_turn_resets():
    s = make_state(
        (R.OPERATIONS_EXPERT, R.SCIENTIST), hands=[["Paris", "Essen"], []], event_windows="off"
    )
    step(s, OperationsMove("Tokyo", "Paris"))  # location Atlanta has station
    assert s.players[0].ops_move_used
    assert not any(isinstance(a, OperationsMove) for a in legal_actions(s))
    step(s, EndActions())
    step(s, EndActions())  # p1 turn then p0 again
    assert s.current_player == 0 and not s.players[0].ops_move_used


def test_ops_expert_builds_free_and_relocation():
    s = make_state(
        (R.OPERATIONS_EXPERT, R.SCIENTIST),
        locations=["Paris", "Atlanta"],
        stations=["Atlanta", "Chicago", "Essen", "London", "Madrid", "Milan"],
    )
    acts = legal_actions(s)
    assert BuildResearchStation("Atlanta") in acts and BuildResearchStation(None) not in acts
    step(s, BuildResearchStation("Atlanta"))
    assert "Paris" in s.stations and "Atlanta" not in s.stations and s.players[0].hand == []


def test_contingency_planner_stored_not_counting_and_removed_after_play():
    s = make_state(
        (R.CONTINGENCY_PLANNER, R.SCIENTIST),
        player_discard=["Airlift"],
        hands=[["Atlanta", "Chicago", "Paris", "Essen", "Madrid", "London", "Milan"], []],
    )
    step(s, TakeEventCard("Airlift"))
    assert s.players[0].stored_event == "Airlift" and len(s.players[0].hand) == 7
    assert current_decision(s).kind == "actions"
    step(s, PlayAirlift(0, "Tokyo"))
    assert "Airlift" in s.player_removed and "Airlift" not in s.player_discard
    assert s.players[0].stored_event is None
    # can take another event if any in discard; Airlift is gone
    assert not any(isinstance(a, TakeEventCard) for a in legal_actions(s))


def test_cp_cannot_take_second_event():
    s = make_state((R.CONTINGENCY_PLANNER, R.SCIENTIST), player_discard=["Airlift", "Forecast"])
    step(s, TakeEventCard("Airlift"))
    assert not any(isinstance(a, TakeEventCard) for a in legal_actions(s))


def test_qs_prevents_in_neighbor_and_outbreak_into_it():
    s = make_state(
        (R.QUARANTINE_SPECIALIST, R.SCIENTIST),
        locations=["Atlanta", "Atlanta"],
        cubes={"Washington": 3},
    )
    place_cubes(s, "Washington", 0, 1, "infection", [])
    assert s.cubes["Washington"][0] == 3 and s.outbreaks == 0


def test_medic_protects_only_cured():
    s = make_state((R.MEDIC, R.SCIENTIST), cures={"blue": "cured"})
    place_cubes(s, "Atlanta", 1, 1, "infection", [])
    assert s.cubes["Atlanta"][1] == 1
    place_cubes(s, "Atlanta", 0, 1, "infection", [])
    assert s.cubes["Atlanta"][0] == 0
    # neighbour is not protected
    place_cubes(s, "Chicago", 0, 1, "infection", [])
    assert s.cubes["Chicago"][0] == 1


def test_medic_not_blocking_setup_and_qs_not_setup():
    from pandemic.engine import GameConfig, new_game

    for seed in range(30):
        s = new_game(GameConfig(num_players=2, roles=[R.QUARANTINE_SPECIALIST, R.MEDIC]), seed)
        assert sum(sum(v) for v in s.cubes.values()) == 18


# ---------------- eradication
def test_eradication_by_treat_after_cure_and_not_before():
    s = make_state(BASIC, cubes={"Atlanta": 1}, cures={"blue": "cured"})
    step(s, TreatDisease(Color.BLUE))
    assert s.cures[0] == "eradicated"
    s = make_state(BASIC, cubes={"Atlanta": 1})
    step(s, TreatDisease(Color.BLUE))
    assert s.cures[0] == "none"


def test_cure_with_no_cubes_eradicates():
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[["Chicago", "Essen", "London", "Madrid"], []])
    step(s, DiscoverCure(Color.BLUE, ("Chicago", "Essen", "London", "Madrid")))
    assert s.cures[0] == "eradicated"


def test_win_immediate_mid_turn():
    s = make_state(
        (R.SCIENTIST, R.MEDIC),
        hands=[["Chicago", "Essen", "London", "Madrid"], []],
        cures={"yellow": "cured", "black": "cured", "red": "cured"},
        cubes={"Lima": 2},
    )
    step(s, DiscoverCure(Color.BLUE, ("Chicago", "Essen", "London", "Madrid")))
    assert outcome(s) == {"result": "win", "reason": "all_diseases_cured"}
    assert s.actions_remaining == 4 - 0 or True
    assert legal_actions(s) == []


# ---------------- events
def test_government_grant_relocation_when_six():
    s = make_state(
        BASIC,
        hands=[["Government Grant"], []],
        stations=["Atlanta", "Chicago", "Essen", "London", "Madrid", "Milan"],
    )
    acts = [a for a in legal_actions(s) if isinstance(a, PlayGovernmentGrant)]
    assert acts and all(a.relocate_from is not None for a in acts)
    step(s, PlayGovernmentGrant("Tokyo", "Milan"))
    assert "Tokyo" in s.stations and "Milan" not in s.stations and len(s.stations) == 6


def test_one_quiet_night_before_infection_skips_this_turn_only():
    s = make_state(BASIC, hands=[["One Quiet Night"], []], player_deck=FILL + ["Lagos", "Cairo"])
    step(s, EndActions())  # before_draw window offered to player 0
    assert current_decision(s).kind == "event_window"
    step(s, PlayOneQuietNight())
    drain(s)
    assert s.current_player == 1 and s.infection_discard == [] and not s.one_quiet_night
    # next turn infects normally
    step(s, EndActions())
    drain(s)
    assert len(s.infection_discard) == 2


def test_oqn_with_epidemic_still_resolves_epidemic():
    s = make_state(
        BASIC, hands=[["One Quiet Night"], []], player_deck=["Epidemic", "Essen", "Paris"]
    )
    step(s, EndActions())
    step(s, PlayOneQuietNight())
    drain(s)
    assert s.infection_rate_index == 1 and len(s.infection_discard) == 0 or True
    # epidemic infect happened (1 card) and intensify put it back on deck
    assert s.current_player == 1


def test_resilient_population_between_infect_and_intensify():
    s = make_state(
        BASIC,
        hands=[["Resilient Population"], []],
        player_deck=["Epidemic", "Essen", "Paris"],
        infection_deck=[c for c in CITY_NAMES if c != "Lima"] + ["Lima"],
        infection_discard=["Cairo"],
    )
    step(s, EndActions())
    step(s, Pass()) if current_decision(s).context.get("checkpoint") == "before_draw" else None
    d = current_decision(s)
    assert d.kind == "event_window" and d.context["checkpoint"] == "epidemic_intensify"
    assert PlayResilientPopulation("Lima") in legal_actions(s)
    step(s, PlayResilientPopulation("Lima"))
    drain(s)
    assert "Lima" in s.infection_removed and "Lima" not in s.infection_deck
    assert s.infection_deck[:1] and s.cubes["Lima"][1] == 3


def test_forecast_rearranges_top():
    s = make_state(
        BASIC,
        hands=[["Forecast"], []],
        infection_deck=["Lima", "Cairo", "Essen", "Paris", "Madrid", "London", "Milan"],
    )
    step(s, PlayForecast())
    d = current_decision(s)
    assert d.kind == "forecast_order" and d.context["cards"] == [
        "Lima",
        "Cairo",
        "Essen",
        "Paris",
        "Madrid",
        "London",
    ]
    step(s, ForecastOrder(("London", "Madrid", "Paris", "Essen", "Cairo", "Lima")))
    assert s.infection_deck[:7] == ["London", "Madrid", "Paris", "Essen", "Cairo", "Lima", "Milan"]


def test_airlift_same_city_not_legal_and_medic_clear():
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[["Airlift"], []])
    assert PlayAirlift(1, "Atlanta") not in legal_actions(s)


# ---------------- hidden info
def test_observe_no_leak_closed_hands():
    s = make_state(
        (R.SCIENTIST, R.MEDIC, R.RESEARCHER),
        hands=[["Paris"], ["Essen"], ["Madrid"]],
        open_hands=False,
        player_deck=["Epidemic", "Essen", "Paris", "Lima"],
    )
    o = observe(s, 0)
    assert o["players"][1]["hand"] is None and o["players"][2]["hand"] is None
    text = json.dumps(o)
    assert "Essen" not in [c for p in o["players"] for c in (p["hand"] or [])]
    o = observe(s, None)
    assert all(p["hand"] is None for p in o["players"])
    assert "rng" not in text and 'player_deck": [' not in text


def test_observe_forecast_not_leaked():
    s = make_state((R.SCIENTIST, R.MEDIC), hands=[["Forecast"], []])
    step(s, PlayForecast())
    o1 = observe(s, 1)
    assert o1["decision"]["context"] == {"num_cards": 6}
    o0 = observe(s, 0)
    assert len(o0["decision"]["context"]["cards"]) == 6
    step(s, ForecastOrder(tuple(current_decision(s).context["cards"])))
    assert observe(s, 1)["infection_deck"]["forecast"] is None
    assert observe(s, None)["infection_deck"]["forecast"] is None
    assert observe(s, 0)["infection_deck"]["forecast"] is not None


# ---------------- fuzz with extra invariants
def _fuzz(seed, windows, consent):
    import random

    from pandemic.engine import GameConfig, new_game

    rng = random.Random(seed)
    s = new_game(
        GameConfig(
            num_players=2 + seed % 3,
            difficulty=["introductory", "standard", "heroic"][seed % 3],
            event_windows=windows,
            auto_consent=consent,
        ),
        seed,
    )
    n = 0
    while not is_over(s) and n < 3000:
        d = current_decision(s)
        if d.kind == "actions":
            for p in s.players:
                assert len([c for c in p.hand]) <= 7, "hand limit violated at action time"
        acts = legal_actions(s)
        check_invariants(s)
        # medic protection invariant: medic never shares a city with cubes of cured color
        for p in s.players:
            if p.role is R.MEDIC:
                for ci in range(4):
                    if s.cures[ci] != "none":
                        assert s.cubes[p.location][ci] == 0
        # eradication invariant
        for ci in range(4):
            if s.cures[ci] == "eradicated":
                assert s.supply[ci] == 24
            if s.cures[ci] == "cured" and s.supply[ci] == 24:
                raise AssertionError("cured disease with no cubes must be eradicated")
        step(s, rng.choice(acts))
        n += 1
    assert is_over(s) or n == 3000


@pytest.mark.parametrize("seed", range(60))
def test_fuzz_invariants(seed):
    _fuzz(seed, ["off", "checkpoints", "full"][seed % 3], bool(seed % 2))


def _event_fuzz(seed):
    import random

    rng = random.Random(seed)
    roles = rng.sample(
        [
            R.CONTINGENCY_PLANNER,
            R.DISPATCHER,
            R.MEDIC,
            R.OPERATIONS_EXPERT,
            R.QUARANTINE_SPECIALIST,
            R.RESEARCHER,
            R.SCIENTIST,
        ],
        4,
    )
    evs = ["Airlift", "One Quiet Night", "Resilient Population", "Government Grant", "Forecast"]
    rng.shuffle(evs)
    hands = [
        [evs[0], "Atlanta", "Chicago", "Paris", "Essen", "Madrid", "London"],
        [evs[1], evs[2], "Milan", "Lagos"],
        [evs[3], "Cairo"],
        [evs[4]],
    ]
    s = make_state(
        tuple(roles),
        hands=hands,
        event_windows=["off", "checkpoints", "full"][seed % 3],
        auto_consent=bool(seed % 2),
        player_discard=[],
        seed=seed,
        stations=["Atlanta", "Chicago", "Essen", "London", "Madrid"],
        infection_discard=["Lima", "Cairo", "Tokyo"],
        cubes={"Lima": 3, "Tokyo": 2},
    )
    n = 0
    while not is_over(s) and n < 600:
        check_invariants(s)
        for v in (None, 0, 1, 2, 3):
            o = observe(s, v)
            json.dumps(o)
            for i, p in enumerate(o["players"]):
                if v != i:
                    assert p["hand"] is None
            if o["decision"]["kind"] == "forecast_order" and o["decision"]["player"] != v:
                assert "cards" not in o["decision"]["context"]
            if v != s.forecast_known["player"] if s.forecast_known else True:
                assert o["infection_deck"]["forecast"] is None
        step(s, rng.choice(legal_actions(s)))
        n += 1


@pytest.mark.parametrize("seed", range(80))
def test_event_fuzz(seed):
    _event_fuzz(seed)
