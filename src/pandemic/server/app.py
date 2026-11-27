"""FastAPI app: REST for room management, WebSocket for play. See docs/SERVER_PROTOCOL.md."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pandemic.server.meta import meta_dict
from pandemic.server.rooms import (
    Outbound,
    Room,
    RoomError,
    RoomManager,
    handle_client_message,
)

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
        return meta_dict()

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
        await ws.accept()
        room = manager.rooms.get(room_id)
        try:
            if room is None:
                raise RoomError("no such room")
            seat = room.seat_of(token)
        except RoomError:
            # Accept first so the client sees close code 4401 (closing before accept would be a
            # plain HTTP 403 handshake failure, which browsers report as 1006).
            await ws.close(code=4401)
            return
        async with hub.locks[room_id]:
            hub.conns[room_id][seat].add(ws)
            await hub.deliver(room_id, room.set_connected(seat, True))
            if room.state is not None:
                await ws.send_json(room.state_message(seat))
        try:
            while True:
                try:
                    data = json.loads(await ws.receive_text())
                except ValueError:
                    await ws.send_json({"type": "error", "code": "bad_request",
                                        "message": "message must be JSON"})
                    continue
                async with hub.locks[room_id]:
                    msgs = handle_client_message(room, token, seat, data)
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


app = create_app()
