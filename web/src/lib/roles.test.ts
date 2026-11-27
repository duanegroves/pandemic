import { describe, expect, it } from "vitest";
import meta from "../__fixtures__/meta.json";
import { ROLE_INFO } from "./roles";

describe("role descriptions", () => {
  it("describes every role the server knows about", () => {
    for (const r of meta.roles as string[]) {
      expect(ROLE_INFO[r], r).toBeDefined();
      expect(ROLE_INFO[r].summary.length).toBeGreaterThan(10);
      expect(ROLE_INFO[r].abilities.length).toBeGreaterThan(0);
    }
  });
});
