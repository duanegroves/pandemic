"""Cloudflare Worker for Pandemic, speaking the protocol in docs/SERVER_PROTOCOL.md.

``Default`` routes HTTP and WebSocket requests; one ``RoomDO`` Durable Object per room holds the
game (``pandemic.server.rooms.Room``). The room is restored lazily from DO storage in every
handler, because a hibernated object loses all instance state. See docs/CLOUDFLARE.md.
"""

import json
import re
from urllib.parse import unquote

from js import Date, WebSocketPair
from workers import DurableObject, Response, WorkerEntrypoint

from pandemic.server.meta import meta_dict
from pandemic.server.rooms import (
    CHECKPOINT_EVERY,
    Room,
    RoomError,
    handle_client_message,
    idle_limit,
    message_too_large,
    new_room,
    new_room_id,
    parse_create_request,
)

ROOM_ID = r"[A-Za-z0-9_-]{1,32}"
ALARM_SLACK_MS = 25  # fire just after the deadline so Room.tick() sees it as expired
IDLE_TTL = 7 * 24 * 3600.0  # a room's storage is deleted this long after its last activity
FINISHED_TTL = 24 * 3600.0  # finished games are cleaned up sooner


def now() -> float:
    """Wall-clock seconds. Room deadlines use this so they survive eviction and restarts."""
    return Date.now() / 1000


def json_response(obj, status=200):
    return Response(
        json.dumps(obj), status=status, headers={"content-type": "application/json"}
    )


def detail(message: str, status: int):
    return json_response({"detail": message}, status)


def url_path(url: str) -> str:
    rest = url.split("//", 1)[-1]
    return "/" + rest.split("/", 1)[1].split("?")[0].split("#")[0] if "/" in rest else "/"


def url_query(url: str) -> dict:
    out = {}
    if "?" in url:
        for part in url.split("?", 1)[1].split("#")[0].split("&"):
            k, _, v = part.partition("=")
            out[k] = unquote(v.replace("+", " "))
    return out


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = url_path(request.url)
        method = str(request.method).upper()
        if path == "/meta" and method == "GET":
            return json_response(meta_dict())
        if path == "/rooms" and method == "POST":
            return await self.create_room(request)
        m = re.fullmatch(rf"/rooms/({ROOM_ID})(/join)?", path)
        if m and method == ("POST" if m.group(2) else "GET"):
            return await self.room_stub(m.group(1)).fetch(request)
        m = re.fullmatch(rf"/ws/({ROOM_ID})", path)
        if m:
            return await self.room_stub(m.group(1)).fetch(request)
        # Anything else is a static asset (the assets binding also handles the SPA fallback).
        return await self.env.ASSETS.fetch(request)

    def room_stub(self, room_id: str):
        ns = self.env.ROOM
        return ns.get(ns.idFromName(room_id))

    async def create_room(self, request):
        try:
            text = (await request.text()).strip()
            body = json.loads(text) if text else {}
        except ValueError:
            return detail("body must be JSON", 422)
        try:
            params = parse_create_request(body)
        except ValueError as e:
            return detail(str(e), 422)
        payload = {
            "config": params.config.to_dict(),
            "timeout": params.timeout,
            "timeout_consent": params.timeout_consent,
        }
        for _ in range(5):  # ids are random; a collision (409) just draws another one
            room_id = new_room_id()
            resp = await self.room_stub(room_id).fetch(
                "https://room.internal/init",
                method="POST",
                headers={"content-type": "application/json"},
                body=json.dumps({**payload, "room_id": room_id}),
            )
            if resp.status == 409:
                continue
            if resp.status != 200:
                return resp
            return json_response({"room_id": room_id})
        return detail("could not allocate a room id", 500)


def seat_of_socket(ws):
    """Seat for a live socket, from its attachment; None if unset or marked closed."""
    att = ws.deserializeAttachment()  # JsNull when nothing was serialized
    if not isinstance(att, str):
        return None
    try:
        return json.loads(att)["seat"]
    except (ValueError, KeyError, TypeError):
        return None


class RoomDO(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.room = None
        self.loaded = False
        self.last_active = now()

    # ------------------------------------------------------------ state
    async def load(self):
        """Restore the room from storage once per object lifetime (checkpoint + replay tail)."""
        if self.loaded:
            return
        raw = await self.ctx.storage.get("snap")
        if raw:
            snap = json.loads(raw)
            room = Room.restore(snap, clock=now)
            self.last_active = float(snap.get("last_active", now()))
            deadline_at = snap.get("deadline_at")
            if room.deadline is not None and deadline_at is not None:
                room.deadline = float(deadline_at)  # keep the original wall-clock deadline
            self.room = room
            self.refresh_connected()
        self.loaded = True

    async def save(self):
        snap = self.room.snapshot(CHECKPOINT_EVERY)
        snap["deadline_at"] = self.room.deadline
        self.last_active = now()
        snap["last_active"] = self.last_active
        await self.ctx.storage.put("snap", json.dumps(snap))
        await self.arm_alarm()

    def expires_at(self) -> float:
        """Wall-clock second after which an idle room's storage is deleted."""
        return self.last_active + idle_limit(self.room, IDLE_TTL, FINISHED_TTL)

    async def arm_alarm(self):
        """One alarm per object: the earlier of the decision deadline and the idle cleanup.

        A stale alarm firing early is harmless: ``alarm`` re-arms itself.
        """
        if self.room is None:
            return
        due = self.expires_at()
        if self.room.deadline is not None:
            due = min(due, self.room.deadline + ALARM_SLACK_MS / 1000)
        await self.ctx.storage.setAlarm(int(due * 1000))

    def sockets_by_seat(self) -> dict:
        out: dict = {}
        for ws in self.ctx.getWebSockets():
            seat = seat_of_socket(ws)
            if seat is not None:
                out.setdefault(seat, []).append(ws)
        return out

    def refresh_connected(self):
        """Recompute connected flags from the live sockets (the flags don't survive hibernation)."""
        live = self.sockets_by_seat()
        for i, s in enumerate(self.room.seat_list):
            s.connected = i in live

    def send(self, out):
        by_seat = self.sockets_by_seat()
        for seat, msg in out:
            socks = by_seat.get(seat)
            if not socks:
                continue
            payload = json.dumps(msg)
            for ws in socks:
                try:
                    ws.send(payload)
                except Exception:
                    pass  # a socket that is going away; its close handler cleans up

    # ------------------------------------------------------------ HTTP
    async def fetch(self, request):
        await self.load()
        self.last_active = now()
        path = url_path(request.url)
        method = str(request.method).upper()
        if path == "/init" and method == "POST":
            return await self.init_room(request)
        m = re.fullmatch(rf"/rooms/({ROOM_ID})(/join)?", path)
        if m:
            if self.room is None:
                await request.text()  # drain the body, or workerd logs an error
                return detail(f"no such room {m.group(1)}", 404)
            if m.group(2):
                return await self.join(request)
            self.refresh_connected()
            return json_response(self.room.lobby_dict())
        m = re.fullmatch(rf"/ws/({ROOM_ID})", path)
        if m:
            return self.open_socket(request)
        return detail("not found", 404)

    async def init_room(self, request):
        if self.room is not None:
            return detail("room exists", 409)
        body = await request.json()
        try:
            params = parse_create_request(body)
            room = new_room(
                body["room_id"],
                params.config,
                params.timeout,
                params.timeout_consent,
                clock=now,
            )
        except (ValueError, TypeError, KeyError) as e:
            return detail(str(e), 422)
        self.room = room
        await self.save()
        return json_response({"room_id": room.id})

    async def join(self, request):
        try:
            body = await request.json()
            name, token = body.get("name") or "", body.get("token")
            if not isinstance(name, str) or not (token is None or isinstance(token, str)):
                raise ValueError
        except (ValueError, AttributeError):
            return detail("body must be {name, token}", 422)
        try:
            seat, token, msgs = self.room.join(name, token)
        except RoomError as e:
            return detail(str(e), 409)
        await self.save()
        self.refresh_connected()
        self.send(self.room.lobby_messages())
        return json_response({"room_id": self.room.id, "seat": seat, "token": token})

    def open_socket(self, request):
        if request.headers.get("Upgrade") != "websocket":
            return Response("expected websocket", status=426)
        token = url_query(request.url).get("token", "")
        client, server = WebSocketPair.new().object_values()
        seat = None
        if self.room is not None:
            try:
                seat = self.room.seat_of(token)
            except RoomError:
                pass
        if seat is None:
            # Accept, then close, so browsers see the close code (a refused handshake is a 1006).
            server.accept()  # plain (non-hibernating) accept: nothing to keep for a refused socket
            server.close(4401, "unknown room or token")
            return Response(None, status=101, web_socket=client)
        self.ctx.acceptWebSocket(server)
        server.serializeAttachment(json.dumps({"seat": seat}))
        self.refresh_connected()
        # Like the FastAPI server: lobby broadcast for the connect, then state for this socket.
        self.send(self.room.lobby_messages())
        if self.room.state is not None:
            server.send(json.dumps(self.room.state_message(seat)))
        return Response(None, status=101, web_socket=client)

    # ------------------------------------------------------------ WebSocket (hibernation API)
    async def webSocketMessage(self, ws, message):
        await self.load()
        seat = seat_of_socket(ws)
        if self.room is None or seat is None:
            return
        token = self.room.seat_list[seat].token

        def reply(code, text):
            ws.send(json.dumps({"type": "error", "code": code, "message": text}))

        self.last_active = now()
        if not isinstance(message, str):
            return reply("bad_request", "binary messages are not supported")
        if message_too_large(message):
            return reply("bad_request", "message too large")
        try:
            data = json.loads(message)
        except ValueError:
            return reply("bad_request", "message must be JSON")
        msgs = handle_client_message(self.room, token, seat, data)
        if any(m.get("type") in ("state", "lobby") for _, m in msgs):
            await self.save()
        self.send(msgs)

    async def webSocketClose(self, ws, code, reason, was_clean):
        await self.load()
        seat = seat_of_socket(ws)
        ws.serializeAttachment("closed")  # getWebSockets() may still list it during this call
        try:
            # 1005/1006 are not valid to send; reply with a plain close in that case.
            ws.close(code, reason) if 1000 <= code <= 1003 or 3000 <= code <= 4999 else ws.close()
        except Exception:
            pass
        if self.room is None or seat is None:
            return
        self.refresh_connected()
        if not self.room.seat_list[seat].connected:
            self.send(self.room.lobby_messages())

    async def webSocketError(self, ws, error):
        await self.webSocketClose(ws, 1006, "error", False)

    # ------------------------------------------------------------ timeouts
    async def alarm(self, alarm_info=None):
        """Auto-pass/decline an expired decision, and delete an idle room's storage.

        Safe to run twice: tick() is deadline-gated and cleanup is time-gated.
        """
        await self.load()
        if self.room is None:
            return
        msgs = self.room.tick()
        if msgs:
            await self.save()
            self.send(msgs)
            return
        if now() >= self.expires_at():
            if self.ctx.getWebSockets():
                self.last_active = now()  # someone is still connected: not idle
            else:
                await self.ctx.storage.deleteAll()  # also clears the alarm
                self.room = None
                return
        await self.arm_alarm()  # fired early (or retried after the work was done)
