import random

import numpy as np
import pytest

pytest.importorskip("numpy")

from pandemic.ai.encoding import (  # noqa: E402
    ACTION_SPACE_SIZE,
    OBS_SIZE,
    action_mask,
    decode,
    encode,
    observation_for,
)
from pandemic.engine import (  # noqa: E402
    DiscoverCure,
    GameConfig,
    current_decision,
    is_over,
    legal_actions,
    new_game,
    observe,
    step,
)

DIFFS = ("introductory", "standard", "heroic")


def _games(n_games, **cfg_over):
    for i in range(n_games):
        cfg = GameConfig(num_players=2 + i % 3, difficulty=DIFFS[(i // 3) % 3],
                         event_windows=("checkpoints", "full", "off")[(i // 9) % 3],
                         auto_consent=(i // 27) % 2 == 0, **cfg_over)
        yield i, new_game(cfg, seed=i), random.Random(i)


def test_sizes():
    assert ACTION_SPACE_SIZE < 10_000
    assert OBS_SIZE > 0


def test_mask_bijective_and_roundtrip():
    seen_kinds = set()
    for _i, s, rng in _games(60):
        while not is_over(s):
            d = current_decision(s)
            seen_kinds.add(d.kind)
            acts = legal_actions(s) if d.kind != "forecast_order" else None
            if acts is None:
                # forecast: mask covers slots only
                m = action_mask(s)
                assert m.sum() == len(d.context["cards"])
                step(s, rng.choice(legal_actions(s)))
                continue
            mask = action_mask(s)
            idx = [encode(a, s) for a in acts]
            assert set(idx) == set(np.flatnonzero(mask))
            cures = [a for a in acts if isinstance(a, DiscoverCure)]
            non_cure = [a for a in acts if not isinstance(a, DiscoverCure)]
            assert len({encode(a, s) for a in non_cure}) == len(non_cure)  # injective
            for a in non_cure:
                assert decode(encode(a, s), s) == a
            for c in cures:
                dec = decode(encode(c, s), s)
                assert dec in acts and dec.color == c.color
                assert dec == [x for x in cures if x.color == c.color][0]
            for k in np.flatnonzero(mask):
                assert decode(int(k), s) in acts
            step(s, rng.choice(acts))
    assert {"actions", "event_window", "discard"} <= seen_kinds


def test_forecast_and_consent_seen():
    kinds = set()
    for _i, s, rng in _games(120):
        while not is_over(s):
            kinds.add(current_decision(s).kind)
            step(s, rng.choice(legal_actions(s)))
    assert {"forecast_order", "consent"} <= kinds


def test_obs_shape_stable_across_configs():
    shapes = set()
    for _i, s, rng in _games(30):
        for _ in range(30):
            if is_over(s):
                break
            p = current_decision(s).player
            o = observation_for(s, p)
            assert o.shape == (OBS_SIZE,) and o.dtype == np.float32
            assert o.min() >= 0 and o.max() <= 1
            shapes.add(o.shape)
            step(s, rng.choice(legal_actions(s)))
    assert len(shapes) == 1


def test_no_hidden_info_leak():
    cfg = GameConfig(num_players=3, difficulty="standard", open_hands=False)
    s = new_game(cfg, seed=5)
    viewer = 0
    base = observation_for(s, viewer)
    t = s.clone()
    # replace another player's hand and the deck order: observation must not change
    other = t.players[1]
    other.hand, t.player_deck[0:len(other.hand)] = (
        list(t.player_deck[:len(other.hand)]), list(other.hand))
    t.player_deck.reverse()
    t.infection_deck.reverse()
    assert not np.array_equal(
        np.asarray(sorted(s.players[1].hand)), np.asarray(sorted(other.hand)))
    assert np.array_equal(base, observation_for(t, viewer))
    assert observe(t, viewer)["players"][1]["hand"] is None
    # but with open hands the other hand is visible
    cfg2 = GameConfig(num_players=3, difficulty="introductory")
    s2 = new_game(cfg2, seed=5)
    assert observe(s2, 0)["players"][1]["hand"] is not None
    t2 = s2.clone()
    t2.players[1].hand = list(reversed(t2.players[1].hand[:-1]))
    assert not np.array_equal(observation_for(s2, 0), observation_for(t2, 0))
