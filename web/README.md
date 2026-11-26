# Pandemic web client

Vite + React + TypeScript frontend for the Pandemic server (`src/pandemic/server`).

## Development

```sh
# terminal 1: API server (port 8000 by default)
uv run --all-extras python -m pandemic.server --port 8000
# terminal 2: Vite dev server with hot reload; proxies /rooms, /meta and /ws
cd web && npm install && npm run dev      # http://localhost:5173
# different backend port:  PANDEMIC_SERVER=http://localhost:8010 npm run dev
```

Open several tabs to play as several players: the seat token is kept in `sessionStorage` per tab and
room. Share a room with `/?room=<code>`.

## Production

```sh
cd web && npm install && npm run build   # outputs web/dist
uv run --all-extras python -m pandemic.server --port 8000
```

FastAPI serves `web/dist` at `/` (falls back to the old debug client if `dist` is missing; the debug client
is always available at `/debug`). Override the location with `PANDEMIC_WEB_DIST`.

## Checks

```sh
npm run typecheck     # tsc --noEmit
npm test              # Vitest (unit + render smoke tests, fixtures in src/__fixtures__)
PANDEMIC_URL=http://localhost:8010 npm test   # also plays a full game through the UI logic over a live server
node scripts/play.mjs --base http://localhost:8010 --players 2 --games 3   # random-bot sanity player
node scripts/play.mjs --players 3 --games 6 --windows full --consent --capture src/__fixtures__/samples.json
                                                  # regenerates the sample state messages
```

## Layout

- `src/lib/actions.ts`: pure legal-actions to UI grouping (`groupActions`, `narrow`, `buildForecastAction`, labels)
- `src/lib/eventLog.ts`: engine events to log text; `src/lib/geo.ts` + `src/data/cityGeo.ts`: projection and layout
- `src/useRoomSocket.ts`: WebSocket with exponential-backoff reconnect; `src/lib/net.ts`: REST + session storage
- `src/components/`: Home, Lobby, Game (decision handling), Board (SVG), Status/Players panels, Chooser, Forecast, Log
