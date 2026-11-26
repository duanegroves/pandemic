import json

import pytest

from pandemic.engine import action_to_dict as a2d
from pandemic.engine import current_decision, is_over, legal_actions
from pandemic.server.rooms import Room, RoomError, RoomManager


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make_room(n=2, clock=None, timeout=None, **cfg):
    mgr = RoomManager(clock=clock or FakeClock())
    room = mgr.create_room({"num_players": n, **cfg}, timeout=timeout)
    tokens = [room.join(f"p{i}")[1] for i in range(n)]
    for t in tokens[1:]:
        room.set_ready(t)
    return room, tokens


def started(n=2, seed=7, **kw):
    room, tokens = make_room(n, **kw)
    room.start(tokens[0], seed=seed)
    return room, tokens


def play_to_end(room, tokens, limit=20000):
    for _ in range(limit):
        if is_over(room.state):
            return
        owner = current_decision(room.state).player
        room.submit(tokens[owner], a2d(legal_actions(room.state)[0]))
    raise AssertionError("game did not end")


def test_join_reconnect_and_full():
    mgr = RoomManager()
    room = mgr.create_room({"num_players": 2})
    s0, t0, _ = room.join("a")
    s1, t1, _ = room.join("b")
    assert (s0, s1) == (0, 1) and t0 != t1
    assert room.join("", token=t1)[0] == 1
    with pytest.raises(RoomError):
        room.join("c")
    with pytest.raises(RoomError):
        room.join("", token="nope")


def test_start_requires_host_ready_full():
    room = RoomManager().create_room({"num_players": 2})
    t0 = room.join("a")[1]
    with pytest.raises(RoomError, match="more players"):
        room.start(t0)
    t1 = room.join("b")[1]
    with pytest.raises(RoomError, match="ready"):
        room.start(t0)
    room.set_ready(t1)
    with pytest.raises(RoomError, match="host"):
        room.start(t1)
    msgs = room.start(t0, seed=1)
    assert {s for s, _ in msgs} == {0, 1} and room.phase == "playing"
    with pytest.raises(RoomError):
        room.join("late")


def test_wrong_seat_and_illegal_action():
    room, tokens = started()
    owner = current_decision(room.state).player
    other = 1 - owner
    act = a2d(legal_actions(room.state)[0])
    before = len(room.action_log)
    (seat, msg), = room.submit(tokens[other], act)
    assert seat == other and msg["type"] == "error" and msg["code"] == "not_your_turn"
    (seat, msg), = room.submit(tokens[owner], {"type": "drive_ferry", "pawn": owner,
                                              "destination": "Sydney"})
    assert seat == owner and msg["code"] == "illegal_action"
    (seat, msg), = room.submit(tokens[owner], {"type": "bogus"})
    assert msg["type"] == "error"
    (seat, msg), = room.submit(tokens[owner], {"type": "drive_ferry"})
    assert msg["type"] == "error"
    assert len(room.action_log) == before
    msgs = room.submit(tokens[owner], act)
    assert len(msgs) == 2 and all(m["type"] == "state" for _, m in msgs)
    assert len(room.action_log) == before + 1


def test_legal_actions_only_to_owner_and_redaction():
    room, tokens = started(3, difficulty="standard")
    assert not room.config.hands_open
    owner = current_decision(room.state).player
    for seat in range(3):
        m = room.state_message(seat)
        assert bool(m["legal_actions"]) == (seat == owner)
        for p in m["observation"]["players"]:
            if p["index"] != seat:
                assert p["hand"] is None
            else:
                assert p["hand"] is not None
    # drive events: no other seat sees a drawn hand
    for _ in range(200):
        if is_over(room.state):
            break
        owner = current_decision(room.state).player
        msgs = room.submit(tokens[owner], a2d(legal_actions(room.state)[0]))
        for seat, m in msgs:
            for e in m["events"]:
                if e["type"] == "player_cards_drawn" and e["player"] != seat:
                    assert all(c in (None, "Epidemic") for c in e["cards"])
            for p in m["observation"]["players"]:
                assert (p["hand"] is None) == (p["index"] != seat)


def test_timeout_auto_pass_with_fake_clock():
    clock = FakeClock()
    room, tokens = make_room(2, clock=clock, timeout=30)
    room.start(tokens[0], seed=3)
    room.state.players[1].hand.append("Airlift")
    room.state.players[0].hand.append("Airlift")
    for _ in range(50):
        d = current_decision(room.state)
        if d.kind == "event_window":
            break
        room.submit(tokens[d.player], a2d(legal_actions(room.state)[-1]))  # ends with EndActions?
        if d.kind == "actions":
            room.submit(tokens[d.player], {"type": "end_actions"})
    d = current_decision(room.state)
    assert d.kind == "event_window"
    assert room.deadline == clock() + 30
    assert room.tick() == []
    clock.t += 29.9
    assert room.tick() == []
    n = len(room.action_log)
    clock.t += 0.2
    msgs = room.tick()
    assert msgs and room.action_log[n] == {"type": "pass"}
    assert room.state_message(0)["deadline_in"] in (None, 30)


def test_timeout_does_not_fire_on_actions():
    clock = FakeClock()
    room, _ = make_room(2, clock=clock, timeout=1)
    room.start(room.seat_list[0].token, seed=3)
    assert room.deadline is None
    clock.t += 100
    assert room.tick() == []


def test_snapshot_restore_determinism(tmp_path):
    room, tokens = started(2, seed=11)
    play_to_end(room, tokens)
    mgr = RoomManager(storage_dir=tmp_path)
    mgr.rooms[room.id] = room
    mgr.save(room)
    mgr2 = RoomManager(storage_dir=tmp_path)
    assert mgr2.load_all() == 1
    r2 = mgr2.get(room.id)
    assert r2.state.to_dict() == room.state.to_dict()
    assert r2.seat_of(tokens[1]) == 1 and r2.phase == "over"
    # tampered log is detected
    snap = json.loads((tmp_path / f"{room.id}.json").read_text())
    snap["state_hash"] = "0" * 64
    with pytest.raises(RoomError, match="mismatch"):
        Room.restore(snap)


def test_restore_lobby_and_midgame():
    room, tokens = started(2, seed=5)
    for _ in range(10):
        owner = current_decision(room.state).player
        room.submit(tokens[owner], a2d(legal_actions(room.state)[0]))
    r2 = Room.restore(room.snapshot())
    assert r2.state.to_dict() == room.state.to_dict()
    lobby = RoomManager().create_room({})
    lobby.join("x")
    assert Room.restore(lobby.snapshot()).state is None


def test_chat():
    room, tokens = make_room(2)
    msgs = room.chat(tokens[1], " hi ")
    assert len(msgs) == 2 and msgs[0][1]["text"] == "hi" and msgs[0][1]["name"] == "p1"
