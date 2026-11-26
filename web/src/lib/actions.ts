import type { Action } from "../types";

/** Turn-action types that move a pawn to a destination city. */
export const MOVE_TYPES = [
  "drive_ferry",
  "direct_flight",
  "charter_flight",
  "shuttle_flight",
  "dispatcher_move",
  "operations_move",
  "play_airlift",
];

const EVENT_BY_TYPE: Record<string, string> = {
  play_airlift: "Airlift",
  play_one_quiet_night: "One Quiet Night",
  play_resilient_population: "Resilient Population",
  play_government_grant: "Government Grant",
  play_forecast: "Forecast",
};

export function eventCardOf(a: Action): string | null {
  return EVENT_BY_TYPE[a.type] ?? null;
}

/** The city an action targets on the map, if any (moves and Government Grant). */
export function targetCity(a: Action): string | null {
  if (MOVE_TYPES.includes(a.type)) return a.destination ?? null;
  if (a.type === "play_government_grant") return a.city ?? null;
  return null;
}

export interface Grouped {
  /** Actions keyed by the map city they target. */
  byCity: Map<string, Action[]>;
  treat: Action[];
  build: Action[];
  give: Action[];
  take: Action[];
  cure: Action[];
  takeEvent: Action[];
  /** Event plays keyed by card name. */
  events: Map<string, Action[]>;
  end: Action | null;
  pass: Action | null;
  discards: Action[];
  consent: Action[];
  forecast: Action[];
  /** Anything not covered above. */
  other: Action[];
}

export function groupActions(legal: Action[]): Grouped {
  const g: Grouped = {
    byCity: new Map(),
    treat: [],
    build: [],
    give: [],
    take: [],
    cure: [],
    takeEvent: [],
    events: new Map(),
    end: null,
    pass: null,
    discards: [],
    consent: [],
    forecast: [],
    other: [],
  };
  const push = <K>(m: Map<K, Action[]>, k: K, a: Action) => {
    const l = m.get(k);
    if (l) l.push(a);
    else m.set(k, [a]);
  };
  for (const a of legal) {
    const city = targetCity(a);
    if (city) push(g.byCity, city, a);
    const ev = eventCardOf(a);
    if (ev) {
      push(g.events, ev, a);
      continue;
    }
    if (city) continue;
    switch (a.type) {
      case "treat_disease":
        g.treat.push(a);
        break;
      case "build_research_station":
        g.build.push(a);
        break;
      case "give_card":
        g.give.push(a);
        break;
      case "take_card":
        g.take.push(a);
        break;
      case "discover_cure":
        g.cure.push(a);
        break;
      case "take_event_card":
        g.takeEvent.push(a);
        break;
      case "end_actions":
        g.end = a;
        break;
      case "pass":
        g.pass = a;
        break;
      case "discard":
        g.discards.push(a);
        break;
      case "consent":
        g.consent.push(a);
        break;
      case "forecast_order":
        g.forecast.push(a);
        break;
      default:
        g.other.push(a);
    }
  }
  return g;
}

/** Cities that are the destination of some legal move (or grant). */
export function moveTargets(legal: Action[]): Set<string> {
  const s = new Set<string>();
  for (const a of legal) {
    const c = targetCity(a);
    if (c) s.add(c);
  }
  return s;
}

export function sameAction(a: Action, b: Action): boolean {
  return JSON.stringify(canon(a)) === JSON.stringify(canon(b));
}

function canon(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === "object") {
    return Object.fromEntries(
      Object.entries(v as Record<string, unknown>)
        .sort(([x], [y]) => (x < y ? -1 : 1))
        .map(([k, x]) => [k, canon(x)]),
    );
  }
  return v;
}

/** Build a ForecastOrder action for the chosen order, or null when the server did not offer it. */
export function buildForecastAction(order: string[], legal: Action[]): Action | null {
  const a: Action = { type: "forecast_order", order };
  return legal.find((l) => sameAction(l, a)) ?? null;
}

/** Group discover_cure actions by color. */
export function cureByColor(cures: Action[]): Map<string, Action[]> {
  const m = new Map<string, Action[]>();
  for (const a of cures) {
    const l = m.get(a.color);
    if (l) l.push(a);
    else m.set(a.color, [a]);
  }
  return m;
}

/** Treat actions keyed by color (at most one each). */
export function treatByColor(treat: Action[]): Map<string, Action> {
  return new Map(treat.map((a) => [a.color as string, a]));
}

// ---- narrowing: pick one action out of several by choosing parameter values step by step ----

const vkey = (v: unknown) => JSON.stringify(v ?? null);

export interface Choice {
  key: string;
  options: { id: string; value: unknown }[];
}

/**
 * Given candidate actions and an ordered list of parameter keys, return either the next parameter the
 * user must choose (with the distinct values still possible), or the single remaining action.
 * `chosen` maps key -> vkey(value) for the choices made so far. Keys with only one possible value are
 * skipped automatically.
 */
export function narrow(
  actions: Action[],
  keys: string[],
  chosen: Record<string, string>,
): { choice: Choice } | { done: Action } | { none: true } {
  const rem = actions.filter((a) => keys.every((k) => !(k in chosen) || vkey(a[k]) === chosen[k]));
  if (rem.length === 0) return { none: true };
  for (const k of keys) {
    if (k in chosen) continue;
    const ids: string[] = [];
    for (const a of rem) {
      const id = vkey(a[k]);
      if (!ids.includes(id)) ids.push(id);
    }
    if (ids.length > 1) {
      return { choice: { key: k, options: ids.map((id) => ({ id, value: JSON.parse(id) })) } };
    }
  }
  return { done: rem[0] };
}

/** The parameter keys, in asking order, for each event card. */
export const EVENT_KEYS: Record<string, string[]> = {
  Airlift: ["pawn", "destination"],
  "Government Grant": ["city", "relocate_from"],
  "Resilient Population": ["card"],
  "One Quiet Night": [],
  Forecast: [],
};

// ---- labelling ----

export const ROLE_LABEL: Record<string, string> = {
  contingency_planner: "Contingency Planner",
  dispatcher: "Dispatcher",
  medic: "Medic",
  operations_expert: "Operations Expert",
  quarantine_specialist: "Quarantine Specialist",
  researcher: "Researcher",
  scientist: "Scientist",
};

export const METHOD_LABEL: Record<string, string> = {
  drive_ferry: "drove",
  direct_flight: "flew direct",
  charter_flight: "chartered a flight",
  shuttle_flight: "took a shuttle",
  dispatcher_move: "was dispatched",
  operations_move: "made an operations move",
  play_airlift: "was airlifted",
};

export interface Labeler {
  /** "Alice (Medic)" style label for a seat. */
  player(seat: number): string;
  you: number | null;
}

/** Human-readable one-line description of an action. */
export function describeAction(a: Action, L: Labeler): string {
  const who = (seat: number) => (seat === L.you ? "yourself" : L.player(seat));
  const pawnPrefix = (pawn: number) => (pawn === L.you ? "" : `Move ${L.player(pawn)}: `);
  switch (a.type) {
    case "drive_ferry":
      return `${pawnPrefix(a.pawn)}Drive/ferry to ${a.destination}`;
    case "direct_flight":
      return `${pawnPrefix(a.pawn)}Direct flight to ${a.destination} (discard ${a.destination})`;
    case "charter_flight":
      return `${pawnPrefix(a.pawn)}Charter flight to ${a.destination} (discard current city card)`;
    case "shuttle_flight":
      return `${pawnPrefix(a.pawn)}Shuttle to ${a.destination}`;
    case "dispatcher_move":
      return `Dispatch ${a.pawn === L.you ? "your pawn" : L.player(a.pawn)} to ${a.destination}`;
    case "operations_move":
      return `Operations move to ${a.destination} (discard ${a.card})`;
    case "build_research_station":
      return a.relocate_from
        ? `Build research station (relocate from ${a.relocate_from})`
        : "Build research station";
    case "treat_disease":
      return `Treat ${a.color}`;
    case "give_card":
      return `Give ${a.card} to ${L.player(a.to_player)}`;
    case "take_card":
      return `Take ${a.card} from ${L.player(a.from_player)}`;
    case "discover_cure":
      return `Discover ${a.color} cure (${(a.cards as string[]).join(", ")})`;
    case "take_event_card":
      return `Take event card ${a.card} from discard`;
    case "end_actions":
      return "End actions";
    case "discard":
      return `Discard ${a.card}`;
    case "pass":
      return "Pass";
    case "consent":
      return a.accept ? "Accept" : "Decline";
    case "forecast_order":
      return `Forecast order: ${(a.order as string[]).join(" > ")}`;
    case "play_airlift":
      return `Play Airlift: ${who(a.pawn)} to ${a.destination}`;
    case "play_one_quiet_night":
      return "Play One Quiet Night";
    case "play_resilient_population":
      return `Play Resilient Population: remove ${a.card}`;
    case "play_government_grant":
      return a.relocate_from
        ? `Play Government Grant: station in ${a.city} (relocate from ${a.relocate_from})`
        : `Play Government Grant: station in ${a.city}`;
    case "play_forecast":
      return "Play Forecast";
    default:
      return JSON.stringify(a);
  }
}

/** Describe a consent request (the `request` action from a consent decision's context). */
export function describeConsent(requester: number, request: Action, L: Labeler): string {
  const r = L.player(requester);
  switch (request.type) {
    case "give_card":
      return `${r} wants to give you ${request.card}.`;
    case "take_card":
      return `${r} wants to take ${request.card} from your hand.`;
    case "play_airlift":
      return `${r} wants to airlift your pawn to ${request.destination}.`;
    default:
      if (MOVE_TYPES.includes(request.type)) {
        return `${r} (Dispatcher) wants to move your pawn to ${request.destination} (${request.type.replace(/_/g, " ")}).`;
      }
      return `${r} requests: ${describeAction(request, L)}`;
  }
}
