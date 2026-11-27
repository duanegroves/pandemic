# Deployment options

The game has one shared core (`src/pandemic`: rules engine and `server/rooms.py`) and two server
wrappers that speak the same protocol (`docs/SERVER_PROTOCOL.md`), so the React frontend runs
unchanged on either.

| Option | What runs | Good for | Details |
|---|---|---|---|
| **Local** | FastAPI server, serves `web/dist` | development, playing on a LAN | below |
| **Docker image** (anywhere, e.g. an Oracle Cloud VM) | FastAPI in a container, Caddy for HTTPS, rooms in a volume | one always-on box you control | `docs/DEPLOY_ORACLE.md` |
| **Cloudflare** | Python Worker + one Durable Object per room, static assets | free, no server to run, global edge | `docs/CLOUDFLARE.md` |

## Local

```bash
cd web && npm ci && npm run build && cd ..          # builds web/dist
uv run --all-extras python -m pandemic.server --port 8000
# optional: PANDEMIC_DATA_DIR=./rooms keeps rooms across restarts
```

Open <http://localhost:8000>. The Cloudflare Worker can also run locally (`pywrangler dev`), see
`docs/CLOUDFLARE.md`.

## CI/CD

`.github/workflows/deploy.yml` runs on every push to `main`:

1. `test`: Python lint and tests, frontend tests and build.
2. `build`: multi-arch Docker image pushed to ghcr.io.
3. `deploy`: Oracle VM over SSH, only if the repo variable `DEPLOY_ENABLED=true`.
4. `deploy-cloudflare`: `pywrangler deploy`, only if the repo variable `CLOUDFLARE_ENABLED=true`
   (needs the secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`).

The two deploy jobs are independent; enable one, both, or neither.

## Verifying a deployment

Scripted protocol checks run against any base URL (both backends pass them):

```bash
uv run --all-extras python tests/conformance/conformance.py --base https://your-host
```

Against a deployed `workers.dev` host this needs a browser-like User-Agent, which the script
already sends. See `docs/CLOUDFLARE.md` for the restart-restore phases and `tests/conformance/run.py`
for the local runner.

## Notes

- There are no accounts: anyone with the URL can create a room, and anyone with a room code can
  join an open seat. Fine for friends; don't post the URL publicly.
