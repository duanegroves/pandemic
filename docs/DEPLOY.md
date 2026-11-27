# Deployment overview

The game has one shared core (`src/pandemic`: rules engine and `server/rooms.py`) and two server
wrappers that speak the same protocol ([SERVER_PROTOCOL.md](SERVER_PROTOCOL.md)), so the React
frontend runs unchanged on either. What is deployed right now: [DEPLOY_STATUS.md](DEPLOY_STATUS.md).

| Option | What runs | Good for | Guide |
|---|---|---|---|
| **Local** | FastAPI server, serves `web/dist` | development, playing on a LAN | below |
| **Docker image** (anywhere, e.g. an Oracle Cloud VM) | FastAPI in a container, Caddy for HTTPS, rooms in a volume | one always-on box you control | [DEPLOY_ORACLE.md](DEPLOY_ORACLE.md) |
| **Cloudflare** | Python Worker + one Durable Object per room, static assets | free, no server to run, global edge | [CLOUDFLARE.md](CLOUDFLARE.md) |

## Local

```bash
cd web && npm ci && npm run build && cd ..          # builds web/dist
uv run --all-extras python -m pandemic.server --port 8000
# optional: PANDEMIC_DATA_DIR=./rooms keeps rooms across restarts
```

Open <http://localhost:8000>. The Cloudflare Worker can also run locally (`pywrangler dev`), see
[CLOUDFLARE.md](CLOUDFLARE.md).

## CI/CD

`.github/workflows/ci.yml` runs on every push to `main` (and on pull requests, for `test` only):

1. `test`: ruff, mypy, pytest, the conformance suite against FastAPI, frontend tests and build.
2. `build`: multi-arch Docker image pushed to ghcr.io (`:latest` and `:<sha>`).
3. `deploy`: Oracle VM over SSH, only if the repository variable `DEPLOY_ENABLED=true`.
4. `deploy-cloudflare`: `pywrangler deploy`, only if the repository variable
   `CLOUDFLARE_ENABLED=true` (needs the secrets `CLOUDFLARE_API_TOKEN` and
   `CLOUDFLARE_ACCOUNT_ID`).

The two deploy jobs are independent; enable one, both, or neither. Dependabot
(`.github/dependabot.yml`) opens weekly update PRs for the actions, Python, npm and Docker
dependencies. The conformance suite against the Worker (`run.py worker`) needs `pywrangler dev`
and is run by hand, not in CI.

## Verifying a deployment

Scripted protocol checks run against any base URL (both backends pass them):

```bash
uv run --all-extras python tests/conformance/run.py fastapi    # starts a local server, restarts it
uv run --all-extras python tests/conformance/run.py worker     # same with pywrangler dev
uv run --all-extras python tests/conformance/conformance.py --base https://your-host
```

Against a deployed `workers.dev` host this needs a browser-like User-Agent, which the script
already sends. `--phase restart-setup` / `--phase restart-verify` (with `--state-file`) split the
restart-restore check around a server restart or deploy.

## Limits and housekeeping (both backends)

Defined once in `src/pandemic/server/rooms.py`:

- `timeout` on room creation is `null` or 5 to 600 seconds (422 otherwise).
- Inbound WebSocket messages are limited to 16 KiB (an `error` message is returned and the
  message is ignored); chat messages to 500 characters; each room keeps its last 100 chat
  messages in memory.
- FastAPI keeps at most `PANDEMIC_MAX_ROOMS` rooms (default 500). Rooms with nobody connected
  that are idle for `PANDEMIC_IDLE_HOURS` (default 48), or `PANDEMIC_FINISHED_IDLE_HOURS`
  (default 1) once the game is over, are evicted from memory and from `PANDEMIC_DATA_DIR`.
  `POST /rooms` returns 503 when the server is still full after eviction.
- On Cloudflare each room's Durable Object deletes its own storage 7 days after its last
  activity (1 day once the game is over) unless someone is connected.

## Notes

- There are no accounts: anyone with the URL can create a room, and anyone with a room code can
  join an open seat. Fine for friends; don't post the URL publicly. Seat tokens travel in the
  WebSocket URL query, so they appear in access logs.
