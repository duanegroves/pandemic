# Pandemic

A cooperative Pandemic board game implementation: a Python rules engine, reinforcement-learning
environments, and a multiplayer web app (FastAPI or Cloudflare Worker backend, React frontend).

> **Unofficial fan project.** This project is not affiliated with, authorized, or endorsed by
> Z-Man Games or Asmodee. *Pandemic* is a trademark of its respective owners. It is a personal,
> non-commercial implementation for learning and play. The rulebook and the official game art
> are not included; you need your own copy of the game to learn the rules.

## What is in the repository

- **Rules engine** (`src/pandemic/engine/`): `new_game`, `legal_actions`, `step`, `observe`. Pure
  Python, no dependencies, deterministic from a seed. See [docs/ENGINE_API.md](docs/ENGINE_API.md).
- **RL environments** (`src/pandemic/ai/`): PettingZoo and Gymnasium wrappers, a fixed action
  encoding and baseline agents.
- **Multiplayer server** (`src/pandemic/server/`): rooms over REST and WebSocket, with the
  protocol in [docs/SERVER_PROTOCOL.md](docs/SERVER_PROTOCOL.md). The same protocol is served by
  a FastAPI app and by a Cloudflare Worker (`cloudflare/worker/`); a conformance suite checks
  both.
- **Web client** (`web/`): Vite, React and TypeScript. See [web/README.md](web/README.md).

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12) and Node 22.

```sh
# Python tests, lint and type check
uv run --all-extras pytest -q
uv run ruff check
uv run mypy src

# Frontend tests and build
cd web && npm ci && npm test && npm run build && cd ..

# Run the server locally (serves web/dist at http://127.0.0.1:8000)
uv run --all-extras python -m pandemic.server --port 8000

# Frontend dev server with hot reload (proxies to the server above)
cd web && npm run dev
```

Check that both backends still speak the same protocol:

```sh
uv run --all-extras python tests/conformance/run.py fastapi
uv run --all-extras python tests/conformance/run.py worker   # needs uv >= 0.13.4, web/dist built
```

## Deployment

There are two supported targets, described in [docs/DEPLOY.md](docs/DEPLOY.md):

- **Cloudflare Worker** with one Durable Object per room: [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).
- **Docker on a VM** (Oracle Cloud Always Free, Caddy for TLS): [docs/DEPLOY_ORACLE.md](docs/DEPLOY_ORACLE.md).

Current state: [docs/DEPLOY_STATUS.md](docs/DEPLOY_STATUS.md). There is no authentication; rooms
are meant for friends who share a room code.

## License

[MIT](LICENSE). The license covers this repository's code only, not the Pandemic name or game.
