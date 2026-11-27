"""RL environments: PettingZoo AEC (``PandemicAECEnv``) and Gymnasium team env
(``PandemicTeamEnv``).

Both wrap :class:`PandemicCore`, which owns the engine ``GameState`` and handles:

* the discrete action space/mask from :mod:`pandemic.ai.encoding`;
* Forecast ordering decomposed into sequential "pick next card" sub-steps (the engine is only
  stepped once the whole order is chosen);
* reward shaping: +1 win / -1 loss (team reward, every agent gets it); optional small shaping
  (``shaping=True``): ``+cure_bonus`` per newly discovered cure, ``-outbreak_penalty`` per
  outbreak;
* illegal actions (``on_illegal``): ``"fallback"`` (default) substitutes the first legal index
  and sets ``info["illegal_action"]``; ``"error"`` raises ``ValueError``. ``illegal_penalty``
  is added to the reward when an illegal action is substituted.

Observations are dicts ``{"observation": float32[OBS_SIZE], "action_mask": int8[ACTION_SPACE]}``
(mask is all zeros when it is not that agent's decision or the game is over).

Defaults for RL: ``auto_consent=True``, ``event_windows="checkpoints"``.
"""

from __future__ import annotations

import functools
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from pettingzoo import AECEnv

from pandemic.ai.encoding import (
    ACTION_SPACE_SIZE,
    OBS_SIZE,
    SEGMENTS,
    action_mask,
    decode,
    encode_observation,
    forecast_order_from_picks,
)
from pandemic.engine import (
    GameConfig,
    GameState,
    current_decision,
    is_over,
    new_game,
    observe,
    step,
)


def _make_config(num_players: int, config: GameConfig | dict | None, **kw: Any) -> GameConfig:
    if isinstance(config, GameConfig):
        return config
    args: dict[str, Any] = {"num_players": num_players, "auto_consent": True,
                            "event_windows": "checkpoints"}
    args.update(config or {})
    args.update(kw)
    return GameConfig(**args)


class PandemicCore:
    """Shared game driver (not an env)."""

    def __init__(self, config: GameConfig, shaping: bool = False, cure_bonus: float = 0.1,
                 outbreak_penalty: float = 0.05, on_illegal: str = "fallback",
                 illegal_penalty: float = 0.0, max_steps: int = 5000):
        assert on_illegal in ("fallback", "error")
        self.config = config
        self.shaping = shaping
        self.cure_bonus = cure_bonus
        self.outbreak_penalty = outbreak_penalty
        self.on_illegal = on_illegal
        self.illegal_penalty = illegal_penalty
        self.max_steps = max_steps
        self.state: GameState
        self.forecast_picks: list[int] = []
        self.steps = 0
        self._mask: np.ndarray | None = None

    # -- lifecycle
    def reset(self, seed: int) -> None:
        self.state = new_game(self.config, seed=seed)
        self.forecast_picks = []
        self.steps = 0
        self._mask = None

    @property
    def over(self) -> bool:
        return is_over(self.state)

    @property
    def truncated(self) -> bool:
        return not self.over and self.steps >= self.max_steps

    @property
    def current_player(self) -> int | None:
        return current_decision(self.state).player

    @property
    def won(self) -> bool:
        return bool(self.state.outcome and self.state.outcome["result"] == "win")

    # -- observation / mask
    def mask(self) -> np.ndarray:
        if self._mask is None:
            self._mask = action_mask(self.state, self.forecast_picks)
        return self._mask

    def action_mask(self) -> np.ndarray:
        return self.mask()

    def observation(self, player: int) -> dict[str, np.ndarray]:
        picks = self.forecast_picks if player == self.current_player else ()
        obs = encode_observation(observe(self.state, player), picks)
        if self.over or player != self.current_player:
            m = np.zeros(ACTION_SPACE_SIZE, dtype=np.int8)
        else:
            m = self.mask().astype(np.int8)
        return {"observation": obs, "action_mask": m}

    # -- stepping
    def _progress(self) -> tuple[int, int]:
        s = self.state
        return sum(c != "none" for c in s.cures), s.outbreaks

    def step(self, index: int) -> tuple[float, dict]:
        """Apply an action index for the current decision owner. Returns (reward, info)."""
        info: dict[str, Any] = {}
        reward = 0.0
        mask = self.mask()
        index = int(index)
        if not (0 <= index < ACTION_SPACE_SIZE and mask[index]):
            if self.on_illegal == "error":
                raise ValueError(f"illegal action index {index}")
            index = int(np.flatnonzero(mask)[0])
            info["illegal_action"] = True
            reward -= self.illegal_penalty
        cures0, out0 = self._progress()
        self.steps += 1
        d = current_decision(self.state)
        if d.kind == "forecast_order":
            self.forecast_picks.append(index - SEGMENTS["forecast_slot"][0])
            if len(self.forecast_picks) == len(d.context["cards"]):
                action = forecast_order_from_picks(self.state, self.forecast_picks)
                self.forecast_picks = []
                step(self.state, action, validate=False)
        else:
            step(self.state, decode(index, self.state), validate=False)
        self._mask = None
        if self.shaping:
            cures1, out1 = self._progress()
            reward += self.cure_bonus * (cures1 - cures0) - self.outbreak_penalty * (out1 - out0)
        if self.over:
            reward += 1.0 if self.won else -1.0
            info["outcome"] = self.state.outcome
        return reward, info


class PandemicAECEnv(AECEnv):
    """PettingZoo AEC env; agents ``player_0..player_{n-1}`` (seat order), cooperative team
    reward."""

    metadata = {"name": "pandemic_aec_v0", "is_parallelizable": False, "render_modes": []}

    def __init__(self, num_players: int = 2, config: GameConfig | dict | None = None,
                 seed: int | None = None, **core_kwargs: Any):
        super().__init__()
        self.game_config = _make_config(num_players, config)
        self.core = PandemicCore(self.game_config, **core_kwargs)
        self._seed = seed
        self._rng = np.random.default_rng(seed)
        n = self.game_config.num_players
        self.possible_agents = [f"player_{i}" for i in range(n)]
        self.agents = list(self.possible_agents)
        self._obs_space = spaces.Dict({
            "observation": spaces.Box(0.0, 1.0, (OBS_SIZE,), dtype=np.float32),
            "action_mask": spaces.Box(0, 1, (ACTION_SPACE_SIZE,), dtype=np.int8),
        })
        self._act_space = spaces.Discrete(ACTION_SPACE_SIZE)

    @property
    def state(self) -> GameState:
        return self.core.state

    @functools.cache  # noqa: B019
    def observation_space(self, agent: str) -> spaces.Space:
        return self._obs_space

    @functools.cache  # noqa: B019
    def action_space(self, agent: str) -> spaces.Space:
        return self._act_space

    def _seat(self, agent: str) -> int:
        return int(agent.split("_")[1])

    def _select(self) -> None:
        p = self.core.current_player
        if p is not None:
            self.agent_selection = f"player_{p}"

    def reset(self, seed: int | None = None, options: dict | None = None) -> None:
        if seed is not None:
            self._seed = seed
            self._rng = np.random.default_rng(seed)
        game_seed = int(self._rng.integers(2**31 - 1))
        self.core.reset(game_seed)
        self.agents = list(self.possible_agents)
        self.rewards = dict.fromkeys(self.agents, 0.0)
        self._cumulative_rewards = dict.fromkeys(self.agents, 0.0)
        self.terminations = dict.fromkeys(self.agents, False)
        self.truncations = dict.fromkeys(self.agents, False)
        self.infos: dict[str, dict] = {a: {} for a in self.agents}
        self._select()

    def observe(self, agent: str) -> dict[str, np.ndarray]:
        return self.core.observation(self._seat(agent))

    def step(self, action: int | None) -> None:
        if self.terminations[self.agent_selection] or self.truncations[self.agent_selection]:
            self._was_dead_step(action)
            return
        agent = self.agent_selection
        self._cumulative_rewards[agent] = 0
        self._clear_rewards()
        reward, info = self.core.step(int(action))  # type: ignore[arg-type]
        self.infos[agent] = info
        for a in self.agents:
            self.rewards[a] = reward
        if self.core.over:
            self.terminations = dict.fromkeys(self.agents, True)
        elif self.core.truncated:
            self.truncations = dict.fromkeys(self.agents, True)
        else:
            self._select()
        self._accumulate_rewards()

    def render(self) -> None:  # pragma: no cover
        return None

    def close(self) -> None:
        pass


class PandemicTeamEnv(gym.Env):
    """Single-agent "team brain" env: one policy acts for every seat. The observation is from
    the perspective of the player who owns the pending decision (``info["player"]``)."""

    metadata = {"render_modes": []}

    def __init__(self, num_players: int = 2, config: GameConfig | dict | None = None,
                 **core_kwargs: Any):
        super().__init__()
        self.game_config = _make_config(num_players, config)
        self.core = PandemicCore(self.game_config, **core_kwargs)
        self.observation_space = spaces.Dict({
            "observation": spaces.Box(0.0, 1.0, (OBS_SIZE,), dtype=np.float32),
            "action_mask": spaces.Box(0, 1, (ACTION_SPACE_SIZE,), dtype=np.int8),
        })
        self.action_space = spaces.Discrete(ACTION_SPACE_SIZE)

    @property
    def state(self) -> GameState:
        return self.core.state

    def _obs(self) -> dict[str, np.ndarray]:
        p = self.core.current_player
        if p is None:  # game over: observe from seat 0 with an empty mask
            p = 0
        return self.core.observation(p)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.core.reset(int(self.np_random.integers(2**31 - 1)))
        return self._obs(), {"player": self.core.current_player}

    def step(self, action: int):
        reward, info = self.core.step(int(action))
        info["player"] = self.core.current_player
        terminated = self.core.over
        truncated = self.core.truncated
        return self._obs(), float(reward), terminated, truncated, info

    def action_masks(self) -> np.ndarray:
        """Boolean mask (sb3-contrib MaskablePPO convention)."""
        return self.core.mask()


__all__ = ["PandemicAECEnv", "PandemicCore", "PandemicTeamEnv"]
