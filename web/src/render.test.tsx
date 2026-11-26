import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import meta from "./__fixtures__/meta.json";
import samples from "./__fixtures__/samples.json";
import { Game } from "./components/Game";
import { Lobby } from "./components/Lobby";
import { MetaContext } from "./meta";
import type { LobbyMsg, Meta, StateMsg } from "./types";
import type { RoomView } from "./useRoomSocket";

const S = samples as unknown as Record<string, StateMsg>;
const noop = () => true;

function lobbyFor(m: StateMsg): LobbyMsg {
  return {
    type: "lobby",
    room_id: "abc123",
    phase: "playing",
    config: {},
    timeout: null,
    capacity: m.observation.players.length,
    seats: m.observation.players.map((p) => ({ seat: p.index, name: `Name${p.index}`, ready: true, connected: true, host: p.index === 0 })),
    you: m.you,
  };
}

function html(m: StateMsg) {
  const view: RoomView = {
    status: "open",
    lobby: lobbyFor(m),
    game: { msg: m, receivedAt: Date.now() },
    log: [{ id: 1, text: "Turn 1: Name0's turn", tone: "turn" }],
    chat: [],
    error: null,
  };
  return renderToString(
    <MetaContext.Provider value={meta as Meta}>
      <Game view={view} send={noop} sendAction={noop} onLeave={() => {}} />
    </MetaContext.Provider>,
  );
}

describe("server-rendered smoke tests with real messages", () => {
  it("renders every captured state without throwing, with all 48 cities", () => {
    for (const [k, m] of Object.entries(S)) {
      const h = html(m);
      expect(h, k).toContain("Pandemic");
      expect((h.match(/class="city/g) ?? []).length, k).toBe(48);
    }
  });
  it("shows movement targets and the action bar for the decision owner", () => {
    const h = html(S["action:drive_ferry"]);
    expect(h).toContain("target-ring");
    expect(h).toContain("End actions");
    expect(h).toContain("All legal actions");
  });
  it("shows consent and forecast prompts", () => {
    expect(html(S["action:consent"])).toContain("Consent requested");
    expect(html(S["action:forecast_order"])).toContain("Forecast: arrange");
  });
  it("shows the game over modal", () => {
    expect(html(S["decision:game_over"])).toMatch(/Defeat|Victory/);
  });
  it("renders the lobby", () => {
    vi.stubGlobal("location", { origin: "http://x", pathname: "/" });
    const m = S["action:drive_ferry"];
    const l = { ...lobbyFor(m), phase: "lobby" as const };
    const h = renderToString(
      <Lobby roomId="abc123" view={{ status: "open", lobby: l, game: null, log: [], chat: [], error: null }} send={noop} onLeave={() => {}} />,
    );
    expect(h).toContain("abc123");
    expect(h).toContain("Not ready");
  });
});
