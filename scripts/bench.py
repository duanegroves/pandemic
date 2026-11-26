"""Random-agent benchmark: `uv run python scripts/bench.py [n_games] [--validate]`."""

from __future__ import annotations

import random
import sys
import time

from pandemic.engine import GameConfig, is_over, legal_actions, new_game, step


def play(seed: int, num_players: int, difficulty: str, validate: bool) -> int:
    rng = random.Random(seed)
    s = new_game(GameConfig(num_players=num_players, difficulty=difficulty), seed=seed)
    steps = 0
    while not is_over(s):
        step(s, rng.choice(legal_actions(s)), validate=validate)
        steps += 1
    return steps


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 300
    validate = "--validate" in sys.argv
    t = time.perf_counter()
    total_steps = 0
    for i in range(n):
        total_steps += play(i, 2 + i % 3, ("introductory", "standard", "heroic")[i % 3],
                            validate)
    dt = time.perf_counter() - t
    print(f"{n} games in {dt:.2f}s: {n / dt:.1f} games/s, {total_steps / dt:.0f} steps/s "
          f"(validate={validate})")


if __name__ == "__main__":
    main()
