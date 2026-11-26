from collections import Counter

import pytest

from pandemic.data.cards import EPIDEMIC
from pandemic.data.cities import CITIES
from pandemic.engine import GameConfig, current_decision, new_game
from pandemic.engine.setup import first_player, pile_sizes
from pandemic.engine.state import is_city_card

from helpers import check_invariants


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("difficulty,epis", [("introductory", 4), ("standard", 5),
                                             ("heroic", 6)])
def test_setup_counts(n, difficulty, epis):
    s = new_game(GameConfig(num_players=n, difficulty=difficulty), seed=n * 10 + epis)
    check_invariants(s)
    counts = Counter()
    for v in s.cubes.values():
        if any(v):
            # only the city's own color is placed during setup
            assert sum(v) == max(v)
            counts[sum(v)] += 1
    assert counts == {3: 3, 2: 3, 1: 3}
    assert sum(s.supply) == 96 - 18
    assert len(s.infection_discard) == 9
    assert len(s.infection_deck) == 39
    assert s.stations == ["Atlanta"]
    assert s.outbreaks == 0 and s.infection_rate_index == 0
    hand = {2: 4, 3: 3, 4: 2}[n]
    assert all(len(p.hand) == hand for p in s.players)
    assert all(p.location == "Atlanta" for p in s.players)
    assert len({p.role for p in s.players}) == n
    assert len(s.player_deck) == 53 - n * hand + epis
    assert s.player_deck.count(EPIDEMIC) == epis
    # pile structure: one epidemic per pile, smaller piles at the bottom
    sizes = [size for size, _ in s.player_deck_piles]
    assert sizes == sorted(sizes, reverse=True) and max(sizes) - min(sizes) <= 1
    pos = 0
    for size in sizes:
        assert s.player_deck[pos:pos + size].count(EPIDEMIC) == 1
        pos += size
    # first player holds the highest-population city card
    best = max((CITIES[c].population, i) for i, p in enumerate(s.players)
               for c in p.hand if is_city_card(c))
    assert s.current_player == best[1]
    d = current_decision(s)
    assert d.kind == "actions" and d.player == s.current_player


def test_first_player_events_have_no_population_and_tiebreak():
    assert first_player([["Airlift", "Forecast"], ["Essen"]]) == 1
    assert first_player([["Essen"], ["Jakarta"], ["Lima"]]) == 1
    assert first_player([["Airlift"], ["One Quiet Night"]]) == 0


def test_pile_sizes():
    assert pile_sizes(45, 5) == [9, 9, 9, 9, 9]
    assert pile_sizes(43, 5) == [9, 9, 9, 8, 8]
    assert pile_sizes(41, 6) == [7, 7, 7, 7, 7, 6]


def test_fixed_roles_and_seed_determinism():
    cfg = GameConfig(num_players=2, roles=["medic", "scientist"])
    a, b = new_game(cfg, seed=5), new_game(cfg, seed=5)
    assert a.to_dict() == b.to_dict()
    assert [p.role.value for p in a.players] == ["medic", "scientist"]
    assert new_game(cfg, seed=6).to_dict() != a.to_dict()


def test_config_validation():
    with pytest.raises(ValueError):
        GameConfig(num_players=5)
    with pytest.raises(ValueError):
        GameConfig(difficulty="easy")
    with pytest.raises(ValueError):
        GameConfig(num_players=2, roles=["medic", "medic"])
    with pytest.raises(ValueError):
        GameConfig(event_windows="sometimes")
    assert GameConfig(difficulty="introductory").hands_open
    assert not GameConfig(difficulty="standard").hands_open
    assert GameConfig(difficulty="heroic", open_hands=True).hands_open
