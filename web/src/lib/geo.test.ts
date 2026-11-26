import { describe, expect, it } from "vitest";
import meta from "../__fixtures__/meta.json";
import { CITY_GEO } from "../data/cityGeo";
import { BOX_H, BOX_W, MAP_H, MAP_W, cityPos, edgeSegments, project } from "./geo";
import { backoffMs, remaining } from "./countdown";

const cities = meta.cities as { name: string; neighbors: string[]; color: string }[];

describe("city layout", () => {
  it("has geo data for exactly the 48 cities of /meta", () => {
    expect(Object.keys(CITY_GEO).sort()).toEqual(cities.map((c) => c.name).sort());
  });

  it("uses an equirectangular projection (monotonic in lon and lat)", () => {
    expect(project(0, 10).x).toBeGreaterThan(project(0, 0).x);
    expect(project(10, 0).y).toBeLessThan(project(0, 0).y);
    const d1 = project(0, 20).x - project(0, 10).x;
    const d2 = project(0, 90).x - project(0, 80).x;
    expect(d1).toBeCloseTo(d2);
  });

  it("keeps every city inside the viewBox with room for its label box", () => {
    for (const c of cities) {
      const p = cityPos(c.name);
      expect(p.x - BOX_W / 2).toBeGreaterThanOrEqual(0);
      expect(p.x + BOX_W / 2).toBeLessThanOrEqual(MAP_W);
      expect(p.y - BOX_H / 2).toBeGreaterThanOrEqual(0);
      expect(p.y + BOX_H / 2).toBeLessThanOrEqual(MAP_H);
    }
  });

  it("has no two overlapping label boxes", () => {
    const pos = cities.map((c) => ({ n: c.name, ...cityPos(c.name) }));
    const bad: string[] = [];
    for (let i = 0; i < pos.length; i++)
      for (let j = i + 1; j < pos.length; j++) {
        const ox = BOX_W - Math.abs(pos[i].x - pos[j].x);
        const oy = BOX_H - Math.abs(pos[i].y - pos[j].y);
        if (ox > 2 && oy > 2) bad.push(`${pos[i].n}/${pos[j].n}`);
      }
    expect(bad).toEqual([]);
  });

  it("keeps nudged cities near their real location", () => {
    for (const [name, [lat, lon]] of Object.entries(CITY_GEO)) {
      const real = project(lat, lon);
      const p = cityPos(name);
      expect(Math.hypot(p.x - real.x, p.y - real.y), name).toBeLessThan(60);
    }
  });
});

describe("edges", () => {
  const key = (a: string, b: string) => [a, b].sort().join("|");
  const all = new Set<string>();
  for (const c of cities) for (const n of c.neighbors) all.add(key(c.name, n));

  it("has the 3 Pacific wrap edges, and only those, drawn as two segments", () => {
    const wraps = [...all].filter((k) => {
      const [a, b] = k.split("|");
      return edgeSegments(a, b).length === 2;
    });
    expect(wraps.sort()).toEqual(
      [key("San Francisco", "Tokyo"), key("San Francisco", "Manila"), key("Los Angeles", "Sydney")].sort(),
    );
  });

  it("wrap segments run to the map edges at a y inside the map", () => {
    for (const [a, b] of [
      ["San Francisco", "Tokyo"],
      ["San Francisco", "Manila"],
      ["Los Angeles", "Sydney"],
    ]) {
      const [left, right] = edgeSegments(a, b);
      expect(left.x2).toBe(0);
      expect(right.x2).toBe(MAP_W);
      for (const y of [left.y2, right.y2]) {
        expect(y).toBeGreaterThan(0);
        expect(y).toBeLessThan(MAP_H);
      }
      // left segment starts at the western city, right at the eastern one
      expect(left.x1).toBeLessThan(MAP_W / 2);
      expect(right.x1).toBeGreaterThan(MAP_W / 2);
    }
  });
});

describe("countdown helpers", () => {
  it("counts down from receipt time and never goes negative", () => {
    expect(remaining(null, 0, 5)).toBeNull();
    expect(remaining(30, 1000, 11000)).toBe(20);
    expect(remaining(5, 0, 60000)).toBe(0);
  });
  it("backs off exponentially up to 10s", () => {
    expect([0, 1, 2, 3].map(backoffMs)).toEqual([500, 1000, 2000, 4000]);
    expect(backoffMs(20)).toBe(10000);
  });
});
