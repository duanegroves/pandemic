"""Protocol conformance scenarios (docs/SERVER_PROTOCOL.md) against any running backend.

    uv run --all-extras python tests/conformance/conformance.py --base http://127.0.0.1:8000

Phases: `all` (default, everything except restart), `restart-setup` (create a mid-game room and
write --state-file) and `restart-verify` (after the server was restarted: reconnect with the
saved tokens, compare, play on). `run.py` drives all three against a local backend.
Test clients send a browser-like User-Agent because workers.dev filters default Python ones.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
import traceback
import urllib.error
import urllib.request

import websockets

UA = "Mozilla/5.0 (pandemic-conformance)"
BASE = "http://127.0.0.1:8000"


def http(method: str, path: str, body=None) -> tuple[int, dict | None]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"User-Agent": UA}
    if data is not None:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, None


def ws_url(room: str, token: str) -> str:
    return BASE.replace("http", "ws", 1) + f"/ws/{room}?token={token}"


class Client:
    """One seat's WebSocket plus a log of every message it received."""

    def __init__(self, room: str, seat: int, token: str, name: str = ""):
        self.room, self.seat, self.token, self.name = room, seat, token, name
        self.ws = None
        self.latest: dict[str, dict] = {}  # last message by type
        self.log: list[dict] = []

    async def connect(self):
        self.ws = await websockets.connect(
            ws_url(self.room, self.token), user_agent_header=UA, open_timeout=20
        )
        return self

    async def send(self, **msg):
        await self.ws.send(json.dumps(msg))

    async def recv(self, timeout: float = 10) -> dict:
        m = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
        self.log.append(m)
        self.latest[m["type"]] = m
        return m

    async def recv_until(self, pred, timeout: float = 10) -> dict:
        end = time.monotonic() + timeout
        while True:
            m = await self.recv(max(0.05, end - time.monotonic()))
            if pred(m):
                return m

    async def drain(self, quiet: float = 0.4) -> list[dict]:
        out = []
        while True:
            try:
                out.append(await self.recv(quiet))
            except TimeoutError:
                return out

    async def close(self):
        if self.ws is not None:
            await self.ws.close()


def check(cond, msg: str = "assertion failed"):
    if not cond:
        raise AssertionError(msg)


async def new_room(n: int = 2, **extra) -> tuple[str, list[Client]]:
    """Create a room, join n players, connect them. Returns (room_id, clients)."""
    status, body = http("POST", "/rooms", {"config": {"num_players": n}, **extra})
    check(status == 200 and body and "room_id" in body, f"create failed: {status} {body}")
    rid = body["room_id"]
    clients = []
    for i in range(n):
        status, j = http("POST", f"/rooms/{rid}/join", {"name": f"p{i}", "token": None})
        check(status == 200 and j["seat"] == i, f"join failed: {status} {j}")
        clients.append(await Client(rid, i, j["token"], f"p{i}").connect())
    return rid, clients


async def start_game(clients: list[Client]):
    for c in clients[1:]:
        await c.send(type="ready", ready=True)
    await asyncio.sleep(0.3)
    await clients[0].send(type="start")
    for c in clients:
        await c.recv_until(lambda m: m["type"] == "state")


async def drain_all(clients):
    await asyncio.sleep(0.05)
    for c in clients:
        await c.drain(0.12)


def owner_of(clients: list[Client]) -> Client | None:
    # The owner is the client whose latest state message has legal actions.
    for c in clients:
        s = c.latest.get("state")
        if s and s["legal_actions"]:
            return c
    return None


async def play_action(clients: list[Client], rng: random.Random, pick=None) -> bool:
    """Owner submits one legal action and waits for every client to see the next state.

    Returns False when nobody owns a decision (game over)."""
    await drain_all(clients)
    c = owner_of(clients)
    if c is None:
        return False
    legal = c.latest["state"]["legal_actions"]
    action = pick(legal) if pick else rng.choice(legal)
    before = {x.seat: id(x.latest["state"]) for x in clients}
    await c.send(type="action", action=action)
    for x in clients:
        await x.recv_until(lambda m: m["type"] == "state")
        check(id(x.latest["state"]) != before[x.seat], "no new state after action")
    return True


def state_messages(clients):
    return [m for c in clients for m in c.log if m["type"] == "state"]


def check_redaction(clients: list[Client], hands_open: bool = False):
    """No seat ever sees another seat's hand (closed hands) in observations or events."""
    for c in clients:
        for m in c.log:
            if m["type"] != "state":
                continue
            check(m["you"] == c.seat, "state addressed to wrong seat")
            for p in m["observation"]["players"]:
                if p["index"] == c.seat:
                    check(isinstance(p["hand"], list), "own hand hidden")
                elif not hands_open:
                    check(p["hand"] is None, f"seat {c.seat} sees hand of seat {p['index']}")
            if m["legal_actions"]:
                check(m["decision"]["player"] == c.seat, "legal actions sent to non-owner")


# ----------------------------------------------------------------- scenarios
async def s_rest_basics():
    status, meta = http("GET", "/meta")
    check(status == 200 and len(meta["cities"]) == 48 and meta["roles"] and meta["events"])
    status, _ = http("GET", "/rooms/ffffff")
    check(status == 404, f"unknown room GET should 404, got {status}")
    status, _ = http("POST", "/rooms/ffffff/join", {"name": "x"})
    check(status == 404, f"unknown room join should 404, got {status}")
    status, _ = http("POST", "/rooms", {"config": {"num_players": 9}})
    check(status == 422, f"bad config should 422, got {status}")
    for bad in (1, 4.9, 601, 0, -3, "10", True):
        status, _ = http("POST", "/rooms", {"timeout": bad})
        check(status == 422, f"timeout {bad!r} should 422, got {status}")
    status, _ = http("POST", "/rooms", {"timeout": 5})
    check(status == 200, f"timeout 5 should be accepted, got {status}")
    status, _ = http("POST", "/rooms", {"config": [1, 2]})
    check(status == 422, f"non-object config should 422, got {status}")
    status, _ = http("POST", "/rooms", {"config": {"bogus_field": 1}})
    check(status == 422, f"unknown config field should 422, got {status}")
    status, body = http("POST", "/rooms", {"config": {"num_players": 2}})
    check(status == 200 and isinstance(body["room_id"], str) and body["room_id"])
    status, lobby = http("GET", f"/rooms/{body['room_id']}")
    check(status == 200 and lobby["type"] == "lobby" and lobby["phase"] == "lobby")
    check(lobby["capacity"] == 2 and lobby["seats"] == [] and lobby["room_id"] == body["room_id"])
    check(lobby["config"]["num_players"] == 2 and lobby["timeout"] is None)
    status, body = http("POST", "/rooms", None)  # empty body: defaults (2 players)
    check(status == 200, f"POST /rooms without a body: {status}")


async def s_join_reconnect():
    status, body = http("POST", "/rooms", {"config": {"num_players": 2}})
    rid = body["room_id"]
    s, a = http("POST", f"/rooms/{rid}/join", {"name": "Ann"})
    check(s == 200 and a["seat"] == 0 and a["room_id"] == rid and a["token"])
    s, b = http("POST", f"/rooms/{rid}/join", {"name": "Bob", "token": None})
    check(s == 200 and b["seat"] == 1 and b["token"] != a["token"])
    s, _ = http("POST", f"/rooms/{rid}/join", {"name": "Cy"})
    check(s == 409, f"full room should 409, got {s}")
    s, again = http("POST", f"/rooms/{rid}/join", {"name": "", "token": b["token"]})
    check(s == 200 and again["seat"] == 1 and again["token"] == b["token"], "reconnect by token")
    s, _ = http("POST", f"/rooms/{rid}/join", {"name": "x", "token": "not-a-token"})
    check(s == 409, f"bad token join should 409, got {s}")
    s, lobby = http("GET", f"/rooms/{rid}")
    check([x["name"] for x in lobby["seats"]] == ["Ann", "Bob"])
    seats = lobby["seats"]
    check(seats[0]["host"] and seats[0]["ready"] and not seats[1]["ready"])


async def s_ws_bad_token():
    status, body = http("POST", "/rooms", {"config": {"num_players": 2}})
    rid = body["room_id"]
    http("POST", f"/rooms/{rid}/join", {"name": "a"})
    for room, tok in ((rid, "wrong"), ("ffffff", "x")):
        ws = await websockets.connect(ws_url(room, tok), user_agent_header=UA, open_timeout=20)
        try:
            await asyncio.wait_for(ws.recv(), 10)
            raise AssertionError("expected close, got a message")
        except websockets.ConnectionClosed as e:
            code = e.rcvd.code if e.rcvd else None
            check(code == 4401, f"expected close code 4401, got {code}")


async def s_lobby_flow():
    rid, (a, b) = await new_room(2)
    try:
        for c in (a, b):
            m = await c.recv_until(lambda m: m["type"] == "lobby" and len(m["seats"]) == 2)
            check(m["you"] == c.seat and m["phase"] == "lobby" and m["capacity"] == 2)
        await drain_all([a, b])
        check(all(s["connected"] for s in a.latest["lobby"]["seats"]), "connected flags")
        # not ready yet: host cannot start; non-host cannot start
        await a.send(type="start")
        m = await a.recv_until(lambda m: m["type"] == "error")
        check(m["code"] == "bad_request" and "ready" in m["message"], m)
        await b.send(type="start")
        m = await b.recv_until(lambda m: m["type"] == "error")
        check("host" in m["message"], m)
        await drain_all([a, b])
        await b.send(type="ready", ready=True)
        m = await a.recv_until(lambda m: m["type"] == "lobby" and m["seats"][1]["ready"])
        await b.send(type="sync")
        m = await b.recv_until(lambda m: m["type"] == "lobby")
        check(m["you"] == 1)
        await b.send(type="chat", text="  hello  ")
        for c in (a, b):
            m = await c.recv_until(lambda m: m["type"] == "chat")
            check(m == {"type": "chat", "seat": 1, "name": "p1", "text": "hello"}, m)
        await drain_all([a, b])
        # disconnect/reconnect updates connected flags
        await b.close()
        m = await a.recv_until(lambda m: m["type"] == "lobby" and not m["seats"][1]["connected"])
        b = await Client(rid, 1, b.token).connect()
        m = await a.recv_until(lambda m: m["type"] == "lobby" and m["seats"][1]["connected"])
        await b.recv_until(lambda m: m["type"] == "lobby")
        await drain_all([a, b])
        await a.send(type="start")
        for c in (a, b):
            m = await c.recv_until(lambda m: m["type"] == "state")
            check(m["phase"] == "playing" and m["you"] == c.seat)
            check(m["decision"]["kind"] and m["deadline_in"] is None and m["outcome"] is None)
        s, lobby = http("GET", f"/rooms/{rid}")
        check(lobby["phase"] == "playing")
        s, _ = http("POST", f"/rooms/{rid}/join", {"name": "late"})
        check(s == 409, f"join after start should 409, got {s}")
        await a.send(type="ready", ready=True)
        m = await a.recv_until(lambda m: m["type"] == "error")
        check("started" in m["message"], m)
        # a state message on reconnect
        await b.close()
        b = await Client(rid, 1, b.token).connect()
        m = await b.recv_until(lambda m: m["type"] == "state")
        check(m["you"] == 1)
    finally:
        await a.close()
        await b.close()


async def s_message_limits():
    """Oversized messages get an error and are ignored; the chat log is capped (not visible)."""
    rid, clients = await new_room(2)
    try:
        c = clients[0]
        await c.drain(0.5)
        await c.send(type="chat", text="x" * 20000)
        m = await c.recv_until(lambda m: m["type"] == "error")
        check(m["code"] == "bad_request" and "large" in m["message"], m)
        await c.send(type="chat", text="still works")  # connection survives
        m = await c.recv_until(lambda m: m["type"] == "chat")
        check(m["text"] == "still works", m)
    finally:
        for c in clients:
            await c.close()


async def s_errors_to_sender_only():
    rid, clients = await new_room(2)
    try:
        await start_game(clients)
        await drain_all(clients)
        owner = owner_of(clients)
        other = clients[1 - owner.seat]
        legal = owner.latest["state"]["legal_actions"]
        # not your turn
        await other.send(type="action", action=legal[0])
        m = await other.recv_until(lambda m: m["type"] == "error")
        check(m["code"] == "not_your_turn", m)
        # illegal action (well-formed, but not legal)
        await owner.send(type="action", action={"type": "Pass"} if {"type": "Pass"} not in legal
                         else {"type": "Drive", "to": "Nowhere"})
        m = await owner.recv_until(lambda m: m["type"] == "error")
        check(m["code"] in ("illegal_action", "bad_action"), m)
        # malformed
        await owner.send(type="action", action={"nonsense": True})
        m = await owner.recv_until(lambda m: m["type"] == "error")
        check(m["code"] in ("bad_action", "illegal_action"), m)
        await owner.send(type="action")
        m = await owner.recv_until(lambda m: m["type"] == "error")
        check(m["code"] == "bad_request", m)
        await owner.send(type="bogus")
        m = await owner.recv_until(lambda m: m["type"] == "error")
        check(m["code"] == "bad_request", m)
        await owner.ws.send("this is not json")
        m = await owner.recv_until(lambda m: m["type"] == "error", timeout=5)
        check(m["code"] == "bad_request", m)
        # nobody else heard any of it, and the game state is unchanged
        extra = await other.drain(0.5)
        check([m for m in extra if m["type"] in ("error", "state")] == [], f"leaked: {extra}")
        await owner.send(type="sync")
        m = await owner.recv_until(lambda m: m["type"] == "state")
        check(m["legal_actions"] == legal, "state changed after errors")
    finally:
        for c in clients:
            await c.close()


async def s_full_game_and_redaction():
    rng = random.Random(7)
    rid, clients = await new_room(2)
    try:
        await start_game(clients)
        n = 0
        while n < 4000 and await play_action(clients, rng):
            n += 1
        final = clients[0].latest["state"]
        check(final["phase"] == "over" and final["outcome"], f"game did not finish ({n} actions)")
        check(final["legal_actions"] == [])
        for c in clients:
            check(c.latest["state"]["phase"] == "over")
        check_redaction(clients)
        # events contain no foreign cards: spot-check structure only
        check(any(m["events"] for m in state_messages(clients)), "no events seen")
        s, lobby = http("GET", f"/rooms/{rid}")
        check(lobby["phase"] == "over")
        print(f"      ({n} actions, outcome {final['outcome']})", end="")
    finally:
        for c in clients:
            await c.close()


async def s_timeout_auto_pass():
    """A room with a short timeout auto-passes an unanswered event_window decision."""
    rng = random.Random(3)
    for _attempt in range(12):
        rid, clients = await new_room_cfg(3, 5)
        try:
            await start_game(clients)
            for _ in range(300):
                await drain_all(clients)
                s = clients[0].latest["state"]
                if s["phase"] == "over":
                    break
                if s["decision"]["kind"] == "event_window":
                    check(s["deadline_in"] is not None and 0 < s["deadline_in"] <= 5,
                          f"deadline_in {s['deadline_in']}")
                    before = json.dumps([s["observation"], s["decision"]], sort_keys=True)
                    t0 = time.monotonic()
                    for c in clients:
                        c.latest.pop("state", None)
                    for c in clients:
                        m = await c.recv_until(lambda m: m["type"] == "state", timeout=12)
                    waited = time.monotonic() - t0
                    after = json.dumps([m["observation"], m["decision"]], sort_keys=True)
                    check(after != before, "state unchanged after timeout")
                    check(waited <= 5 + 3, f"auto-pass came too late ({waited:.2f}s)")
                    print(f"      (auto-passed after {waited:.1f}s)", end="")
                    return
                if not await play_action(clients, rng):
                    break
        finally:
            for c in clients:
                await c.close()
    raise AssertionError("never reached an event_window decision in 12 games")


async def new_room_cfg(n: int, timeout: float):
    status, body = http(
        "POST", "/rooms",
        {"config": {"num_players": n, "event_windows": "full"}, "timeout": timeout},
    )
    check(status == 200, f"create failed: {status} {body}")
    rid = body["room_id"]
    s, lobby = http("GET", f"/rooms/{rid}")
    check(lobby["timeout"] == timeout, "timeout not echoed in lobby")
    clients = []
    for i in range(n):
        s, j = http("POST", f"/rooms/{rid}/join", {"name": f"p{i}"})
        clients.append(await Client(rid, i, j["token"], f"p{i}").connect())
    return rid, clients


async def s_restart_setup(state_file: str):
    """Make a mid-game room with enough actions to cross a checkpoint, then save its identity."""
    rng = random.Random(11)
    n = 0
    for _ in range(25):
        rid, clients = await new_room(2)
        await start_game(clients)
        n = 0
        while n < 28 and await play_action(clients, rng):
            n += 1
        if n == 28 and clients[0].latest["state"]["phase"] == "playing":
            break
        for c in clients:
            await c.close()
    else:
        raise AssertionError("could not get a game that survives 28 actions")
    await drain_all(clients)
    owner = owner_of(clients)
    saved = {
        "base": BASE, "room_id": rid, "actions": n,
        "tokens": [c.token for c in clients],
        "latest": [c.latest["state"] for c in clients],
        "owner": owner.seat if owner else None,
    }
    with open(state_file, "w") as f:
        json.dump(saved, f)
    for c in clients:
        await c.close()
    print(f"      (room {rid}, {n} actions)", end="")


async def s_restart_verify(state_file: str):
    with open(state_file) as f:
        saved = json.load(f)
    rid = saved["room_id"]
    s, lobby = http("GET", f"/rooms/{rid}")
    check(s == 200 and lobby["phase"] == "playing", f"room lost after restart: {s} {lobby}")
    clients = []
    for seat, tok in enumerate(saved["tokens"]):
        c = await Client(rid, seat, tok).connect()
        m = await c.recv_until(lambda m: m["type"] == "state")
        old = saved["latest"][seat]
        for key in ("you", "phase", "decision", "legal_actions", "observation", "outcome"):
            check(m[key] == old[key], f"{key} differs after restart for seat {seat}")
        clients.append(c)
    # reconnecting by token over REST still maps to the same seats
    for seat, tok in enumerate(saved["tokens"]):
        s, j = http("POST", f"/rooms/{rid}/join", {"name": "", "token": tok})
        check(s == 200 and j["seat"] == seat)
    # the game continues, and a bad token is still refused
    rng = random.Random(1)
    for _ in range(8):
        if not await play_action(clients, rng):
            break
    check_redaction(clients)
    for c in clients:
        await c.close()
    ws = await websockets.connect(ws_url(rid, "wrong"), user_agent_header=UA, open_timeout=20)
    try:
        await asyncio.wait_for(ws.recv(), 10)
        raise AssertionError("bad token accepted after restart")
    except websockets.ConnectionClosed as e:
        check(e.rcvd and e.rcvd.code == 4401, "bad token not 4401 after restart")


SCENARIOS = [
    ("rest_basics", s_rest_basics),
    ("join_reconnect_by_token", s_join_reconnect),
    ("ws_bad_token_4401", s_ws_bad_token),
    ("lobby_flow_chat_connected", s_lobby_flow),
    ("message_limits", s_message_limits),
    ("errors_to_sender_only", s_errors_to_sender_only),
    ("full_game_and_redaction", s_full_game_and_redaction),
    ("timeout_auto_pass", s_timeout_auto_pass),
]


async def run(phase: str, state_file: str) -> int:
    if phase == "all":
        todo = SCENARIOS
    elif phase == "restart-setup":
        todo = [("restart_setup", lambda: s_restart_setup(state_file))]
    else:
        todo = [("restart_verify", lambda: s_restart_verify(state_file))]
    failed = 0
    for name, fn in todo:
        t0 = time.monotonic()
        try:
            print(f"  {name} ...", end="", flush=True)
            await fn()
            print(f" PASS ({time.monotonic() - t0:.1f}s)")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f" FAIL: {e!r}")
            traceback.print_exc(limit=4, file=sys.stdout)
    return failed


def main() -> None:
    global BASE
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--phase", choices=["all", "restart-setup", "restart-verify"], default="all")
    p.add_argument("--state-file", default=".conformance_state.json")
    a = p.parse_args()
    BASE = a.base.rstrip("/")
    print(f"conformance against {BASE} (phase {a.phase})")
    sys.exit(1 if asyncio.run(run(a.phase, a.state_file)) else 0)


if __name__ == "__main__":
    main()
