from fastapi.testclient import TestClient

from pandemic.server.app import create_app
from pandemic.server.rooms import RoomManager


def recv_state(ws):
    while True:
        m = ws.receive_json()
        if m["type"] == "state":
            return m


def test_two_clients_play_to_completion():
    # Use TestClient as a context manager so both websockets share one event-loop
    # portal (as under uvicorn); otherwise cross-loop sends can stall the reader.
    with TestClient(create_app(RoomManager())) as client:
        _play_to_completion(client)


def _play_to_completion(client):
    rid = client.post("/rooms", json={"config": {"num_players": 2,
                                                  "difficulty": "introductory"}}).json()["room_id"]
    assert client.get("/rooms/404x").status_code == 404
    j = [client.post(f"/rooms/{rid}/join", json={"name": n}).json() for n in ("a", "b")]
    assert client.post(f"/rooms/{rid}/join", json={"name": "c"}).status_code == 409
    assert client.get(f"/rooms/{rid}").json()["seats"][1]["name"] == "b"
    with client.websocket_connect(f"/ws/{rid}?token={j[0]['token']}") as w0, \
            client.websocket_connect(f"/ws/{rid}?token={j[1]['token']}") as w1:
        wss = [w0, w1]
        assert w0.receive_json()["type"] == "lobby"
        w1.send_json({"type": "chat", "text": "hello"})
        w1.send_json({"type": "start"})  # not host -> error to w1 only
        w1.send_json({"type": "ready"})
        w0.send_json({"type": "start"})
        # drain until each has a state message
        states = [None, None]
        seen_err = False
        for i, w in enumerate(wss):
            while states[i] is None:
                m = w.receive_json()
                seen_err |= m["type"] == "error"
                if m["type"] == "state":
                    states[i] = m
        assert seen_err
        for _ in range(20000):
            owner_msg = next((m for m in states if m["legal_actions"]), None)
            if owner_msg is None:
                break
            owner = owner_msg["you"]
            wss[owner].send_json({"type": "action", "action": owner_msg["legal_actions"][0]})
            states = [recv_state(w) for w in wss]
        assert all(m["phase"] == "over" for m in states)
        assert states[0]["outcome"]["result"] in ("win", "loss")
        wss[0].send_json({"type": "action", "action": {"type": "end_actions"}})
        assert wss[0].receive_json()["type"] == "error"


def test_bad_token_rejected():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with TestClient(create_app(RoomManager())) as client:
        rid = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{rid}?token=x") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4401
        with client.websocket_connect("/ws/nope?token=x") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4401


def test_meta_and_index():
    with TestClient(create_app(RoomManager())) as client:
        m = client.get("/meta").json()
        assert len(m["cities"]) == 48
        atl = next(c for c in m["cities"] if c["name"] == "Atlanta")
        assert atl["color"] == "blue" and "Chicago" in atl["neighbors"]
        assert "medic" in m["roles"] and "Forecast" in m["events"]
        assert client.get("/debug").status_code in (404, 405)
