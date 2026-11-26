from pandemic.data.cities import CITY_NAMES
from pandemic.engine import EndActions, Role, observe, step
from pandemic.engine.game_events import CubesPlaced, EpidemicDrawn, Outbreak
from pandemic.engine.infection import place_cubes

from helpers import check_invariants, make_state

BASIC = (Role.CONTINGENCY_PLANNER, Role.SCIENTIST)


def test_single_infection_and_outbreak():
    s = make_state(BASIC, cubes={"Tokyo": 3})
    ev: list = []
    place_cubes(s, "Osaka", 3, 1, "infection", ev)
    assert s.cubes["Osaka"][3] == 1
    place_cubes(s, "Tokyo", 3, 1, "infection", ev)
    assert s.cubes["Tokyo"][3] == 3 and s.outbreaks == 1
    for nb in ("Osaka", "Seoul", "Shanghai", "San Francisco"):
        assert s.cubes[nb][3] >= 1
    assert s.cubes["Osaka"][3] == 2
    check_invariants(s)


def test_outbreak_chain_skips_already_outbroken():
    s = make_state(BASIC, cubes={"Atlanta": 3, "Chicago": 3, "Washington": 3})
    ev: list = []
    place_cubes(s, "Atlanta", 0, 1, "infection", ev)
    outbreaks = [e.city for e in ev if isinstance(e, Outbreak)]
    assert outbreaks == ["Atlanta", "Chicago", "Washington"]
    assert s.outbreaks == 3
    assert s.cubes["Atlanta"][0] == 3  # not re-infected by Chicago/Washington
    assert s.cubes["Chicago"][0] == 3 and s.cubes["Washington"][0] == 3
    assert s.cubes["Miami"][0] == 2  # from Atlanta and Washington (blue cubes on a yellow city)
    assert s.cubes["Montréal"][0] == 2  # from Chicago and Washington
    assert s.cubes["New York"][0] == 1 and s.cubes["San Francisco"][0] == 1
    check_invariants(s)


def test_eradicated_disease_never_placed():
    s = make_state(BASIC, cures={"blue": "eradicated"})
    place_cubes(s, "Atlanta", 0, 3, "epidemic", [])
    assert s.cubes["Atlanta"][0] == 0


def _epidemic_state(bottom, **kw):
    deck = [c for c in CITY_NAMES if c not in bottom and c not in kw.get("infection_discard", [])]
    return make_state(BASIC, infection_deck=deck + list(bottom), event_windows="off", **kw)


def test_epidemic_bring_to_three_and_outbreak():
    s = _epidemic_state(["Lima"], cubes={"Lima": 1}, player_deck=["Epidemic", "Essen", "Paris"],
                        infection_discard=["Cairo"])
    _, ev = step(s, EndActions())
    assert s.infection_rate_index == 1
    epi = ev.index(next(e for e in ev if isinstance(e, EpidemicDrawn)))
    first_outbreak = next(e for e in ev if isinstance(e, Outbreak))
    assert first_outbreak.city == "Lima" and first_outbreak.total == 1
    assert ev.index(first_outbreak) > epi
    assert s.cubes["Lima"][1] == 3
    assert CubesPlaced("Lima", "yellow", 2, "epidemic") in ev
    assert s.cubes["Santiago"][1] >= 1 and s.cubes["Bogotá"][1] >= 1
    assert "Epidemic" in s.player_removed and s.players[0].hand == ["Essen"]
    # Intensify put {Cairo, Lima} on top; both then flipped by the rate-2 infection step.
    assert set(s.infection_discard) == {"Cairo", "Lima"}
    assert s.outbreaks == 2  # Lima flipped again while at 3
    check_invariants(s)


def test_epidemic_empty_city_gets_three_no_outbreak_and_known_top():
    s = _epidemic_state(["Lima"], player_deck=["Epidemic", "Essen", "Paris"],
                        infection_discard=["Cairo", "Tokyo", "Delhi"])
    s.one_quiet_night = True  # keep the intensified cards on top for inspection
    step(s, EndActions())
    assert s.cubes["Lima"][1] == 3 and s.outbreaks == 0
    assert set(s.infection_deck[:4]) == {"Cairo", "Tokyo", "Delhi", "Lima"}
    obs = observe(s, 1)
    assert [set(x) for x in obs["infection_deck"]["known_top"]] == [
        {"Cairo", "Tokyo", "Delhi", "Lima"}]
    check_invariants(s)


def test_double_epidemic():
    s = _epidemic_state(["Bogotá", "Lima"], player_deck=["Epidemic", "Epidemic", "Paris"],
                        infection_discard=["Cairo", "Tokyo"])
    _, ev = step(s, EndActions())
    assert sum(isinstance(e, EpidemicDrawn) for e in ev) == 2
    assert s.infection_rate_index == 2
    assert s.players[0].hand == []  # no replacement draws
    assert s.player_removed.count("Epidemic") == 5
    # Second epidemic infected Bogotá and intensified only that card onto the top,
    # so the first infection flip outbreaks Bogotá.
    outbreaks = [e.city for e in ev if isinstance(e, Outbreak)]
    assert outbreaks[0] == "Bogotá"
    assert s.cubes["Lima"][1] == 3 or "Lima" in outbreaks
    check_invariants(s)


def test_loss_eight_outbreaks():
    s = make_state(BASIC, cubes={"Tokyo": 3}, infection_deck=["Tokyo"], event_windows="off",
                   player_deck=["Essen", "Paris"])
    s.outbreaks = 7
    step(s, EndActions())
    assert s.outcome == {"result": "loss", "reason": "outbreaks"}
    assert s.outbreaks == 8
    check_invariants(s)


def test_loss_cube_shortage():
    blues = ["Chicago", "Essen", "London", "Madrid", "Milan", "Paris", "Montréal", "New York"]
    s = make_state(BASIC, cubes={c: 3 for c in blues}, infection_deck=["Atlanta"],
                   event_windows="off", player_deck=["Tokyo", "Lima"])
    assert s.supply[0] == 0
    step(s, EndActions())
    assert s.outcome == {"result": "loss", "reason": "cube_shortage"}
    check_invariants(s)


def test_loss_player_deck_exhausted():
    s = make_state(BASIC, player_deck=["Essen"], event_windows="off")
    step(s, EndActions())
    assert s.outcome == {"result": "loss", "reason": "player_deck_exhausted"}
    check_invariants(s)


def test_infection_rate_cards_flipped():
    s = make_state(BASIC, event_windows="off", player_deck=["Essen", "Paris", "Lima", "Cairo"])
    s.infection_rate_index = 5  # rate 4
    step(s, EndActions())
    assert len(s.infection_discard) == 4
