// Plays full games over the real server using the UI's own grouping/forecast/log logic.
// Skipped unless PANDEMIC_URL is set, e.g.  PANDEMIC_URL=http://localhost:8010 npm test
import { describe, expect, it } from "vitest";
import { buildForecastAction, groupActions } from "./lib/actions";
import { formatEvents } from "./lib/eventLog";
import type { Action, StateMsg } from "./types";

const base = process.env.PANDEMIC_URL;

async function post(path: string, body: unknown) {
  const r = await fetch(base + path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  expect(r.ok).toBe(true);
  return r.json();
}

/** A UI-style policy: only picks actions via the grouped structure the UI renders. */
function choose(m: StateMsg): Action {
  const g = groupActions(m.legal_actions);
  expect(g.other, "ungrouped actions").toEqual([]);
  switch (m.decision.kind) {
    case "forecast_order": {
      const cards: string[] = m.decision.context.cards;
      const a = buildForecastAction([...cards].reverse(), g.forecast);
      expect(a).not.toBeNull();
      return a!;
    }
    case "consent":
      return g.consent.find((a) => a.accept)!;
    case "event_window":
      return g.pass!;
    case "discard":
      return g.discards[0];
    default: {
      if (g.cure.length) return g.cure[0];
      if (g.treat.length) return g.treat[0];
      if (g.build.length && Math.random() < 0.3) return g.build[0];
      const rnd = Math.random();
      if (rnd < 0.5) {
        const cities = [...g.byCity.keys()];
        const acts = g.byCity.get(cities[Math.floor(Math.random() * cities.length)]) ?? [];
        const a = acts.find((x) => !x.type.startsWith("play_"));
        if (a) return a;
      }
      if (g.events.size && rnd > 0.9) return [...g.events.values()][0][0];
      return g.end ?? m.legal_actions[0];
    }
  }
}

describe.skipIf(!base)("full 2-player game via the UI logic", () => {
  it("plays to completion", async () => {
    const wsBase = base!.replace(/^http/, "ws");
    const { room_id } = await post("/rooms", { config: { num_players: 2, difficulty: "introductory" } });
    const seats = [await post(`/rooms/${room_id}/join`, { name: "A" }), await post(`/rooms/${room_id}/join`, { name: "B" })];
    let steps = 0;
    let logged = 0;
    const final = await new Promise<StateMsg>((resolve, reject) => {
      let done = 0;
      const timer = setTimeout(() => reject(new Error("timeout")), 60000);
      seats.forEach((s, i) => {
        const ws = new WebSocket(`${wsBase}/ws/${room_id}?token=${s.token}`);
        ws.onopen = () => ws.send(JSON.stringify({ type: "ready", ready: true }));
        ws.onmessage = (ev) => {
          try {
            const m = JSON.parse(ev.data as string);
            if (m.type === "lobby" && i === 0 && m.phase === "lobby" && m.seats.length === 2 && m.seats.every((x: { ready: boolean }) => x.ready))
              ws.send(JSON.stringify({ type: "start" }));
            if (m.type === "error") throw new Error(m.message);
            if (m.type !== "state") return;
            logged += formatEvents(m.events, { name: (k) => `P${k}`, you: m.you }).length;
            if (m.phase === "over") {
              ws.close();
              if (++done === 2) {
                clearTimeout(timer);
                resolve(m);
              }
            } else if (m.legal_actions.length) {
              steps++;
              ws.send(JSON.stringify({ type: "action", action: choose(m) }));
            }
          } catch (e) {
            clearTimeout(timer);
            reject(e);
          }
        };
      });
    });
    expect(["win", "loss"]).toContain(final.outcome!.result);
    expect(steps).toBeGreaterThan(10);
    expect(logged).toBeGreaterThan(steps);
  }, 70000);
});
