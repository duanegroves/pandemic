"""FastAPI app: REST for room management, WebSocket for play. See docs/SERVER_PROTOCOL.md."""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pandemic.data.cards import EventCard
from pandemic.data.cities import CITIES
from pandemic.engine.config import ROLES
from pandemic.server.rooms import Outbound, Room, RoomError, RoomManager

STATIC = Path(__file__).parent / "static"
_DEFAULT_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
WEB_DIST = Path(os.environ.get("PANDEMIC_WEB_DIST") or _DEFAULT_DIST)
TICK_SECONDS = 0.5


class CreateRoom(BaseModel):
    config: dict = Field(default_factory=dict)
    timeout: float | None = Field(default=None, gt=0)
    timeout_consent: bool = False


class JoinRoom(BaseModel):
    name: str = ""
    token: str | None = None


class Hub:
    """Room manager plus per-room locks and live WebSocket connections."""

    def __init__(self, manager: RoomManager):
        self.manager = manager
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.conns: dict[str, dict[int, set[WebSocket]]] = defaultdict(lambda: defaultdict(set))

    async def deliver(self, room_id: str, msgs: list[Outbound]) -> None:
        for seat, msg in msgs:
            for ws in list(self.conns[room_id][seat]):
                try:
                    await ws.send_json(msg)
                except Exception:
                    self.conns[room_id][seat].discard(ws)

    async def ticker(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            for rid, room in list(self.manager.rooms.items()):
                if room.deadline is None:
                    continue
                async with self.locks[rid]:
                    msgs = room.tick()
                    if msgs:
                        self.manager.save(room)
                        await self.deliver(rid, msgs)


def create_app(manager: RoomManager | None = None) -> FastAPI:
    if manager is None:
        manager = RoomManager(storage_dir=os.environ.get("PANDEMIC_DATA_DIR") or None)
        manager.load_all()
    hub = Hub(manager)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(hub.ticker())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="Pandemic server", lifespan=lifespan)
    app.state.hub = hub

    def room_or_404(room_id: str) -> Room:
        try:
            return manager.get(room_id)
        except RoomError as e:
            raise HTTPException(404, str(e)) from None

    @app.get("/meta")
    def meta():
        """Static board data so clients need not duplicate the map."""
        return {
            "cities": [
                {"name": c.name, "color": c.color.value, "population": c.population,
                 "neighbors": list(c.neighbors)}
                for c in CITIES.values()
            ],
            "roles": [r.value for r in ROLES],
            "events": [e.value for e in EventCard],
        }

    @app.get("/debug")
    def debug_client():
        return FileResponse(STATIC / "index.html")

    @app.get("/")
    def index():
        built = WEB_DIST / "index.html"
        return FileResponse(built if built.is_file() else STATIC / "index.html")

    @app.post("/rooms")
    def create_room(body: CreateRoom | None = None):
        body = body or CreateRoom()
        try:
            room = manager.create_room(body.config, body.timeout, body.timeout_consent)
        except (ValueError, TypeError) as e:
            raise HTTPException(422, str(e)) from None
        manager.save(room)
        return {"room_id": room.id}

    @app.get("/rooms/{room_id}")
    def get_room(room_id: str):
        return room_or_404(room_id).lobby_dict()

    @app.post("/rooms/{room_id}/join")
    async def join_room(room_id: str, body: JoinRoom):
        room = room_or_404(room_id)
        async with hub.locks[room_id]:
            try:
                seat, token, msgs = room.join(body.name, body.token)
            except RoomError as e:
                raise HTTPException(409, str(e)) from None
            manager.save(room)
            await hub.deliver(room_id, msgs)
        return {"room_id": room_id, "seat": seat, "token": token}

    @app.websocket("/ws/{room_id}")
    async def ws_endpoint(ws: WebSocket, room_id: str, token: str = ""):
        room = manager.rooms.get(room_id)
        try:
            if room is None:
                raise RoomError("no such room")
            seat = room.seat_of(token)
        except RoomError:
            await ws.close(code=4401)
            return
        await ws.accept()
        async with hub.locks[room_id]:
            hub.conns[room_id][seat].add(ws)
            await hub.deliver(room_id, room.set_connected(seat, True))
            if room.state is not None:
                await ws.send_json(room.state_message(seat))
        try:
            while True:
                data = await ws.receive_json()
                async with hub.locks[room_id]:
                    msgs = _handle(room, token, seat, data)
                    if any(m.get("type") in ("state", "lobby") for _, m in msgs):
                        manager.save(room)
                    await hub.deliver(room_id, msgs)
        except WebSocketDisconnect:
            pass
        finally:
            async with hub.locks[room_id]:
                hub.conns[room_id][seat].discard(ws)
                if not hub.conns[room_id][seat]:
                    await hub.deliver(room_id, room.set_connected(seat, False))

    # Built frontend assets (registered last so API routes win). Mounted only if present.
    if (WEB_DIST / "index.html").is_file():
        app.mount("/", StaticFiles(directory=WEB_DIST), name="web")

    return app


def _handle(room: Room, token: str, seat: int, data) -> list[Outbound]:
    def err(message: str, code: str = "bad_request") -> list[Outbound]:
        return [(seat, {"type": "error", "code": code, "message": message})]

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


app = create_app()
