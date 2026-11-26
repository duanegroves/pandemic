"""Evaluate Random vs Heuristic agents on the team env.

    uv run --extra ai python scripts/eval_agents.py --games 200 --players 2 --difficulty standard
"""

from __future__ import annotations

import argparse
import time

from pandemic.ai.agents import HeuristicAgent, RandomAgent
from pandemic.ai.env import PandemicTeamEnv


def run(agent_cls, games: int, players: int, difficulty: str, windows: str, seed0: int):
    env = PandemicTeamEnv(players, config={"difficulty": difficulty, "event_windows": windows})
    agent = agent_cls(seed0)
    wins = outbreaks = steps = 0
    reasons: dict[str, int] = {}
    t0 = time.perf_counter()
    for g in range(games):
        env.reset(seed=seed0 + g)
        done = False
        while not done:
            _, _, te, tr, _ = env.step(agent.act(env.core))
            steps += 1
            done = te or tr
        s = env.state
        wins += env.core.won
        outbreaks += s.outbreaks
        r = (s.outcome or {}).get("reason", "truncated")
        reasons[str(r)] = reasons.get(str(r), 0) + 1
    dt = time.perf_counter() - t0
    return wins / games, outbreaks / games, steps / games, steps / dt, reasons


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--players", type=int, default=2)
    ap.add_argument("--difficulty", default="standard")
    ap.add_argument("--windows", default="checkpoints")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    print(f"{a.games} games, {a.players} players, {a.difficulty}, windows={a.windows}")
    for cls in (RandomAgent, HeuristicAgent):
        wr, ob, st, sps, why = run(cls, a.games, a.players, a.difficulty, a.windows, a.seed)
        print(f"{cls.__name__:15s} win={wr:6.1%} outbreaks={ob:5.2f} steps/game={st:6.1f} "
              f"steps/s={sps:8.0f} outcomes={why}")


if __name__ == "__main__":
    main()
