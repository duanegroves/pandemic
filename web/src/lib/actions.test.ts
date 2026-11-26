import { describe, expect, it } from "vitest";
import samples from "../__fixtures__/samples.json";
import type { Action, StateMsg } from "../types";
import {
  EVENT_KEYS,
  buildForecastAction,
  cureByColor,
  describeAction,
  describeConsent,
  groupActions,
  moveTargets,
  narrow,
  targetCity,
  treatByColor,
} from "./actions";

const S = samples as unknown as Record<string, StateMsg>;
const L = {
  you: 0,
  player: (s: number) => `P${s}`,
};

describe("groupActions on a real actions-phase message", () => {
  const m = S["action:drive_ferry"];
  const g = groupActions(m.legal_actions);

  it("is the owner's message with legal actions", () => {
    expect(m.legal_actions.length).toBeGreaterThan(0);
    expect(m.decision.player).toBe(m.you);
  });

  it("indexes movement by destination and matches moveTargets", () => {
    const targets = moveTargets(m.legal_actions);
    expect([...g.byCity.keys()].sort()).toEqual([...targets].sort());
    for (const [city, acts] of g.byCity) for (const a of acts) expect(targetCity(a)).toBe(city);
    const drives = m.legal_actions.filter((a) => a.type === "drive_ferry");
    for (const d of drives) expect(g.byCity.get(d.destination)).toContain(d);
  });

  it("offers end_actions and puts every action in exactly one bucket or the city map", () => {
    expect(g.end).not.toBeNull();
    const counted =
      g.treat.length + g.build.length + g.give.length + g.take.length + g.cure.length + g.takeEvent.length +
      (g.end ? 1 : 0) + g.other.length +
      [...g.events.values()].reduce((n, l) => n + l.length, 0) +
      m.legal_actions.filter((a) => targetCity(a) && !a.type.startsWith("play_")).length;
    expect(counted).toBe(m.legal_actions.length);
    expect(g.other).toEqual([]);
  });
});

describe("treat / build / share on real messages", () => {
  it("treat_disease by color", () => {
    const m = S["action:treat_disease"];
    const g = groupActions(m.legal_actions);
    const t = treatByColor(g.treat);
    expect(t.size).toBeGreaterThan(0);
    const me = m.observation.players[m.you];
    for (const c of t.keys()) expect(m.observation.cubes[me.location][c as "blue"]).toBeGreaterThan(0);
  });
  it("build, give and take land in their buckets", () => {
    expect(groupActions(S["action:build_research_station"].legal_actions).build.length).toBeGreaterThan(0);
    expect(groupActions(S["action:give_card"].legal_actions).give.length).toBeGreaterThan(0);
    expect(groupActions(S["action:take_card"].legal_actions).take.length).toBeGreaterThan(0);
  });
  it("take_event_card is a role action", () => {
    expect(groupActions(S["action:take_event_card"].legal_actions).takeEvent.length).toBeGreaterThan(0);
  });
  it("dispatcher moves are shown with the moved pawn", () => {
    const a = S["action:dispatcher_move"].legal_actions.find((x) => x.type === "dispatcher_move")!;
    expect(describeAction(a, { ...L, you: 99 })).toContain(`P${a.pawn}`);
  });
});

describe("event cards", () => {
  it("groups plays by card; Airlift needs pawn then destination", () => {
    const m = S["action:play_airlift"];
    const g = groupActions(m.legal_actions);
    const acts = g.events.get("Airlift")!;
    expect(acts.length).toBeGreaterThan(1);
    // airlift destinations are also reachable from the map
    for (const a of acts) expect(g.byCity.get(a.destination)).toContain(a);
    let r = narrow(acts, EVENT_KEYS.Airlift, {});
    const pawns = new Set(acts.map((a) => a.pawn));
    if (pawns.size > 1) {
      expect("choice" in r && r.choice.key).toBe("pawn");
      const first = [...pawns][0];
      r = narrow(acts, EVENT_KEYS.Airlift, { pawn: JSON.stringify(first) });
    }
    expect("choice" in r && r.choice.key).toBe("destination");
    const dest = acts[0].destination;
    const done = narrow(acts, EVENT_KEYS.Airlift, { pawn: JSON.stringify(acts[0].pawn), destination: JSON.stringify(dest) });
    expect("done" in done && done.done).toEqual(acts[0]);
  });
  it("One Quiet Night and Forecast are single actions (no choice needed)", () => {
    for (const [key, card] of [
      ["action:play_one_quiet_night", "One Quiet Night"],
      ["action:play_forecast", "Forecast"],
    ] as const) {
      const acts = groupActions(S[key].legal_actions).events.get(card)!;
      expect(acts).toHaveLength(1);
      expect("done" in narrow(acts, EVENT_KEYS[card], {})).toBe(true);
    }
  });
  it("Government Grant narrows city then relocation", () => {
    const acts = groupActions(S["action:play_government_grant"].legal_actions).events.get("Government Grant")!;
    const r = narrow(acts, EVENT_KEYS["Government Grant"], {});
    expect("choice" in r && r.choice.key).toBe("city");
  });
  it("targetCity covers grant city", () => {
    expect(targetCity({ type: "play_government_grant", city: "Paris", relocate_from: null })).toBe("Paris");
  });
});

describe("narrow", () => {
  const relocate: Action[] = [
    { type: "build_research_station", relocate_from: "Atlanta" },
    { type: "build_research_station", relocate_from: "Paris" },
  ];
  it("asks for the relocation choice when several are legal", () => {
    const r = narrow(relocate, ["relocate_from"], {});
    expect("choice" in r && r.choice.options.map((o) => o.value)).toEqual(["Atlanta", "Paris"]);
  });
  it("a single build with null relocate needs no choice", () => {
    const one = [{ type: "build_research_station", relocate_from: null }];
    expect("done" in narrow(one, ["relocate_from"], {})).toBe(true);
  });
  it("reports none for impossible choices", () => {
    expect(narrow(relocate, ["relocate_from"], { relocate_from: '"Lima"' })).toEqual({ none: true });
  });
});

describe("discover_cure (synthetic, same JSON shape as ENGINE_API.md)", () => {
  const cures: Action[] = [
    { type: "discover_cure", color: "blue", cards: ["Atlanta", "Chicago", "Essen", "London", "Madrid"] },
    { type: "discover_cure", color: "blue", cards: ["Atlanta", "Chicago", "Essen", "London", "Milan"] },
    { type: "discover_cure", color: "red", cards: ["Bangkok", "Beijing", "Hong Kong", "Jakarta", "Manila"] },
  ];
  it("groups by color then asks which cards", () => {
    const by = cureByColor(cures);
    expect([...by.keys()]).toEqual(["blue", "red"]);
    let r = narrow(cures, ["color", "cards"], {});
    expect("choice" in r && r.choice.key).toBe("color");
    r = narrow(cures, ["color", "cards"], { color: '"blue"' });
    expect("choice" in r && r.choice.key).toBe("cards");
    r = narrow(cures, ["color", "cards"], { color: '"red"' });
    expect("done" in r && r.done.color).toBe("red");
  });
  it("a cure action is classified as cure", () => {
    expect(groupActions(cures).cure).toHaveLength(3);
  });
});

describe("discard, event window, consent", () => {
  it("discard decisions: discards + event plays", () => {
    const m = S["action:discard"];
    expect(m.decision.kind).toBe("discard");
    const g = groupActions(m.legal_actions);
    expect(g.discards.length).toBeGreaterThan(0);
    const hand = m.observation.players[m.you].hand!;
    for (const d of g.discards) expect(hand).toContain(d.card);
    expect(g.end).toBeNull();
  });
  it("event window: has Pass and at least one event", () => {
    const m = S["action:pass"];
    const g = groupActions(m.legal_actions);
    expect(g.pass).not.toBeNull();
    expect(g.events.size).toBeGreaterThan(0);
  });
  it("consent: accept/decline and a description", () => {
    const m = S["action:consent"];
    const g = groupActions(m.legal_actions);
    expect(g.consent.map((a) => a.accept).sort()).toEqual([false, true]);
    const ctx = m.decision.context;
    const text = describeConsent(ctx.requester, ctx.request, L);
    expect(text).toContain(`P${ctx.requester}`);
    expect(text.length).toBeGreaterThan(20);
  });
});

describe("forecast", () => {
  const m = S["action:forecast_order"];
  const cards: string[] = m.decision.context.cards;
  it("offers every permutation of the revealed cards", () => {
    expect(m.legal_actions).toHaveLength(factorial(cards.length));
  });
  it("builds a valid ForecastOrder and rejects anything the server did not offer", () => {
    const rev = [...cards].reverse();
    expect(buildForecastAction(rev, m.legal_actions)).toEqual({ type: "forecast_order", order: rev });
    expect(buildForecastAction([...cards.slice(1), "Nowhere"], m.legal_actions)).toBeNull();
    expect(buildForecastAction(cards.slice(1), m.legal_actions)).toBeNull();
  });
});

function factorial(n: number): number {
  return n <= 1 ? 1 : n * factorial(n - 1);
}

describe("describeAction", () => {
  it("describes every action in every sample without falling back to raw JSON", () => {
    for (const m of Object.values(S))
      for (const a of m.legal_actions.slice(0, 50)) {
        const t = describeAction(a, L);
        expect(t.startsWith("{")).toBe(false);
      }
  });
});
