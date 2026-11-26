import numpy as np
import pytest

pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

from gymnasium.utils.env_checker import check_env  # noqa: E402
from pettingzoo.test import api_test  # noqa: E402

from pandemic.ai.agents import HeuristicAgent, RandomAgent  # noqa: E402
from pandemic.ai.encoding import SEGMENTS  # noqa: E402
from pandemic.ai.env import PandemicAECEnv, PandemicTeamEnv  # noqa: E402
from pandemic.engine import GameConfig, current_decision  # noqa: E402


def test_aec_api():
    api_test(PandemicAECEnv(3, seed=1), num_cycles=300, verbose_progress=False)


def test_team_check_env():
    check_env(PandemicTeamEnv(2), skip_render_check=True)


def _play(env, agent, seed):
    env.reset(seed=seed)
    trace, done = [], False
    while not done:
        a = agent.act(env.core)
        trace.append(a)
        _, r, te, tr, _ = env.step(a)
        done = te or tr
    return trace, r, env.state.to_dict()


@pytest.mark.parametrize("agent_cls", [RandomAgent, HeuristicAgent])
def test_determinism(agent_cls):
    e1, e2 = PandemicTeamEnv(3), PandemicTeamEnv(3)
    t1, r1, s1 = _play(e1, agent_cls(7), 11)
    t2, r2, s2 = _play(e2, agent_cls(7), 11)
    assert t1 == t2 and r1 == r2 and s1 == s2


def test_reward_terminal_only_by_default():
    env = PandemicTeamEnv(2)
    env.reset(seed=3)
    agent = RandomAgent(0)
    total, done = 0.0, False
    while not done:
        _, r, te, tr, _ = env.step(agent.act(env.core))
        if not (te or tr):
            assert r == 0.0
        total += r
        done = te or tr
    assert total in (-1.0, 1.0)


def test_shaping_and_illegal_fallback():
    env = PandemicTeamEnv(2, shaping=True)
    env.reset(seed=3)
    _, _, _, _, info = env.step(0)  # index 0 (drive pawn0->first city) mostly illegal
    assert info.get("illegal_action") or env.core.mask().any()
    strict = PandemicTeamEnv(2, on_illegal="error")
    strict.reset(seed=3)
    bad = int(np.flatnonzero(strict.core.mask() == 0)[0])
    with pytest.raises(ValueError):
        strict.step(bad)


def test_forecast_substeps():
    """Play until a Forecast decision; picks accumulate and the engine steps once."""
    for seed in range(300):
        env = PandemicTeamEnv(2)
        env.reset(seed=seed)
        rng = np.random.default_rng(seed)
        done = False
        while not done:
            d = current_decision(env.state)
            if d.kind == "forecast_order":
                n = len(d.context["cards"])
                before = env.state.to_dict()
                off = SEGMENTS["forecast_slot"][0]
                for k in range(n):
                    m = env.core.mask()
                    assert m.sum() == n - k and not m[:off].any()
                    if k < n - 1:
                        assert env.state.to_dict() == before or k == 0
                    env.step(off + int(np.flatnonzero(m)[-1] - off))
                assert current_decision(env.state).kind != "forecast_order" or env.core.over
                return
            o = env.core.observation(d.player)
            _, _, te, tr, _ = env.step(int(rng.choice(np.flatnonzero(o["action_mask"]))))
            done = te or tr
    pytest.fail("no forecast decision encountered")


def test_config_passthrough_and_defaults():
    env = PandemicTeamEnv(4, config={"difficulty": "heroic"})
    env.reset(seed=1)
    c = env.state.config
    assert c.num_players == 4 and c.difficulty == "heroic"
    assert c.auto_consent and c.event_windows == "checkpoints"
    env2 = PandemicTeamEnv(config=GameConfig(num_players=2, auto_consent=False))
    env2.reset(seed=1)
    assert not env2.state.config.auto_consent


def test_consent_games_run():
    env = PandemicTeamEnv(3, config={"auto_consent": False, "event_windows": "full"})
    agent = RandomAgent(1)
    for s in range(5):
        _play(env, agent, s)


def test_masks_match_legal_in_env():
    env = PandemicAECEnv(2, seed=2)
    env.reset()
    for _ in range(50):
        if all(env.terminations.values()):
            break
        a = env.agent_selection
        obs = env.observe(a)
        d = current_decision(env.state)
        if d.kind != "forecast_order":
            assert obs["action_mask"].any()
        env.step(int(np.flatnonzero(obs["action_mask"])[0]))
