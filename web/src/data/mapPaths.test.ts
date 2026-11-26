import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { LAND, REGIONS } from "./mapPaths";
import { LAT_MAX, LAT_SPAN, LON_MIN, LON_SPAN, MAP_H, MAP_W, project } from "../lib/geo";

const MARGIN = 150;

function subpaths(d: string): [number, number][][] {
  return d
    .split("M")
    .filter(Boolean)
    .map((s) =>
      s
        .replace(/Z$/, "")
        .split("L")
        .map((p) => p.split(" ").map(Number) as [number, number]),
    );
}

const all: [string, string][] = [["LAND", LAND], ...Object.entries(REGIONS)];

describe("map paths", () => {
  it.each(all)("%s is non-empty with no NaN", (_n, d) => {
    expect(d.length).toBeGreaterThan(1000);
    expect(d).not.toMatch(/NaN|undefined|Infinity/);
  });

  it.each(all)("%s stays near the viewBox and has no long streak segments", (_n, d) => {
    for (const ring of subpaths(d)) {
      expect(ring.length).toBeGreaterThanOrEqual(3);
      for (let i = 0; i < ring.length; i++) {
        const [x, y] = ring[i]!;
        expect(Number.isFinite(x) && Number.isFinite(y)).toBe(true);
        expect(x).toBeGreaterThan(-MARGIN);
        expect(x).toBeLessThan(MAP_W + MARGIN);
        expect(y).toBeGreaterThan(-MARGIN);
        expect(y).toBeLessThan(MAP_H + MARGIN);
        const [x2, y2] = ring[(i + 1) % ring.length]!;
        expect(Math.abs(x2 - x)).toBeLessThan(MAP_W / 2);
        expect(Math.abs(y2 - y)).toBeLessThan(MAP_H / 2);
      }
    }
  });

  it("gen-map.mjs projection constants match geo.ts", () => {
    const src = readFileSync(new URL("../../scripts/gen-map.mjs", import.meta.url), "utf8");
    const num = (n: string) => Number(new RegExp(`${n} = (-?\\d+)`).exec(src)![1]);
    expect(num("MAP_W")).toBe(MAP_W);
    expect(num("LON_MIN")).toBe(LON_MIN);
    expect(num("LON_SPAN")).toBe(LON_SPAN);
    expect(num("LAT_MAX")).toBe(LAT_MAX);
    expect(num("LAT_SPAN")).toBe(LAT_SPAN);
    const px = num("PAD_X"), py = num("PAD_Y"), ph = num("PLOT_H");
    const p = project(10, 20);
    expect(p.x).toBeCloseTo(px + ((20 - LON_MIN) / LON_SPAN) * (MAP_W - 2 * px));
    expect(p.y).toBeCloseTo(py + ((LAT_MAX - 10) / LAT_SPAN) * ph);
  });
});
