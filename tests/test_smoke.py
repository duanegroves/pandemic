"""Random legal-agent fuzzing with invariant checks after every step."""

import json
import random

import pytest

from pandemic.engine import GameConfig, GameState, is_over, legal_actions, new_game, observe, step

from helpers import check_invariants

DIFFS = ("introductory", "standard", "heroic")
MODES = ("checkpoints", "full", "off")


@pytest.mark.parametrize("chunk", range(5))
def test_random_games(chunk):
    for i in range(chunk * 100, chunk * 100 + 100):  # 500 games total
        rng = random.Random(i)
        cfg = GameConfig(num_players=2 + i % 3, difficulty=DIFFS[(i // 3) % 3],
                         event_windows=MODES[(i // 9) % 3], auto_consent=(i // 27) % 2 == 0)
        s = new_game(cfg, seed=i)
        n = 0
        while not is_over(s):
            check_invariants(s)
            if n % 25 == 0:
                d = s.to_dict()
                assert GameState.from_dict(json.loads(json.dumps(d))).to_dict() == d
                json.dumps(observe(s, n % s.num_players))
            step(s, rng.choice(legal_actions(s)))
            n += 1
            assert n < 20_000, "game did not terminate"
        check_invariants(s)
        assert s.outcome["result"] in ("win", "loss")
