"""Consent, observation, serialization and determinism."""

import json
import random

from pandemic.engine import (
    ACTION_TYPES,
    Consent,
    EndActions,
    GameConfig,
    GameState,
    GiveCard,
    TakeCard,
    action_from_dict,
    action_to_dict,
    current_decision,
    is_over,
    legal_actions,
    new_game,
    observe,
    outcome,
    redact_event,
    state_from_json,
    state_to_json,
    step,
)
from pandemic.engine import Role as R
from pandemic.engine.game_events import PlayerCardsDrawn

from helpers import make_state

BASIC = (R.CONTINGENCY_PLANNER, R.SCIENTIST)


def test_share_knowledge_consent_both_directions():
    s = make_state(BASIC, hands=[["Atlanta"], []], auto_consent=False)
    step(s, GiveCard(1, "Atlanta"))
    d = current_decision(s)
    assert d.kind == "consent" and d.player == 1 and d.context["requester"] == 0
    step(s, Consent(False))
    assert s.players[0].hand == ["Atlanta"] and s.actions_remaining == 4
    step(s, GiveCard(1, "Atlanta"))
    step(s, Consent(True))
    assert s.players[1].hand == ["Atlanta"] and s.actions_remaining == 3
    step(s, TakeCard(1, "Atlanta"))
    assert current_decision(s).player == 1
    step(s, Consent(True))
    assert s.players[0].hand == ["Atlanta"]


def _play_random(seed, cfg, n_steps=None):
    rng = random.Random(seed)
    s = new_game(cfg, seed)
    log = []
    while not is_over(s) and (n_steps is None or len(log) < n_steps):
        a = rng.choice(legal_actions(s))
        log.append(action_to_dict(a))
        step(s, a)
    return s, log


def test_json_round_trip_mid_game_and_continue():
    cfg = GameConfig(num_players=3, difficulty="heroic", event_windows="full",
                     auto_consent=False)
    s, _ = _play_random(3, cfg, n_steps=40)
    d = s.to_dict()
    text = json.dumps(d)
    s2 = GameState.from_dict(json.loads(text))
    assert s2.to_dict() == d
    assert state_from_json(state_to_json(s)).to_dict() == d
    assert s.clone().to_dict() == d
    # all three copies continue identically (RNG state included)
    rng_actions = random.Random(9)
    copies = [s, s2, s.clone()]
    while not is_over(copies[0]):
        a = rng_actions.choice(legal_actions(copies[0]))
        for c in copies:
            step(c, a)
    assert copies[0].to_dict() == copies[1].to_dict() == copies[2].to_dict()


def test_determinism_same_seed_and_actions():
    cfg = GameConfig(num_players=4, difficulty="standard")
    a, log = _play_random(11, cfg)
    b = new_game(cfg, 11)
    for ad in log:
        step(b, action_from_dict(ad))
    assert a.to_dict() == b.to_dict()
    assert outcome(a) == outcome(b) and outcome(a)["result"] in ("win", "loss")


def test_action_dict_round_trip_all_types():
    seen = set()
    for seed in range(40):
        rng = random.Random(seed)
        cfg = GameConfig(num_players=2 + seed % 3, event_windows="full", auto_consent=seed % 2)
        s = new_game(cfg, seed)
        while not is_over(s):
            acts = legal_actions(s)
            for a in acts:
                if a.type not in seen:
                    seen.add(a.type)
                    d = json.loads(json.dumps(action_to_dict(a)))
                    assert d["type"] == a.type and action_from_dict(d) == a
            step(s, rng.choice(acts))
    assert len(seen) >= 15
    assert seen <= set(ACTION_TYPES)


def test_events_are_json_and_redacted():
    s = make_state(BASIC, player_deck=["Essen", "Epidemic", "Paris"], event_windows="off")
    _, ev = step(s, EndActions())
    for e in ev:
        json.dumps(e.to_dict())
        assert "type" in e.to_dict()
    drawn = next(e for e in ev if isinstance(e, PlayerCardsDrawn))
    assert redact_event(drawn, s, 0)["cards"] == ["Essen", "Epidemic"]
    assert redact_event(drawn, s, 1)["cards"] == [None, "Epidemic"]


def test_observe_redaction():
    s = new_game(GameConfig(num_players=3, difficulty="standard"), seed=2)
    o = observe(s, 1)
    json.dumps(o)
    assert o["players"][1]["hand"] == s.players[1].hand
    assert o["players"][0]["hand"] is None and o["players"][0]["hand_size"] == 3
    assert "rng" not in o
    assert o["player_deck"]["size"] == len(s.player_deck)
    assert o["player_deck"]["epidemics_remaining"] == 5
    assert len(o["player_deck"]["piles"]) == 5
    assert o["infection_deck"] == {"size": 39, "known_top": [], "forecast": None}
    assert o["infection_discard"] == s.infection_discard
    assert set(o["player_deck"]) == {"size", "piles", "epidemics_remaining"}
    open_obs = observe(new_game(GameConfig(num_players=2, difficulty="introductory"), 2), 0)
    assert all(p["hand"] is not None for p in open_obs["players"])
