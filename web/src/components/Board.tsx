import { type ReactNode, useMemo, useState } from "react";
import { LAND, REGIONS } from "../data/mapPaths";
import { MAP_H, MAP_W, cityPos, edgeSegments, project } from "../lib/geo";
import { DISEASE_FILL, ROLE_STYLE } from "../lib/theme";
import { useMeta } from "../meta";
import { COLORS, type Color, type Observation } from "../types";

interface Props {
  obs: Observation;
  you: number;
  names: string[];
  targets: Set<string>;
  selected: string | null;
  onCity: (city: string, anchor: { x: number; y: number }) => void;
  overlay?: ReactNode;
}

const graticule = (() => {
  const lines: { d: string; k: string }[] = [];
  for (let lon = -120; lon <= 150; lon += 30) {
    const a = project(66, lon);
    const b = project(-42, lon);
    lines.push({ k: "lon" + lon, d: `M${a.x},${a.y}L${b.x},${b.y}` });
  }
  for (let lat = -30; lat <= 60; lat += 30) {
    const a = project(lat, -135);
    const b = project(lat, 165);
    lines.push({ k: "lat" + lat, d: `M${a.x},${a.y}L${b.x},${b.y}` });
  }
  return lines;
})();

export function Board({ obs, you, names, targets, selected, onCity, overlay }: Props) {
  const meta = useMeta();
  const [hover, setHover] = useState<string | null>(null);

  const edges = useMemo(() => {
    const seen = new Set<string>();
    const out: { a: string; b: string; segs: ReturnType<typeof edgeSegments> }[] = [];
    for (const c of meta.cities)
      for (const n of c.neighbors) {
        const k = [c.name, n].sort().join("|");
        if (seen.has(k)) continue;
        seen.add(k);
        out.push({ a: c.name, b: n, segs: edgeSegments(c.name, n) });
      }
    return out;
  }, [meta]);

  const pawnsAt = useMemo(() => {
    const m = new Map<string, typeof obs.players>();
    for (const p of obs.players) m.set(p.location, [...(m.get(p.location) ?? []), p]);
    return m;
  }, [obs.players]);
  const stations = useMemo(() => new Set(obs.research_stations), [obs.research_stations]);
  const hoverNeighbors = useMemo(
    () => new Set(hover ? (meta.cities.find((c) => c.name === hover)?.neighbors ?? []) : []),
    [hover, meta],
  );

  return (
    <div className="board-wrap">
      <svg className="board" viewBox={`0 0 ${MAP_W} ${MAP_H}`} role="img" aria-label="World map">
        <rect width={MAP_W} height={MAP_H} className="ocean" />
        <g className="map-bg" aria-hidden="true">
          {COLORS.map((k) => (
            <path key={k} d={REGIONS[k]} className={"region " + k} />
          ))}
          <path d={LAND} className="land" />
        </g>
        {graticule.map((g) => (
          <path key={g.k} d={g.d} className="grat" />
        ))}
        <g className="edges">
          {edges.map((e) => {
            const hot = hover !== null && (e.a === hover || e.b === hover);
            return e.segs.map((s, i) => (
              <line
                key={e.a + e.b + i}
                x1={s.x1}
                y1={s.y1}
                x2={s.x2}
                y2={s.y2}
                className={"edge" + (e.segs.length > 1 ? " wrap" : "") + (hot ? " hot" : "")}
              />
            ));
          })}
        </g>
        {meta.cities.map((c) => {
          const { x, y } = cityPos(c.name);
          const cubes = COLORS.filter((k) => (obs.cubes[c.name]?.[k] ?? 0) > 0).map((k) => ({
            k,
            n: obs.cubes[c.name]![k]!,
          }));
          const pawns = pawnsAt.get(c.name) ?? [];
          const isTarget = targets.has(c.name);
          const cls =
            "city" +
            (isTarget ? " target" : "") +
            (selected === c.name ? " selected" : "") +
            (hover === c.name ? " hover" : hoverNeighbors.has(c.name) ? " neighbor" : "");
          return (
            <g
              key={c.name}
              className={cls}
              transform={`translate(${x},${y})`}
              onMouseEnter={() => setHover(c.name)}
              onMouseLeave={() => setHover((h) => (h === c.name ? null : h))}
              onClick={(e) => {
                e.stopPropagation();
                onCity(c.name, { x, y });
              }}
            >
              <title>
                {c.name} ({c.color}, pop. {c.population.toLocaleString()})
                {cubes.map((q) => `, ${q.n} ${q.k}`).join("")}
              </title>
              <circle r={19} className="hit" />
              {isTarget && <circle r={17} className="target-ring" />}
              <circle r={11} fill={DISEASE_FILL[c.color]} className="node" />
              {stations.has(c.name) && <Station />}
              <CubeRow cubes={cubes} />
              {pawns.map((p, i) => (
                <Pawn
                  key={p.index}
                  role={p.role}
                  slot={i}
                  current={p.index === obs.current_player}
                  you={p.index === you}
                  title={`${names[p.index] ?? "Player " + (p.index + 1)}`}
                />
              ))}
              <text y={28} className="label">
                {c.name}
              </text>
            </g>
          );
        })}
      </svg>
      {overlay}
    </div>
  );
}

function CubeRow({ cubes }: { cubes: { k: Color; n: number }[] }) {
  if (!cubes.length) return null;
  const w = 13;
  const x0 = (-cubes.length * w) / 2;
  return (
    <g className="cubes" transform="translate(0,-28)">
      {cubes.map((q, i) => (
        <g key={q.k} transform={`translate(${x0 + i * w + w / 2},0)`}>
          <rect x={-6} y={-6} width={12} height={12} rx={2} fill={DISEASE_FILL[q.k]} className="cube" />
          <text className="cube-n" fill={q.k === "yellow" ? "#222" : "#fff"} y={0.5}>
            {q.n}
          </text>
        </g>
      ))}
    </g>
  );
}

function Station() {
  return (
    <polygon
      className="station"
      transform="translate(17,-11)"
      points="0,-7 7,-1.5 7,6 -7,6 -7,-1.5"
    />
  );
}

const SLOTS = [18, -18, 32, -32];
function Pawn({
  role,
  slot,
  current,
  you,
  title,
}: {
  role: string;
  slot: number;
  current: boolean;
  you: boolean;
  title: string;
}) {
  const st = ROLE_STYLE[role] ?? { fill: "#ccc", text: "#000", initials: "?" };
  return (
    <g transform={`translate(${SLOTS[slot % 4]},2)`} className={"pawn" + (current ? " current" : "")}>
      <title>{title}</title>
      <circle r={8} fill={st.fill} className={you ? "pawn-you" : ""} />
      <text fill={st.text} y={0.5} className="pawn-t">
        {st.initials}
      </text>
    </g>
  );
}
