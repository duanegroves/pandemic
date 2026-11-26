import { describe, expect, it } from "vitest";
import samples from "../__fixtures__/samples.json";
import type { GameEvent, StateMsg } from "../types";
import { formatEvent, formatEvents } from "./eventLog";

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
