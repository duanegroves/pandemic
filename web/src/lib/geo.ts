import { CITY_GEO } from "../data/cityGeo";

/** Map coordinate space (SVG viewBox). */
export const MAP_W = 1200;
export const MAP_H = 700;
/** Longitude/latitude window shown (the Pandemic board only spans roughly -123..152 E, 60..-35 N). */
export const LON_MIN = -135;
export const LON_SPAN = 300;
export const LAT_MAX = 66;
export const LAT_SPAN = 108;
const PAD_X = 30;
const PAD_Y = 30;
const PLOT_W = MAP_W - 2 * PAD_X;
const PLOT_H = 640;
/** Label-box used for layout verification and relaxation. */
export const BOX_W = 74;
export const BOX_H = 52;

/** Equirectangular projection (x linear in lon, y linear in lat; y is stretched ~1.5x for legibility). */
export function project(lat: number, lon: number): { x: number; y: number } {
  return {
    x: PAD_X + ((lon - LON_MIN) / LON_SPAN) * PLOT_W,
    y: PAD_Y + ((LAT_MAX - lat) / LAT_SPAN) * PLOT_H,
  };
}

/** Pixel width of 360 degrees of longitude (used for the Pacific wrap). */
export const WORLD_W = (360 / LON_SPAN) * PLOT_W;

export function cityPos(name: string): { x: number; y: number } {
  const g = CITY_GEO[name];
  if (!g) throw new Error(`no geo for ${name}`);
  const p = project(g[0], g[1]);
  return { x: p.x + g[2], y: p.y + g[3] };
}

export interface Segment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * Line segments to draw for edge a-b. Normal edges give one segment. If the direct line is longer than
 * half the world (a Pacific crossing), two segments are returned, each running off the left or right edge
 * of the map, with the edge-crossing y interpolated along the wrapped line.
 */
export function edgeSegments(a: string, b: string): Segment[] {
  const pa = cityPos(a);
  const pb = cityPos(b);
  if (Math.abs(pa.x - pb.x) <= WORLD_W / 2) return [{ x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y }];
  const [w, e] = pa.x < pb.x ? [pa, pb] : [pb, pa]; // w = western (left) city, e = eastern (right) city
  const eWrapped = e.x - WORLD_W; // east city seen from beyond the left edge
  const t = (0 - w.x) / (eWrapped - w.x); // where the line crosses x = 0
  const yLeft = w.y + t * (e.y - w.y);
  const wWrapped = w.x + WORLD_W;
  const t2 = (MAP_W - e.x) / (wWrapped - e.x);
  const yRight = e.y + t2 * (w.y - e.y);
  return [
    { x1: w.x, y1: w.y, x2: 0, y2: yLeft },
    { x1: e.x, y1: e.y, x2: MAP_W, y2: yRight },
  ];
}
