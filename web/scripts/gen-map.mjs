// Generates src/data/mapPaths.ts (LAND + REGIONS SVG paths). Run: npm run gen:map
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { feature, merge } from "topojson-client";

const require = createRequire(import.meta.url);
const topo = JSON.parse(readFileSync(require.resolve("world-atlas/countries-110m.json"), "utf8"));
const root = new URL("..", import.meta.url);

// --- projection: MUST match src/lib/geo.ts (checked by mapPaths.test.ts) ---
const MAP_W = 1200, LON_MIN = -135, LON_SPAN = 300, LAT_MAX = 66, LAT_SPAN = 108;
const PAD_X = 30, PAD_Y = 30, PLOT_W = MAP_W - 2 * PAD_X, PLOT_H = 640;
const px = (lon) => PAD_X + ((lon - LON_MIN) / LON_SPAN) * PLOT_W;
const py = (lat) => PAD_Y + ((LAT_MAX - lat) / LAT_SPAN) * PLOT_H;
// Clip box (only trims Alaska/Aleutian slivers far west; the viewBox clips the rest).
const CX0 = -100, CX1 = 1300, CY0 = -100, CY1 = 800;

// --- cities: true lat/lon from cityGeo.ts, colors from the /meta fixture ---
const geoSrc = readFileSync(new URL("src/data/cityGeo.ts", root), "utf8");
const cityGeo = {};
for (const m of geoSrc.matchAll(/"([^"]+)":\s*\[\s*(-?[\d.]+),\s*(-?[\d.]+)/g)) cityGeo[m[1]] = [+m[2], +m[3]];
const meta = JSON.parse(readFileSync(new URL("src/__fixtures__/meta.json", root), "utf8"));
const cities = meta.cities.map((c) => ({ name: c.name, color: c.color, lat: cityGeo[c.name][0], lon: cityGeo[c.name][1] }));

const rad = Math.PI / 180;
function gc(lat1, lon1, lat2, lon2) {
  const a = Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 2 * Math.asin(Math.sqrt(a));
}

// Countries whose nearest-city result is odd (or that span several regions).
const OVERRIDE = {
  Greenland: "blue", Iceland: "blue", Russia: "black", Egypt: "black", Sudan: "yellow", "S. Sudan": "yellow",
  Turkey: "black", Australia: "red", "New Zealand": "red", Indonesia: "red", Kazakhstan: "black",
  Uzbekistan: "black", Turkmenistan: "black", Kyrgyzstan: "black", Tajikistan: "black", Afghanistan: "black",
  Mongolia: "red", China: "red", Canada: "blue", "United States of America": "blue", Mexico: "yellow",
  Libya: "black", Algeria: "black", Morocco: "blue", "W. Sahara": "blue", Tunisia: "black",
  Ukraine: "black", Belarus: "blue", Georgia: "black", Armenia: "black", Azerbaijan: "black",
  "Papua New Guinea": "red", Fiji: "red", "New Caledonia": "red", Ethiopia: "yellow", Somalia: "yellow",
  Eritrea: "yellow", Chad: "yellow", Niger: "yellow", Mali: "yellow", Mauritania: "yellow",
};

const countries = feature(topo, topo.objects.countries).features.filter((f) => f.properties.name !== "Antarctica");
const geomById = new Map(topo.objects.countries.geometries.map((g) => [g.id ?? g.properties?.name, g]));

function polys(f) {
  return f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
}
function ringArea(r) {
  let a = 0;
  for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
  return a / 2;
}
function centroid(r) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < r.length - 1; i++) {
    const k = r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
    a += k; cx += (r[i][0] + r[i + 1][0]) * k; cy += (r[i][1] + r[i + 1][1]) * k;
  }
  return a ? [cx / (3 * a), cy / (3 * a)] : r[0];
}

const assign = {};
const byColor = { blue: [], yellow: [], black: [], red: [] };
const auto = [];
countries.forEach((f, i) => {
  const name = f.properties.name;
  const big = polys(f).map((p) => p[0]).sort((a, b) => Math.abs(ringArea(b)) - Math.abs(ringArea(a)))[0];
  const [lon, lat] = centroid(big);
  let best = null, bd = Infinity;
  for (const c of cities) {
    const d = gc(lat, lon, c.lat, c.lon);
    if (d < bd) { bd = d; best = c; }
  }
  const color = OVERRIDE[name] ?? best.color;
  assign[name] = color;
  if (!OVERRIDE[name]) auto.push(`${name}->${best.name}(${best.color})`);
  byColor[color].push(topo.objects.countries.geometries.find((g) => g.id === f.id && g.properties.name === name));
});

// --- ring processing ---
function clipEdge(pts, inside, inter) {
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const ia = inside(a), ib = inside(b);
    if (ia) out.push(a);
    if (ia !== ib) out.push(inter(a, b));
  }
  return out;
}
function clipRing(pts) {
  const lerpX = (x) => (a, b) => [x, a[1] + ((b[1] - a[1]) * (x - a[0])) / (b[0] - a[0])];
  const lerpY = (y) => (a, b) => [a[0] + ((b[0] - a[0]) * (y - a[1])) / (b[1] - a[1]), y];
  let r = pts;
  for (const [ins, int] of [
    [(p) => p[0] >= CX0, lerpX(CX0)], [(p) => p[0] <= CX1, lerpX(CX1)],
    [(p) => p[1] >= CY0, lerpY(CY0)], [(p) => p[1] <= CY1, lerpY(CY1)],
  ]) {
    if (r.length < 3) return [];
    r = clipEdge(r, ins, int);
  }
  return r;
}
const r1 = (n) => Math.round(n * 10) / 10;
// Ramer-Douglas-Peucker on an open polyline.
function rdp(pts, eps) {
  if (pts.length < 3) return pts;
  const [a, b] = [pts[0], pts[pts.length - 1]];
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1e-9;
  let mi = 0, md = -1;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = Math.abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / len;
    if (d > md) { md = d; mi = i; }
  }
  if (md <= eps) return [a, b];
  return [...rdp(pts.slice(0, mi + 1), eps).slice(0, -1), ...rdp(pts.slice(mi), eps)];
}
const SIMPLIFY = 0.6;
function ringPath(ring) {
  // Unwrap longitudes so rings crossing +-180 (Chukotka, Fiji) stay continuous instead of streaking across the map.
  const un = [];
  let prev = null;
  for (const [lon0, lat] of ring.slice(0, -1)) {
    let lon = lon0;
    if (prev !== null) while (lon - prev > 180) lon -= 360;
    if (prev !== null) while (lon - prev < -180) lon += 360;
    un.push([lon, lat]);
    prev = lon;
  }
  let pts = un.map(([lon, lat]) => [px(lon), py(lat)]);
  pts = clipRing(pts);
  if (pts.length > 4) {
    // split at the farthest-apart pair of anchor points so a closed ring simplifies well
    const h = Math.floor(pts.length / 2);
    pts = [...rdp(pts.slice(0, h + 1), SIMPLIFY).slice(0, -1), ...rdp([...pts.slice(h), pts[0]], SIMPLIFY).slice(0, -1)];
  }
  pts = pts.map(([x, y]) => [r1(x), r1(y)]);
  pts = pts.filter((p, i) => i === 0 || p[0] !== pts[i - 1][0] || p[1] !== pts[i - 1][1]);
  if (pts.length < 3 || Math.abs(ringArea([...pts, pts[0]])) < 6) return "";
  return "M" + pts.map((p) => p[0] + " " + p[1]).join("L") + "Z";
}
function geomPath(mp) {
  return mp.coordinates.map((poly) => poly.map(ringPath).join("")).join("");
}
const mergeTo = (geoms) => geomPath(merge(topo, geoms));

const antarcticaId = topo.objects.countries.geometries.find((g) => g.properties.name === "Antarctica")?.id;
const landGeoms = topo.objects.countries.geometries.filter((g) => g.id !== antarcticaId);
const LAND = mergeTo(landGeoms);
const REGIONS = Object.fromEntries(Object.entries(byColor).map(([k, g]) => [k, mergeTo(g)]));

const out =
  "// GENERATED by scripts/gen-map.mjs (npm run gen:map). Natural Earth 110m via world-atlas (public domain). Do not edit.\n" +
  `export const LAND = ${JSON.stringify(LAND)};\n` +
  `export const REGIONS: Record<"blue" | "yellow" | "black" | "red", string> = ${JSON.stringify(REGIONS)};\n`;
writeFileSync(new URL("src/data/mapPaths.ts", root), out);

console.log("Assignment (override table):");
for (const [k, v] of Object.entries(OVERRIDE)) if (assign[k]) console.log(`  ${k} -> ${v}`);
console.log("Assignment (nearest city):\n  " + auto.join("\n  "));
for (const [k, g] of Object.entries(byColor)) console.log(`${k}: ${g.length} countries`);
console.log(`wrote mapPaths.ts: ${(out.length / 1024).toFixed(1)} KB`);
