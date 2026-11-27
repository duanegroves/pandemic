# Server protocol

Run: `uv run uvicorn pandemic.server.app:app` or `uv run python -m pandemic.server --port 8000`
(needs the `server` extra: `uv sync --extra server`). Set `PANDEMIC_DATA_DIR=./rooms` to persist
rooms as JSON snapshots (reloaded at startup). `GET /` serves a debug client.

## REST

| Request | Body | Response |
|---|---|---|
| `POST /rooms` | `{"config": {GameConfig fields}, "timeout": seconds\|null, "timeout_consent": bool}` | `{"room_id"}` (422 on bad config) |
| `GET /rooms/{id}` | | lobby object (see below); 404 if unknown |
| `POST /rooms/{id}/join` | `{"name": str, "token": str\|null}` | `{"room_id","seat","token"}`; 409 if full or started |

`config` takes `num_players`, `difficulty`, `roles`, `open_hands`, `auto_consent`,
`event_windows`. Seats are assigned in join order; seat 0 is the host. The `token` is the
player's secret: join again with it (or just open the WebSocket) to reconnect.
`timeout`: seconds before an unanswered `event_window` decision is auto-passed (and, with
`timeout_consent`, an unanswered `consent` is declined). Timed-out actions are recorded in the
action log like any other.

## WebSocket `/ws/{room_id}?token=...`

Invalid room/token: the socket is accepted and then closed with code 4401. On connect the server sends the current `lobby`
message (before start) or `state` message (after start).

### Client to server

| message | effect |
|---|---|
| `{"type":"ready","ready":true}` | set ready flag (lobby only) |
| `{"type":"start"}` | host only; needs a full room with everyone ready; server picks the seed |
| `{"type":"action","action":{...}}` | engine action JSON (see ENGINE_API.md); only the owner of the current decision may act |
| `{"type":"chat","text":"..."}` | broadcast to all seats |
| `{"type":"sync"}` | resend the current lobby/state message to the sender |

### Server to client

- `{"type":"lobby","room_id","phase":"lobby|playing|over","config","timeout","capacity","seats":[{"seat","name","ready","connected","host"}],"you":seat}`
  sent on every join, ready change and connect/disconnect.
- `{"type":"state","you","phase","observation","decision":{"kind","player","context"},"legal_actions":[...],"events":[...],"deadline_in":seconds|null,"outcome":null|{...}}`
  sent to every seat after each applied action. `observation` is `observe(state, you)`;
  `events` are the engine events from that step passed through `redact_event` for that seat.
  `legal_actions` (action JSON) is non-empty only for the owner of the current decision.
  `deadline_in` is the seconds until a pending auto-pass/decline.
- `{"type":"chat","seat","name","text"}`
- `{"type":"error","code","message"}` sent only to the offending client. Codes: `not_your_turn`,
  `illegal_action`, `bad_action`, `bad_request`, `error`. The game state is unchanged.

## Persistence

A snapshot is `{id, config, timeout, seats (name, token), seed, actions: [action dicts],
state_hash, checkpoint?}`. `checkpoint` is `{"at": n, "state": GameState.to_dict()}`: the state
after the first `n` actions, refreshed every 25 actions when the caller asks for it
(`Room.snapshot(checkpoint_every=...)`). `Room.restore` loads the checkpoint and replays only
`actions[n:]` (or replays everything from the seed when there is none, or when the checkpoint
fails to reproduce the hash) and checks the SHA-256 of the state JSON, raising `RoomError` on a
mismatch. Snapshots without `checkpoint` remain valid.

The Cloudflare Worker backend (`docs/CLOUDFLARE.md`) implements this same protocol.
