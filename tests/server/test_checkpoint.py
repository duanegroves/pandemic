"""State checkpoints in room snapshots: restore replays only the tail."""

import copy
import json
import random

import pytest
from test_rooms import started

from pandemic.engine import action_to_dict as a2d
from pandemic.engine import current_decision, is_over, legal_actions
from pandemic.server import rooms as rooms_mod
from pandemic.server.rooms import Room, RoomError, RoomManager, state_hash


def play(room, tokens, n, rng=None):
    rng = rng or random.Random(0)
    for _ in range(n):
        if is_over(room.state):
            return
        owner = current_decision(room.state).player
        room.submit(tokens[owner], a2d(rng.choice(legal_actions(room.state))))


def test_no_checkpoint_by_default_and_legacy_snapshot_restores():
    room, tokens = started(2, seed=3)
    play(room, tokens, 15)
    snap = room.snapshot()
    assert "checkpoint" not in snap
    r2 = Room.restore(json.loads(json.dumps(snap)))
    assert r2.state.to_dict() == room.state.to_dict()
    assert r2.action_log == room.action_log


def test_checkpoint_created_after_n_actions_and_carried_forward():
    room, tokens = started(2, seed=3)
    play(room, tokens, 10)
    assert "checkpoint" not in room.snapshot(checkpoint_every=12)
    play(room, tokens, 6)
    n = len(room.action_log)
    snap = room.snapshot(checkpoint_every=12)
    assert snap["checkpoint"]["at"] == n
    play(room, tokens, 3)
    # below the threshold: the old checkpoint is carried forward, even without the argument
    assert room.snapshot(checkpoint_every=12)["checkpoint"]["at"] == n
    assert room.snapshot()["checkpoint"]["at"] == n


def test_restore_from_checkpoint_replays_only_tail(monkeypatch):
    room, tokens = started(2, seed=9)
    play(room, tokens, 20)
    snap = json.loads(json.dumps(room.snapshot(checkpoint_every=10)))
    cp_at = snap["checkpoint"]["at"]
    assert cp_at > 0
    play(room, tokens, 4)
    snap = json.loads(json.dumps(room.snapshot()))
    calls = []
    real_step = rooms_mod.step
    monkeypatch.setattr(rooms_mod, "step", lambda *a, **k: calls.append(1) or real_step(*a, **k))
    r2 = Room.restore(snap)
    assert len(calls) == len(snap["actions"]) - cp_at < len(snap["actions"])
    assert r2.state.to_dict() == room.state.to_dict()
    assert r2.action_log == room.action_log
    # The restored room keeps playing identically to the original (rng state is in the checkpoint).
    monkeypatch.undo()
    play(room, tokens, 15, random.Random(5))
    play(r2, tokens, 15, random.Random(5))
    assert state_hash(r2.state) == state_hash(room.state)


def test_checkpoint_is_not_aliased_to_live_state():
    room, tokens = started(2, seed=4)
    play(room, tokens, 12)
    snap = room.snapshot(checkpoint_every=5)
    frozen = copy.deepcopy(snap["checkpoint"])
    play(room, tokens, 10)
    assert room.checkpoint == frozen
    # ...and restoring then playing does not corrupt the checkpoint it came from
    r2 = Room.restore(json.loads(json.dumps(snap)))
    keep = copy.deepcopy(r2.checkpoint)
    play(r2, tokens, 10)
    assert r2.checkpoint == keep


def test_bad_checkpoint_falls_back_to_full_replay():
    room, tokens = started(2, seed=6)
    play(room, tokens, 14)
    snap = json.loads(json.dumps(room.snapshot(checkpoint_every=5)))
    snap["checkpoint"]["state"]["turn"] += 5  # corrupt it
    r2 = Room.restore(snap)
    assert r2.state.to_dict() == room.state.to_dict()
    assert r2.checkpoint is None
    snap["checkpoint"]["state"] = {"junk": 1}
    assert Room.restore(snap).state.to_dict() == room.state.to_dict()


def test_tampered_hash_still_detected_with_checkpoint():
    room, tokens = started(2, seed=6)
    play(room, tokens, 14)
    snap = json.loads(json.dumps(room.snapshot(checkpoint_every=5)))
    snap["state_hash"] = "0" * 64
    with pytest.raises(RoomError, match="mismatch"):
        Room.restore(snap)


def test_manager_saves_checkpoints_and_reloads(tmp_path):
    mgr = RoomManager(storage_dir=tmp_path, checkpoint_every=5)
    room = mgr.create_room({"num_players": 2})
    tokens = [room.join("a")[1], room.join("b")[1]]
    room.set_ready(tokens[1])
    room.start(tokens[0], seed=2)
    play(room, tokens, 12)
    mgr.save(room)
    data = json.loads((tmp_path / f"{room.id}.json").read_text())
    assert data["checkpoint"]["at"] >= 5
    mgr2 = RoomManager(storage_dir=tmp_path)
    assert mgr2.load_all() == 1
    assert mgr2.get(room.id).state.to_dict() == room.state.to_dict()
