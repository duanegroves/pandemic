import pytest

from pandemic.data.cities import CITY_NAMES
from pandemic.engine import (
    Consent,
    Discard,
    EndActions,
    ForecastOrder,
    GiveCard,
    Pass,
    PlayAirlift,
    PlayForecast,
    PlayGovernmentGrant,
    PlayOneQuietNight,
    PlayResilientPopulation,
    current_decision,
    legal_actions,
    observe,
    step,
)
from pandemic.engine import Role as R

from helpers import check_invariants, make_state

BASIC = (R.CONTINGENCY_PLANNER, R.SCIENTIST)


def test_airlift_self_and_other_with_consent():
    s = make_state(BASIC, hands=[["Airlift"], []], auto_consent=False)
    step(s, PlayAirlift(1, "Tokyo"))
    d = current_decision(s)
    assert d.kind == "consent" and d.player == 1
    assert d.context["request"] == {"type": "play_airlift", "pawn": 1, "destination": "Tokyo"}
    step(s, Consent(False))
    assert s.players[1].location == "Atlanta" and "Airlift" in s.players[0].hand
    step(s, PlayAirlift(0, "Lima"))  # own pawn, no consent
    assert s.players[0].location == "Lima" and s.player_discard == ["Airlift"]
    assert s.actions_remaining == 4


def test_one_quiet_night_skips_next_infect_step():
    s = make_state(BASIC, hands=[["One Quiet Night"], []], event_windows="off",
                   player_deck=["Essen", "Paris", "Lima", "Cairo"])
    step(s, PlayOneQuietNight())
    assert PlayOneQuietNight not in {type(a) for a in legal_actions(s)}
    top = list(s.infection_deck)
    step(s, EndActions())
    assert s.infection_deck == top and s.infection_discard == []
    assert not s.one_quiet_night
    step(s, EndActions())  # next player's infections happen normally
    assert len(s.infection_discard) == 2


def test_resilient_population_mid_epidemic():
    deck = [c for c in CITY_NAMES if c != "Lima"] + ["Lima"]
    s = make_state(BASIC, hands=[[], ["Resilient Population", "Airlift"]], infection_deck=deck,
                   player_deck=["Epidemic", "Essen", "Paris"], infection_discard=["Cairo"])
    step(s, EndActions())
    d = current_decision(s)
    # before_draw window offered to the event holder (player 1)
    assert d.kind == "event_window" and d.context["checkpoint"] == "before_draw"
    step(s, Pass())
    d = current_decision(s)
    assert d.kind == "event_window" and d.context["checkpoint"] == "epidemic_intensify"
    assert d.player == 1
    acts = legal_actions(s)
    assert {type(a) for a in acts} == {PlayResilientPopulation, Pass}  # RP only here
    assert s.cubes["Lima"][1] == 3 and set(s.infection_discard) == {"Cairo", "Lima"}
    step(s, PlayResilientPopulation("Lima"))
    assert "Lima" in s.infection_removed and "Lima" not in s.infection_deck
    # window closes automatically (no more RP); intensify, then before_infection window
    d = current_decision(s)
    assert d.kind == "event_window" and d.context["checkpoint"] == "before_infection"
    assert s.infection_deck[0] == "Cairo"
    check_invariants(s)


def test_government_grant_and_relocation():
    s = make_state(BASIC, hands=[["Government Grant"], []])
    grants = [a for a in legal_actions(s) if isinstance(a, PlayGovernmentGrant)]
    assert len(grants) == 47
    step(s, PlayGovernmentGrant("Tokyo"))
    assert s.stations == ["Atlanta", "Tokyo"]
    six = ["Atlanta", "Cairo", "Tokyo", "Lima", "Paris", "Delhi"]
    s = make_state(BASIC, hands=[["Government Grant"], []], stations=six)
    assert PlayGovernmentGrant("Sydney") not in legal_actions(s)
    step(s, PlayGovernmentGrant("Sydney", "Cairo"))
    assert "Sydney" in s.stations and "Cairo" not in s.stations and len(s.stations) == 6


def test_forecast_reorder_and_knowledge():
    s = make_state(BASIC, hands=[["Forecast"], []], event_windows="off")
    top6 = s.infection_deck[:6]
    step(s, PlayForecast())
    d = current_decision(s)
    assert d.kind == "forecast_order" and d.player == 0 and d.context["cards"] == top6
    assert len(legal_actions(s)) == 720
    assert observe(s, 1)["decision"]["context"] == {"num_cards": 6}
    new = tuple(reversed(top6))
    step(s, ForecastOrder(new))
    assert s.infection_deck[:6] == list(new)
    assert observe(s, 0)["infection_deck"]["forecast"] == {"cards_above": 0, "order": list(new)}
    assert observe(s, 1)["infection_deck"]["forecast"] is None
    step(s, EndActions())  # flips the 2 top cards
    assert s.infection_discard == list(new[:2])
    assert observe(s, 0)["infection_deck"]["forecast"]["order"] == list(new[2:])
    check_invariants(s)


def test_forecast_merges_public_known_sets():
    s = make_state(BASIC, hands=[["Forecast"], []], event_windows="off")
    s.infection_known = [s.infection_deck[:2], s.infection_deck[2:9]]
    step(s, PlayForecast())
    step(s, ForecastOrder(tuple(s.infection_deck[:6][::-1])))
    assert len(s.infection_known) == 1 and len(s.infection_known[0]) == 9
    check_invariants(s)
    s = make_state(BASIC, hands=[["Forecast"], []], event_windows="off")
    s.infection_known = [s.infection_deck[:3]]
    step(s, PlayForecast())
    step(s, ForecastOrder(tuple(s.infection_deck[:6][::-1])))
    assert s.infection_known == []  # no longer reliable
    check_invariants(s)


def test_event_played_instead_of_discarding():
    hand = ["Chicago", "Essen", "London", "Madrid", "Milan", "Airlift"]
    s = make_state(BASIC, hands=[hand, []], player_deck=["Paris", "Tokyo", "Lima", "Cairo"],
                   event_windows="off")
    step(s, EndActions())
    d = current_decision(s)
    assert d.kind == "discard" and d.player == 0 and len(s.players[0].hand) == 8
    acts = legal_actions(s)
    assert Discard("Airlift") in acts and PlayAirlift(1, "Tokyo") in acts
    step(s, PlayAirlift(0, "Tokyo"))
    assert len(s.players[0].hand) == 7 and s.players[0].location == "Tokyo"
    assert current_decision(s).kind == "actions" and s.current_player == 1
    check_invariants(s)


def test_receiver_plays_event_instead_of_discarding_after_share():
    full = ["Chicago", "Essen", "London", "Madrid", "Milan", "Paris", "One Quiet Night"]
    s = make_state(BASIC, hands=[["Atlanta"], full], event_windows="off")
    step(s, GiveCard(1, "Atlanta"))
    assert current_decision(s).kind == "discard"
    step(s, PlayOneQuietNight())
    assert s.one_quiet_night and current_decision(s).player == 0


@pytest.mark.parametrize("mode", ["off", "checkpoints", "full"])
def test_event_window_modes(mode):
    s = make_state(BASIC, hands=[[], ["Airlift"]], event_windows=mode,
                   player_deck=["Essen", "Paris", "Lima", "Cairo"])
    d = current_decision(s)
    if mode == "full":
        assert d.kind == "event_window" and d.context["checkpoint"] == "actions"
        assert d.player == 1
        step(s, Pass())
    assert current_decision(s).kind == "actions"
    step(s, EndActions())
    kinds = []
    while current_decision(s).kind == "event_window":
        kinds.append(current_decision(s).context["checkpoint"])
        step(s, Pass())
    if mode == "off":
        assert kinds == []
    else:
        assert kinds == ["before_draw", "before_infection", "before_infection"]
    assert s.current_player == 1


def test_windows_skipped_when_nobody_holds_events():
    s = make_state(BASIC, event_windows="full", player_deck=["Essen", "Paris", "Lima", "Cairo"])
    assert current_decision(s).kind == "actions"
    step(s, EndActions())
    assert current_decision(s).kind == "actions" and s.current_player == 1


def test_between_epidemics_window():
    s = make_state(BASIC, hands=[[], ["Airlift"]], player_deck=["Epidemic", "Epidemic", "Paris"])
    step(s, EndActions())
    seen = []
    while current_decision(s).kind == "event_window":
        seen.append(current_decision(s).context["checkpoint"])
        step(s, Pass())
    assert seen[:2] == ["before_draw", "between_epidemics"]


def test_airlift_quarantine_specialist_between_infections():
    deck = ["Tokyo", "Cairo"] + [c for c in CITY_NAMES if c not in ("Tokyo", "Cairo")]
    s = make_state((R.SCIENTIST, R.QUARANTINE_SPECIALIST), hands=[["Airlift"], []],
                   infection_deck=deck, cubes={"Tokyo": 3, "Cairo": 3},
                   player_deck=["Essen", "Paris"])
    step(s, EndActions())
    step(s, Pass())  # before_draw
    step(s, Pass())  # before first flip -> Tokyo outbreaks
    assert s.outbreaks == 1
    d = current_decision(s)
    assert d.kind == "event_window" and d.context["checkpoint"] == "before_infection"
    s_pass = s.clone()
    step(s_pass, Pass())
    assert s_pass.outbreaks == 2  # Cairo outbreaks
    step(s, PlayAirlift(1, "Cairo"))
    assert s.outbreaks == 1  # Cairo flip prevented by the Quarantine Specialist
    assert s.current_player == 1
    check_invariants(s)
