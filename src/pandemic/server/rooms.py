"""Transport-agnostic room manager for multiplayer Pandemic.

Everything here is plain Python: methods return lists of ``(seat, message_dict)`` pairs and the
transport layer (``app.py``) is responsible for delivering them. Time comes from an injectable
``clock`` so timeouts can be tested without sleeping.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pandemic.engine import (
    Consent,
    GameConfig,
    GameState,
    IllegalActionError,
    Pass,
    action_from_dict,
    action_to_dict,
    current_decision,
    is_over,
    legal_actions,
    new_game,
    observe,
    outcome,
    redact_event,
    state_to_json,
    step,
)

Outbound = tuple[int, dict]
Clock = Callable[[], float]

MAX_CHAT = 500
# Snapshots carry a state checkpoint once this many actions have passed since the last one.
CHECKPOINT_EVERY = 25


class RoomError(Exception):
    """A request the room cannot honour (bad token, room full, not host...)."""


def new_room_id() -> str:
    return secrets.token_hex(3)


def state_hash(state: GameState) -> str:
    return hashlib.sha256(state_to_json(state).encode()).hexdigest()


@dataclass
class Seat:
    name: str
    token: str
    ready: bool = False
    connected: bool = False


@dataclass
class Room:
    id: str
    config: GameConfig
    clock: Clock = time.monotonic
    # Seconds before an unanswered decision of a timed kind is auto-resolved. None disables.
    timeout: float | None = None
    # Decision kinds subject to the timeout. event_window -> Pass, consent -> decline.
    timeout_kinds: tuple[str, ...] = ("event_window",)
    seat_list: list[Seat] = field(default_factory=list)
    seed: int | None = None
    state: GameState | None = None
    action_log: list[dict] = field(default_factory=list)
    deadline: float | None = None
    chat_log: list[dict] = field(default_factory=list)
    # Latest state checkpoint {"at": number of actions applied, "state": GameState.to_dict()}.
    # Lets restore replay only the actions after it instead of the whole game.
    checkpoint: dict | None = None

    # ------------------------------------------------------------------ lobby
    @property
    def phase(self) -> str:
        if self.state is None:
            return "lobby"
        return "over" if is_over(self.state) else "playing"

    def seat_of(self, token: str) -> int:
        for i, s in enumerate(self.seat_list):
            if secrets.compare_digest(s.token, token):
                return i
        raise RoomError("unknown token")

    def join(self, name: str, token: str | None = None) -> tuple[int, str, list[Outbound]]:
        """Take a free seat, or reconnect to one with its token. Returns (seat, token, msgs)."""
        if token is not None:
            seat = self.seat_of(token)
            return seat, token, self.lobby_messages()
        if self.state is not None:
            raise RoomError("game already started; rejoin with your token")
        if len(self.seat_list) >= self.config.num_players:
            raise RoomError("room is full")
        name = (name or "").strip()[:40] or f"Player {len(self.seat_list) + 1}"
        new_token = secrets.token_urlsafe(16)
        self.seat_list.append(Seat(name=name, token=new_token))
        return len(self.seat_list) - 1, new_token, self.lobby_messages()

    def set_connected(self, seat: int, connected: bool) -> list[Outbound]:
        self.seat_list[seat].connected = connected
        return self.lobby_messages()

    def set_ready(self, token: str, ready: bool = True) -> list[Outbound]:
        seat = self.seat_of(token)
        if self.state is not None:
            raise RoomError("game already started")
        self.seat_list[seat].ready = ready
        return self.lobby_messages()

    def lobby_dict(self) -> dict:
        return {
            "type": "lobby",
            "room_id": self.id,
            "phase": self.phase,
            "config": self.config.to_dict(),
            "timeout": self.timeout,
            "seats": [
                {"seat": i, "name": s.name, "ready": s.ready or i == 0, "connected": s.connected,
                 "host": i == 0}
                for i, s in enumerate(self.seat_list)
            ],
            "capacity": self.config.num_players,
        }

    def lobby_messages(self) -> list[Outbound]:
        return [(i, {**self.lobby_dict(), "you": i}) for i in range(len(self.seat_list))]

    def start(self, token: str, seed: int | None = None) -> list[Outbound]:
        if self.seat_of(token) != 0:
            raise RoomError("only the host can start the game")
        if self.state is not None:
            raise RoomError("game already started")
        if len(self.seat_list) != self.config.num_players:
            raise RoomError("waiting for more players")
        if not all(s.ready for s in self.seat_list[1:]):
            raise RoomError("not all players are ready")
        self.seed = secrets.randbits(32) if seed is None else seed
        self.state = new_game(self.config, self.seed)
        self._reset_deadline()
        return self._broadcast([])

    # ------------------------------------------------------------------ play
    def decision_dict(self) -> dict:
        d = current_decision(self.state)
        return {"kind": d.kind, "player": d.player, "context": d.context}

    def _reset_deadline(self) -> None:
        self.deadline = None
        if self.timeout is None or self.state is None or is_over(self.state):
            return
        if current_decision(self.state).kind in self.timeout_kinds:
            self.deadline = self.clock() + self.timeout

    def state_message(self, seat: int, events: list[dict] | None = None) -> dict:
        assert self.state is not None
        msg = {
            "type": "state",
            "you": seat,
            "phase": self.phase,
            "observation": observe(self.state, seat),
            "decision": self.decision_dict(),
            "legal_actions": [],
            "events": events or [],
            "deadline_in": (
                None if self.deadline is None else max(0.0, self.deadline - self.clock())
            ),
            "outcome": outcome(self.state),
        }
        if not is_over(self.state) and current_decision(self.state).player == seat:
            msg["legal_actions"] = [action_to_dict(a) for a in legal_actions(self.state)]
        return msg

    def _broadcast(self, events: list) -> list[Outbound]:
        assert self.state is not None
        return [
            (i, self.state_message(i, [redact_event(e, self.state, i) for e in events]))
            for i in range(len(self.seat_list))
        ]

    def sync(self, token: str) -> list[Outbound]:
        """Full current message for one seat (used on (re)connect)."""
        seat = self.seat_of(token)
        if self.state is None:
            return [(seat, {**self.lobby_dict(), "you": seat})]
        return [(seat, self.state_message(seat))]

    def _apply(self, action_dict: dict) -> list[Outbound]:
        action = action_from_dict(action_dict)  # raises IllegalActionError
        _, events = step(self.state, action)  # validates; raises IllegalActionError
        self.action_log.append(action_to_dict(action))
        self._reset_deadline()
        return self._broadcast(events)

    def submit(self, token: str, action_dict: dict) -> list[Outbound]:
        """Apply an action from the owner of the current decision. Errors go to the sender only."""
        try:
            seat = self.seat_of(token)
        except RoomError as e:
            raise RoomError(str(e)) from None
        if self.state is None:
            return [(seat, _error("game has not started"))]
        if is_over(self.state):
            return [(seat, _error("game is over"))]
        owner = current_decision(self.state).player
        if owner != seat:
            msg = f"not your decision (waiting for seat {owner})"
            return [(seat, _error(msg, "not_your_turn"))]
        try:
            return self._apply(action_dict)
        except IllegalActionError as e:
            return [(seat, _error(str(e), "illegal_action"))]
        except (KeyError, TypeError, ValueError) as e:
            return [(seat, _error(f"malformed action: {e!r}", "bad_action"))]

    def tick(self) -> list[Outbound]:
        """Resolve an expired timed decision (Pass / decline). Call periodically."""
        if self.deadline is None or self.state is None or self.clock() < self.deadline:
            return []
        kind = current_decision(self.state).kind
        action = Pass() if kind == "event_window" else Consent(False)
        return self._apply(action_to_dict(action))

    def chat(self, token: str, text: str) -> list[Outbound]:
        seat = self.seat_of(token)
        text = str(text).strip()[:MAX_CHAT]
        if not text:
            return []
        msg = {"type": "chat", "seat": seat, "name": self.seat_list[seat].name, "text": text}
        self.chat_log.append(msg)
        return [(i, msg) for i in range(len(self.seat_list))]

    # ------------------------------------------------------------ persistence
    def snapshot(self, checkpoint_every: int | None = None) -> dict:
        """JSON-able room snapshot.

        With ``checkpoint_every=N`` the snapshot also carries a state checkpoint, refreshed
        whenever N or more actions have been applied since the last one, so ``restore`` replays
        at most about N actions. Without it, an existing checkpoint is carried forward as is.
        """
        if checkpoint_every and self.state is not None:
            done = len(self.action_log)
            last = self.checkpoint["at"] if self.checkpoint else 0
            if done - last >= checkpoint_every:
                self.checkpoint = {"at": done, "state": self.state.to_dict()}
        snap = {
            "version": 1,
            "id": self.id,
            "config": self.config.to_dict(),
            "timeout": self.timeout,
            "timeout_kinds": list(self.timeout_kinds),
            "seats": [{"name": s.name, "token": s.token, "ready": s.ready} for s in self.seat_list],
            "seed": self.seed,
            "actions": list(self.action_log),
            "state_hash": None if self.state is None else state_hash(self.state),
        }
        if self.checkpoint is not None:
            snap["checkpoint"] = self.checkpoint
        return snap

    @classmethod
    def restore(cls, snap: dict, clock: Clock = time.monotonic) -> Room:
        """Rebuild a room from a snapshot and verify the stored state hash.

        Loads the checkpoint if there is one and replays only the actions after it; if that
        does not reproduce the stored hash it falls back to replaying the whole log from the
        seed. Snapshots without a checkpoint (the original format) replay everything.
        """
        room = cls(
            id=snap["id"],
            config=GameConfig.from_dict(snap["config"]),
            clock=clock,
            timeout=snap.get("timeout"),
            timeout_kinds=tuple(snap.get("timeout_kinds", ("event_window",))),
        )
        room.seat_list = [Seat(s["name"], s["token"], s.get("ready", False)) for s in snap["seats"]]
        if snap["seed"] is not None:
            room.seed = snap["seed"]
            actions = snap["actions"]
            expected = snap.get("state_hash")
            cp = snap.get("checkpoint")
            state = None
            if cp and 0 < cp["at"] <= len(actions):
                try:
                    state = GameState.from_dict(cp["state"])
                    for a in actions[cp["at"]:]:
                        step(state, action_from_dict(a))
                    if expected and state_hash(state) != expected:
                        state = None
                except Exception:
                    state = None
                if state is not None:
                    room.checkpoint = cp
            if state is None:
                state = new_game(room.config, room.seed)
                for a in actions:
                    step(state, action_from_dict(a))
                if expected and state_hash(state) != expected:
                    raise RoomError(f"replay mismatch restoring room {room.id}")
            room.state = state
            room.action_log = list(actions)
            room._reset_deadline()
        return room


def new_room(
    room_id: str,
    config: dict | GameConfig | None = None,
    timeout: float | None = None,
    timeout_consent: bool = False,
    clock: Clock = time.monotonic,
) -> Room:
    """Build an empty lobby. Raises ValueError/TypeError for a bad config."""
    if not isinstance(config, GameConfig):
        config = GameConfig(**(config or {}))
    kinds = ("event_window", "consent") if timeout_consent else ("event_window",)
    return Room(id=room_id, config=config, clock=clock, timeout=timeout, timeout_kinds=kinds)


def handle_client_message(room: Room, token: str, seat: int, data) -> list[Outbound]:
    """Dispatch one decoded client WebSocket message; errors come back as messages to ``seat``."""

    def err(message: str, code: str = "bad_request") -> list[Outbound]:
        return [(seat, _error(message, code))]

    if not isinstance(data, dict):
        return err("message must be a JSON object")
    kind = data.get("type")
    try:
        if kind == "action":
            if not isinstance(data.get("action"), dict):
                return err("missing action object")
            return room.submit(token, data["action"])
        if kind == "ready":
            return room.set_ready(token, bool(data.get("ready", True)))
        if kind == "start":
            return room.start(token)
        if kind == "chat":
            return room.chat(token, data.get("text", ""))
        if kind == "sync":
            return room.sync(token)
    except RoomError as e:
        return err(str(e))
    return err(f"unknown message type {kind!r}")


def _error(message: str, code: str = "error") -> dict:
    return {"type": "error", "code": code, "message": message}


class RoomManager:
    def __init__(
        self,
        clock: Clock = time.monotonic,
        storage_dir: str | Path | None = None,
        checkpoint_every: int | None = CHECKPOINT_EVERY,
    ):
        self.clock = clock
        self.checkpoint_every = checkpoint_every
        self.rooms: dict[str, Room] = {}
        self.storage_dir = Path(storage_dir) if storage_dir else None

    def create_room(
        self,
        config: dict | GameConfig | None = None,
        timeout: float | None = None,
        timeout_consent: bool = False,
    ) -> Room:
        room = new_room(new_room_id(), config, timeout, timeout_consent, self.clock)
        while room.id in self.rooms:
            room.id = new_room_id()
        self.rooms[room.id] = room
        return room

    def get(self, room_id: str) -> Room:
        try:
            return self.rooms[room_id]
        except KeyError:
            raise RoomError(f"no such room {room_id}") from None

    def tick(self) -> dict[str, list[Outbound]]:
        out = {}
        for rid, room in self.rooms.items():
            msgs = room.tick()
            if msgs:
                out[rid] = msgs
        return out

    # persistence
    def save(self, room: Room) -> None:
        if self.storage_dir is None:
            return
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.storage_dir / f"{room.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(room.snapshot(self.checkpoint_every)))
        tmp.replace(path)

    def load_all(self) -> int:
        if self.storage_dir is None or not self.storage_dir.is_dir():
            return 0
        n = 0
        for p in sorted(self.storage_dir.glob("*.json")):
            room = Room.restore(json.loads(p.read_text()), self.clock)
            self.rooms[room.id] = room
            n += 1
        return n
