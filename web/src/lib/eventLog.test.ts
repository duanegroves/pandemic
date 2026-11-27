import { describe, expect, it } from "vitest";
import samples from "../__fixtures__/samples.json";
import type { GameEvent, StateMsg } from "../types";
import { formatEvent, formatEvents, groupLog } from "./eventLog";

const S = Object.values(samples as unknown as Record<string, StateMsg>);
const ctx = { name: (i: number) => `P${i}`, you: 0 };

describe("event log", () => {
  const events: GameEvent[] = S.flatMap((m) => m.events);

  it("has real events to test with", () => {
    expect(new Set(events.map((e) => e.type)).size).toBeGreaterThan(15);
  });

  it("formats every real event type to non-empty text", () => {
    for (const e of events) {
      const f = formatEvent(e, ctx);
      expect(f, e.type).not.toBeNull();
      expect(f!.text.length).toBeGreaterThan(3);
      expect(f!.text).not.toContain("undefined");
      expect(f!.text).not.toContain("null");
    }
  });

  it("handles redacted draws", () => {
    const f = formatEvent({ type: "player_cards_drawn", player: 1, cards: [null, "Epidemic"] }, ctx)!;
    expect(f.text).toBe("P1 drew a card, Epidemic");
  });

  it("tells you apart from others and numbers entries", () => {
    const out = formatEvents(
      [
        { type: "turn_started", player: 1, turn: 3 },
        { type: "outbreak", city: "Paris", color: "blue", total: 2 },
        { type: "epidemic", player: 0, infection_rate_index: 1, infection_rate: 2 },
      ],
      ctx,
      10,
    );
    expect(out.map((o) => o.id)).toEqual([10, 11, 12]);
    expect(out[0].text).toBe("Turn 3: P1's turn");
    expect(out[1]).toMatchObject({ tone: "bad" });
    expect(out[1].text).toContain("OUTBREAK in Paris");
  });

  it("uses second person for you", () => {
    expect(
      formatEvent({ type: "pawn_moved", pawn: 0, from_city: "A", to_city: "B", method: "drive_ferry", by_player: 0 }, ctx)!.text,
    ).toBe("You drove from A to B");
    expect(
      formatEvent({ type: "pawn_moved", pawn: 0, from_city: "A", to_city: "B", method: "play_airlift", by_player: 1 }, ctx)!.text,
    ).toBe("You were airlifted from A to B (by P1)");
  });
});

describe("turn sections", () => {
  const turn = [
    { type: "cubes_placed", city: "Lima", color: "yellow", count: 3, source: "setup" },
    { type: "turn_started", player: 1, turn: 2 },
    { type: "pawn_moved", pawn: 0, from_city: "Atlanta", to_city: "Miami", method: "dispatcher_move", by_player: 1 },
    { type: "actions_ended", player: 1 },
    { type: "player_cards_drawn", player: 1, cards: ["Tokyo", "Epidemic"] },
    { type: "epidemic", player: 1, infection_rate_index: 1, infection_rate: 2 },
    { type: "infection_card_drawn", card: "Santiago", source: "epidemic" },
    { type: "cubes_placed", city: "Santiago", color: "yellow", count: 3, source: "epidemic" },
    { type: "intensify" },
    { type: "infection_card_drawn", card: "Tokyo", source: "infection" },
    { type: "outbreak", city: "Tokyo", color: "red", total: 1 },
    { type: "cubes_placed", city: "Osaka", color: "red", count: 1, source: "outbreak" },
    { type: "cubes_placed", city: "Osaka", color: "red", count: 1, source: "infection" },
    { type: "cure_discovered", player: 0, color: "blue" },
  ] as GameEvent[];
  const log = formatEvents(turn, ctx);
  const sections = groupLog(log);

  it("puts setup first, then one section per turn", () => {
    expect(sections.map((s) => s.turn?.n ?? "setup")).toEqual(["setup", 2]);
    expect(sections[1].turn).toEqual({ n: 2, player: 1 });
  });

  it("summarises draws, infections, epidemics, outbreaks and cures", () => {
    const s = sections[1].summary;
    expect(s.drew).toEqual([{ player: 1, cards: ["Tokyo"] }]); // Epidemic shown as its own chip
    expect(s.epidemics).toEqual(["Santiago"]);
    expect(s.outbreaks).toEqual([{ city: "Tokyo", color: "red" }]);
    expect(s.infected).toEqual([
      { city: "Santiago", color: "yellow", count: 3 },
      { city: "Osaka", color: "red", count: 2 }, // outbreak spread + infection add up
    ]);
    expect(s.cures).toEqual(["blue"]);
    expect(sections[0].summary.infected).toEqual([]); // setup cubes aren't "infections"
  });

  it("tags who did it, which disease, and what stands out", () => {
    const by = (t: string) => log.find((e) => e.text.toLowerCase().includes(t))!;
    expect(by("from atlanta").actor).toBe(1); // the Dispatcher who moved it, not the pawn
    expect(by("outbreak in tokyo")).toMatchObject({ disease: "red", emphasis: "alert" });
    expect(by("epidemic drawn")).toMatchObject({ emphasis: "alert" });
    expect(by("cure")).toMatchObject({ actor: 0, emphasis: "milestone" });
    expect(log.filter((e) => e.quiet).map((e) => e.text)).toEqual([
      "P1 ended their actions",
      "Epidemic infects: Santiago",
      "Infection card: Tokyo",
    ]);
  });
});

describe("first turn", () => {
  it("names the section before the first turn header after whoever acted in it", () => {
    const log = formatEvents(
      [
        { type: "cubes_placed", city: "Lima", color: "yellow", count: 3, source: "setup" },
        { type: "pawn_moved", pawn: 1, from_city: "Atlanta", to_city: "Miami", method: "drive_ferry", by_player: 1 },
        { type: "turn_started", player: 0, turn: 2 },
      ] as GameEvent[],
      ctx,
    );
    expect(groupLog(log).map((s) => s.turn)).toEqual([{ n: 1, player: 1 }, { n: 2, player: 0 }]);
    // with no actions yet it's just the setup
    expect(groupLog(log.slice(0, 1))[0].turn).toBeUndefined();
  });
});
