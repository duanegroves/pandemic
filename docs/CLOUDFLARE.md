# Cloudflare Workers + Durable Objects backend

A second wrapper around the same engine and `Room` class as the FastAPI server. It speaks
exactly the protocol in `docs/SERVER_PROTOCOL.md`, serves the built React app, and runs on the
Cloudflare free plan. Overview of all deployment options: `docs/DEPLOY.md`.

## Architecture

```
browser --HTTP/WS--> Worker (cloudflare/worker/src/entry.py, class Default)
                        |-- GET /meta, static assets (public/), SPA fallback, /debug/
                        |-- POST /rooms                 -> picks a random id, init on the room's DO
                        |-- GET /rooms/{id}, POST /rooms/{id}/join, WS /ws/{id}
                        v
                     RoomDO  (one Durable Object per room, idFromName(room_id))
                        holds a pandemic.server.rooms.Room, DO storage key "snap"
```

- **Shared code.** `src/pandemic/engine`, `data`, `server/rooms.py` and `server/meta.py` are the
  only things the Worker uses. `scripts/sync.sh` copies them into `cloudflare/worker/src/pandemic/`
  (gitignored; never commit the copies) and builds `cloudflare/worker/public/` from `web/dist` plus
  the debug client at `/debug/`. Everything protocol-level that is not transport lives in
  `rooms.py` (`handle_client_message`, `new_room`, snapshots), so FastAPI and the Worker cannot drift.
- **Routing.** `assets.run_worker_first` sends `/rooms`, `/rooms/*`, `/meta` and `/ws/*` to the
  Worker; everything else is a static asset (free, unlimited), with
  `not_found_handling: single-page-application` for deep links. `/?room=abc` is just `/`.
  Unknown rooms return 404 like FastAPI (the id is only valid once `POST /rooms` initialised the DO).
- **WebSockets** use the Hibernation API (`ctx.acceptWebSocket`, `webSocketMessage`,
  `webSocketClose`). Each socket's attachment holds `{"seat": n}` (the token is looked up from the
  room), so seat mapping survives hibernation. A bad room or token is accepted and then closed with
  code **4401** (the client sees the code; a refused handshake would show as 1006).
- **Lazy restore.** A hibernated or evicted DO loses all instance state, so every handler first
  calls `load()`, which rebuilds the `Room` from storage once. The `connected` flags are
  recomputed from `ctx.getWebSockets()` after every wake, connect and close.
- **Persistence.** After every state or lobby change the whole snapshot is written to storage
  (`config`, seats and tokens, seed, action log, state hash) plus a **state checkpoint**
  (`GameState.to_dict()` and the number of actions it covers) refreshed every 25 actions
  (`CHECKPOINT_EVERY` in `rooms.py`). `Room.restore` loads the checkpoint and replays only the
  actions after it, then verifies the SHA-256 state hash; if the checkpoint does not reproduce the
  hash it falls back to a full replay from the seed. Snapshots without a checkpoint (older files,
  FastAPI before this change) still restore. The FastAPI `RoomManager` writes the same format.
- **Timeouts.** When a room has a deadline (pending `event_window`, optionally `consent`), the DO
  sets an alarm for it (`deadline + 25 ms`). The alarm handler calls `room.tick()`, persists,
  broadcasts and re-arms if a new deadline exists. Deadlines are wall-clock (`Date.now()`) and
  stored in the snapshot (`deadline_at`), so they survive eviction and restarts. Alarms retry on
  errors; the handler is idempotent because `tick()` only acts when the stored deadline has passed,
  and an early or repeated alarm just re-arms.
- **Chat** is broadcast to connected seats; the history (`room.chat_log`) is in memory only and is
  lost when the DO is evicted. Nothing reads it today.

## Protocol differences from FastAPI

None that a client can observe, apart from these implementation details:

- Both servers now accept the WebSocket first and then close with 4401 for a bad token or room.
- Non-JSON text frames get a `bad_request` error message on both (FastAPI used to drop the
  connection).
- Room ids are 6 hex characters on both; the Worker 404s ids that are not `[A-Za-z0-9_-]{1,32}`.

## Local development

Needs uv >= 0.13.4 (`pywrangler` requirement; `brew upgrade uv`), Node 22, and a built frontend.

```bash
cd web && npm ci && npm run build && cd ..
cd cloudflare/worker
./scripts/sync.sh                       # copy engine + frontend in (re-run after changing them)
uv run pywrangler dev --port 8788       # http://localhost:8788
```

DO storage persists in `cloudflare/worker/.wrangler/state`, so restarting `pywrangler dev` keeps
rooms (delete that directory to reset). Editing `src/entry.py` auto-reloads.

## Conformance tests

`tests/conformance/conformance.py` runs the same scenarios against any base URL: REST basics,
join/reconnect by token, wrong token (close 4401), lobby flow with chat and connected flags, errors
to the sender only, a full two-client game to completion with redaction checks, timeout auto-pass,
and restart-restore (two extra phases).

```bash
# one command: starts the backend on a free port, runs everything, restarts it, verifies, stops it
uv run --all-extras python tests/conformance/run.py fastapi
uv run --all-extras python tests/conformance/run.py worker

# against something already running or deployed
uv run --all-extras python tests/conformance/conformance.py --base https://pandemic-game.<you>.workers.dev
```

`--phase restart-setup` / `--phase restart-verify` (with `--state-file`) split the restart-restore
check around a server restart or deploy. Test clients send a browser-like User-Agent because
workers.dev bot filtering returns 403 to default Python ones (`Python-urllib`, `websockets`).

## Deploy by hand

```bash
cd web && npm ci && npm run build && cd ..
cd cloudflare/worker
./scripts/sync.sh
uv run pywrangler deploy --dry-run      # builds and lists bindings, no upload
uv run pywrangler login                 # or export CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID
uv run pywrangler deploy
```

The Worker name is `pandemic-game` (URL `https://pandemic-game.<your-subdomain>.workers.dev`).
This replaces the feasibility spike that was deployed under the same name: the Durable Object class
is still `RoomDO` with the unchanged `v1` migration (`new_sqlite_classes`), so no new migration is
needed. Rooms left over from the spike stay in storage but are harmless. If you ever rename or
delete the class, add a new migration tag (`renamed_classes` or `deleted_classes`) instead of
editing `v1`.

## Deploy via GitHub Actions

The `deploy-cloudflare` job in `.github/workflows/deploy.yml` runs after `test` on pushes to `main`
(and manual runs) when the repository variable `CLOUDFLARE_ENABLED` is `true`. It builds
`web/dist`, runs `sync.sh`, installs uv >= 0.13.4 and runs `uv run pywrangler deploy`.

1. Find your **Account ID**: Cloudflare dashboard, Workers & Pages, right-hand sidebar (or the URL
   `dash.cloudflare.com/<account id>/...`).
2. Create an **API token**: dashboard, My Profile, API Tokens, Create Token. Easiest is the
   **Edit Cloudflare Workers** template, restricted under Account Resources to your one account.
   A custom token needs, at minimum, Account / Workers Scripts / Edit (the template also adds
   read-only account settings and user details, which wrangler uses for lookups; add Account /
   Account Settings / Read if a deploy complains). No zone permissions are needed for a
   `workers.dev` deployment.
3. Store them and enable the job:

   ```bash
   gh secret set CLOUDFLARE_API_TOKEN          # paste the token
   gh secret set CLOUDFLARE_ACCOUNT_ID --body "<account id>"
   gh variable set CLOUDFLARE_ENABLED --body true
   ```

First time only: the account needs a `workers.dev` subdomain (dashboard, Workers & Pages), which
the first `wrangler deploy` offers to create when run interactively.

## Limits and free-plan notes (from the feasibility spike, 2026-11)

- The free plan accepts Python Workers and SQLite-backed Durable Objects. No paid plan was needed.
- Free limits: 10 ms CPU per request/event, 128 MB memory, about 1 s startup, 100k DO requests/day,
  100k rows written/day; static asset requests are free. Each WebSocket message is a DO request,
  so a very long game session over many players could approach the daily cap; the paid plan
  ($5/month) raises all of these.
- Startup time measured live was 653-754 ms (Pyodide + our modules) against the ~1 s limit, so
  avoid heavy top-level imports. The bundle is about 54 modules, 206 KiB.
- CPU per event measured live on the spike: WebSocket action mostly 2-3 ms (max 13 ms), connect
  1-14 ms, room info 3-19 ms. Cloudflare tolerated occasional bursts over 10 ms. This is why
  restore uses checkpoints: replaying a long game on wake is the main risk, and now costs at most
  25 steps plus one `GameState.from_dict`. If CPU limits do bite, lower `CHECKPOINT_EVERY`
  or move to the paid plan.
- In-Worker timers read 0 ms (the clock is frozen during compute). Use `wrangler tail --format json`
  (`cpuTime`) or the dashboard for timings.
- Latency from a dev machine: static page 0.11-0.2 s, WebSocket action round trip to both clients
  70-150 ms.
- Hibernation: ping/pong are answered without waking the DO; attachments are limited to 16 KiB;
  alarms are one per DO and retried with backoff on uncaught exceptions.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pywrangler` complains about the uv version | needs uv >= 0.13.4: `brew upgrade uv`, or `astral-sh/setup-uv` with `version: ">=0.13.4"` |
| `missing .../web/dist/index.html` from `sync.sh` | build the frontend first (`cd web && npm ci && npm run build`) |
| Python client gets 403 from `workers.dev` | bot filtering; send a browser-like `User-Agent` (browsers are fine) |
| `deserializeAttachment()` returns `JsNull` | a socket with no attachment; the code checks `isinstance(att, str)` |
| `ws.close(1006)` raises `InvalidAccessError` | 1005/1006 cannot be sent; `webSocketClose` falls back to a plain close |
| Changes to the engine have no effect | re-run `scripts/sync.sh`; the Worker uses the copies in `cloudflare/worker/src/pandemic/` |
| Room restore raises `replay mismatch` | the engine changed in a way that alters old games; the stored hash no longer matches. Old rooms are unrecoverable, new ones are fine |
| Deploy fails on authentication in CI | check the two secrets and that the token is scoped to the right account |
| Console error "Can't read from request stream after response has been sent" | a handler answered before reading a request body; the code drains bodies on 404 paths |
| Timeouts fire late or not at all in dev | alarms need the DO to be running under `pywrangler dev`; check the log for exceptions in `alarm()` |
