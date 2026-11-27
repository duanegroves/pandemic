"""Shared limits and room eviction: create-request validation, chat cap, message size, caps."""

import pytest
from fastapi.testclient import TestClient

from pandemic.server.app import create_app
from pandemic.server.rooms import (
    MAX_CHAT_LOG,
    MAX_MESSAGE_BYTES,
    RoomManager,
    ServerFullError,
    message_too_large,
    parse_create_request,
)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ------------------------------------------------------------ create-request parsing
def test_parse_defaults():
    p = parse_create_request(None)
    assert p.config.num_players == 2 and p.timeout is None and p.timeout_consent is False
    assert parse_create_request({}).config.num_players == 2


def test_parse_ok():
    p = parse_create_request(
        {"config": {"num_players": 3}, "timeout": 30, "timeout_consent": 1}
    )
    assert p.config.num_players == 3 and p.timeout == 30 and p.timeout_consent is True
    assert parse_create_request({"timeout": 5}).timeout == 5
    assert parse_create_request({"timeout": 600.0}).timeout == 600.0
    assert parse_create_request({"timeout": None}).timeout is None


@pytest.mark.parametrize(
    "body",
    [
        [],
        "x",
        {"config": []},
        {"config": {"num_players": 9}},
        {"config": {"nope": 1}},
        {"timeout": 4.99},
        {"timeout": 601},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": "10"},
        {"timeout": True},
    ],
)
def test_parse_rejects(body):
    with pytest.raises(ValueError):
        parse_create_request(body)


def test_http_create_validation():
    with TestClient(create_app(RoomManager())) as client:
        assert client.post("/rooms", json={"timeout": 1}).status_code == 422
        assert client.post("/rooms", json={"timeout": 700}).status_code == 422
        assert client.post("/rooms", json={"config": {"x": 1}}).status_code == 422
        assert client.post("/rooms", json={"timeout": 10}).status_code == 200
        assert client.post("/rooms").status_code == 200


# ------------------------------------------------------------ chat and message size
def test_chat_log_capped():
    mgr = RoomManager()
    room = mgr.create_room({})
    token = room.join("a")[1]
    for i in range(MAX_CHAT_LOG + 25):
        room.chat(token, f"m{i}")
    assert len(room.chat_log) == MAX_CHAT_LOG
    assert room.chat_log[-1]["text"] == f"m{MAX_CHAT_LOG + 24}"
    assert room.chat_log[0]["text"] == "m25"


def test_message_too_large():
    assert not message_too_large("x" * MAX_MESSAGE_BYTES)
    assert message_too_large("x" * (MAX_MESSAGE_BYTES + 1))
    assert message_too_large("é" * MAX_MESSAGE_BYTES)  # 2 bytes each


def test_ws_oversized_message_ignored():
    with TestClient(create_app(RoomManager())) as client:
        rid = client.post("/rooms").json()["room_id"]
        token = client.post(f"/rooms/{rid}/join", json={"name": "a"}).json()["token"]
        with client.websocket_connect(f"/ws/{rid}?token={token}") as ws:
            ws.receive_json()  # lobby
            ws.send_text("x" * (MAX_MESSAGE_BYTES + 1))
            err = ws.receive_json()
            assert err["type"] == "error" and "too large" in err["message"]
            ws.send_json({"type": "chat", "text": "hello"})
            assert ws.receive_json()["text"] == "hello"


# ------------------------------------------------------------ cap and eviction
def test_room_cap_and_eviction():
    clock = FakeClock()
    mgr = RoomManager(clock=clock, max_rooms=2, idle_ttl=3600, finished_ttl=60)
    a = mgr.create_room({})
    mgr.create_room({})
    with pytest.raises(ServerFullError):
        mgr.create_room({})
    clock.t += 3601
    mgr.touch(mgr.get(a.id).id)  # a is active again, b is idle
    c = mgr.create_room({})  # evicts b
    assert set(mgr.rooms) == {a.id, c.id}


def test_eviction_skips_connected_and_removes_files(tmp_path):
    clock = FakeClock()
    mgr = RoomManager(clock=clock, storage_dir=tmp_path, idle_ttl=100, finished_ttl=10)
    idle = mgr.create_room({})
    busy = mgr.create_room({})
    mgr.save(idle)
    mgr.save(busy)
    busy.join("x")
    busy.set_connected(0, True)
    evicted = []
    mgr.on_evict = evicted.append
    clock.t += 101
    assert mgr.evict_idle() == [idle.id]
    assert evicted == [idle.id]
    assert set(mgr.rooms) == {busy.id}
    assert not (tmp_path / f"{idle.id}.json").exists()
    assert (tmp_path / f"{busy.id}.json").exists()


def test_finished_rooms_evicted_sooner():
    from test_rooms import play_to_end, started

    room, tokens = started(2, seed=3)
    clock = room.clock
    mgr = RoomManager(clock=clock, idle_ttl=1000, finished_ttl=10)
    mgr.rooms[room.id] = room
    mgr.touch(room.id)
    for s in room.seat_list:
        s.connected = False
    clock.t += 50
    assert mgr.evict_idle() == []  # still playing
    play_to_end(room, tokens)
    mgr.touch(room.id)
    clock.t += 11
    assert mgr.evict_idle() == [room.id]


def test_load_all_uses_file_mtime(tmp_path):
    import os

    clock = FakeClock()
    mgr = RoomManager(clock=clock, storage_dir=tmp_path, idle_ttl=3600)
    room = mgr.create_room({})
    mgr.save(room)
    old = tmp_path / f"{room.id}.json"
    import time

    os.utime(old, (time.time() - 7200, time.time() - 7200))
    mgr2 = RoomManager(clock=clock, storage_dir=tmp_path, idle_ttl=3600)
    assert mgr2.load_all() == 1
    assert mgr2.evict_idle() == [room.id]


def test_http_503_when_full():
    mgr = RoomManager(max_rooms=1)
    with TestClient(create_app(mgr)) as client:
        assert client.post("/rooms").status_code == 200
        r = client.post("/rooms")
        assert r.status_code == 503 and "full" in r.json()["detail"]
