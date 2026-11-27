import { describe, expect, it } from "vitest";
import meta from "../__fixtures__/meta.json";
import { EVENT_INFO, eventInfo } from "./eventCards";

describe("event card descriptions", () => {
  it("describes every event card the server knows about", () => {
    for (const c of meta.events as string[]) expect(EVENT_INFO[c]?.length, c).toBeGreaterThan(20);
  });
  it("returns nothing for city cards", () => {
    expect(eventInfo("Atlanta")).toBeUndefined();
  });
});
