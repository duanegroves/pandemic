import type { Color, GameEvent } from "../types";
import { METHOD_LABEL } from "./actions";

export type Tone = "info" | "bad" | "good" | "warn" | "turn";

/** Facts a turn summary is built from (cards drawn, infections, epidemics, outbreaks, cures). */
export type Fact =
  | { k: "drew"; player: number; cards: string[] }
  | { k: "infected"; city: string; color: Color; count: number; source: string }
  | { k: "epidemic"; city: string }
  | { k: "outbreak"; city: string; color: Color }
  | { k: "cure"; color: Color }
  | { k: "game_over"; win: boolean };

export interface LogEntry {
  id: number;
  text: string;
  tone: Tone;
  /** Seat of the player who did it: the bar is drawn in their pawn colour. */
  actor?: number;
  /** Disease the line is about, for things the board did: drawn as a small cube. */
  disease?: Color;
  /** alert = epidemic/outbreak/loss, milestone = cure/eradication/win; routine lines have none. */
  emphasis?: "alert" | "milestone";
  /** Present but not shown in the detail list (redundant with another line). */
  quiet?: boolean;
  /** Set on turn headers. */
  turn?: { n: number; player: number };
  fact?: Fact;
}

type Meta = Omit<LogEntry, "id" | "text" | "tone">;

/** Who/what each event is about, for colouring and turn summaries. */
export function describeEvent(e: GameEvent): Meta {
  switch (e.type) {
    case "turn_started":
      return { turn: { n: e.turn, player: e.player }, actor: e.player };
    case "cubes_placed":
      return e.source === "setup"
        ? { disease: e.color }
        : {
            disease: e.color,
            fact: { k: "infected", city: e.city, color: e.color, count: e.count, source: e.source },
          };
    case "cubes_removed":
      return e.player != null ? { actor: e.player } : { disease: e.color };
    case "placement_prevented":
    case "infection_card_removed":
      return { disease: e.color };
    case "outbreak":
      return { disease: e.color, emphasis: "alert", fact: { k: "outbreak", city: e.city, color: e.color } };
    case "infection_card_drawn":
      // The cubes_placed / placement_prevented line that follows says the same thing.
      return e.source === "epidemic"
        ? { quiet: true, fact: { k: "epidemic", city: e.card } }
        : { quiet: true };
    case "epidemic":
      return { emphasis: "alert" };
    case "player_cards_drawn":
      return {
        actor: e.player,
        fact: { k: "drew", player: e.player, cards: (e.cards as (string | null)[]).map((x) => x ?? "a card") },
      };
    case "pawn_moved":
      return { actor: e.by_player };
    case "card_transferred":
      return { actor: e.from_player };
    case "consent_requested":
      return { actor: e.requester };
    case "cure_discovered":
      return { actor: e.player, emphasis: "milestone", fact: { k: "cure", color: e.color } };
    case "disease_eradicated":
      return { disease: e.color, emphasis: "milestone" };
    case "actions_ended":
      return { actor: e.player, quiet: true };
    case "game_over":
      return {
        emphasis: e.result === "win" ? "milestone" : "alert",
        fact: { k: "game_over", win: e.result === "win" },
      };
    case "intensify":
    case "infections_skipped":
      return {};
    default:
      return typeof e.player === "number" ? { actor: e.player } : {};
  }
}

/** A turn (or the setup) with its log lines and a catch-up summary. */
export interface LogSection {
  key: string;
  turn?: { n: number; player: number };
  entries: LogEntry[];
  summary: {
    drew: { player: number; cards: string[] }[];
    /** city -> cubes added this turn (infections, epidemics and outbreak spread) */
    infected: { city: string; color: Color; count: number }[];
    epidemics: string[];
    outbreaks: { city: string; color: Color }[];
    cures: Color[];
    gameOver?: { win: boolean };
  };
}

/** Group a chronological log into sections, one per turn, each with a summary. */
export function groupLog(log: LogEntry[]): LogSection[] {
  const out: LogSection[] = [];
  const start = (key: string, turn?: LogSection["turn"]): LogSection => {
    const s: LogSection = {
      key,
      turn,
      entries: [],
      summary: { drew: [], infected: [], epidemics: [], outbreaks: [], cures: [] },
    };
    out.push(s);
    return s;
  };
  let cur: LogSection | null = null;
  for (const e of log) {
    if (e.turn) {
      cur = start(`t${e.turn.n}-${e.id}`, e.turn);
      continue; // the header itself is the section title
    }
    if (!cur) cur = start("setup");
    // The engine doesn't announce turn 1, so the section before the first header holds the
    // setup and turn 1: name it after the first player who acted in it.
    if (!cur.turn && e.actor != null && !out.some((x) => x.turn)) cur.turn = { n: 1, player: e.actor };
    cur.entries.push(e);
    const f = e.fact;
    const s = cur.summary;
    if (!f) continue;
    if (f.k === "drew") s.drew.push({ player: f.player, cards: f.cards.filter((c) => c !== "Epidemic") });
    else if (f.k === "infected") {
      const prev = s.infected.find((x) => x.city === f.city && x.color === f.color);
      if (prev) prev.count += f.count;
      else s.infected.push({ city: f.city, color: f.color, count: f.count });
    } else if (f.k === "epidemic") s.epidemics.push(f.city);
    else if (f.k === "outbreak") s.outbreaks.push({ city: f.city, color: f.color });
    else if (f.k === "cure") s.cures.push(f.color);
    else if (f.k === "game_over") s.gameOver = { win: f.win };
  }
  return out;
}

export interface LogCtx {
  /** Display name for a seat, e.g. "Alice". */
  name(seat: number): string;
  you: number | null;
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** Turn one engine event into a human-readable log line (null = not worth logging). */
export function formatEvent(e: GameEvent, c: LogCtx): { text: string; tone: Tone } | null {
  const who = (s: number) => (s === c.you ? "You" : c.name(s));
  switch (e.type) {
    case "turn_started":
      return { text: `Turn ${e.turn}: ${c.name(e.player)}'s turn`, tone: "turn" };
    case "cubes_placed": {
      const src: Record<string, string> = {
        setup: "Setup",
        infection: "Infection",
        epidemic: "Epidemic",
        outbreak: "Outbreak spread",
      };
      return {
        text: `${src[e.source] ?? e.source}: ${plural(e.count, e.color + " cube")} on ${e.city}`,
        tone: e.source === "setup" ? "info" : "bad",
      };
    }
    case "cubes_removed":
      return {
        text: `${e.player != null ? who(e.player) + " treated" : "Removed"} ${plural(e.count, e.color + " cube")} in ${e.city}${e.reason === "medic" ? " (Medic)" : ""}`,
        tone: "good",
      };
    case "placement_prevented": {
      const why: Record<string, string> = {
        eradicated: "the disease is eradicated",
        medic: "the Medic is there",
        quarantine_specialist: "the Quarantine Specialist protects it",
      };
      return {
        text: `No ${e.color} cube placed on ${e.city}: ${why[e.reason] ?? e.reason}`,
        tone: "good",
      };
    }
    case "outbreak":
      return {
        text: `OUTBREAK in ${e.city} (${e.color})! Outbreaks: ${e.total}`,
        tone: "bad",
      };
    case "infection_card_drawn":
      return {
        text: `${e.source === "epidemic" ? "Epidemic infects" : "Infection card"}: ${e.card}`,
        tone: e.source === "epidemic" ? "bad" : "warn",
      };
    case "epidemic":
      return {
        text: `EPIDEMIC drawn by ${c.name(e.player)}! Infection rate is now ${e.infection_rate}`,
        tone: "bad",
      };
    case "intensify":
      return { text: "Intensify: infection discard shuffled onto the deck", tone: "bad" };
    case "player_cards_drawn": {
      const cards = (e.cards as (string | null)[]).map((x) => x ?? "a card");
      return { text: `${who(e.player)} drew ${cards.join(", ")}`, tone: "info" };
    }
    case "pawn_moved": {
      const how = METHOD_LABEL[e.method] ?? e.method;
      const by = e.by_player !== e.pawn ? ` (by ${who(e.by_player)})` : "";
      return {
        text: `${who(e.pawn)} ${how} from ${e.from_city} to ${e.to_city}${by}`.replace(
          /^You was /,
          "You were ",
        ),
        tone: "info",
      };
    }
    case "station_built":
      return {
        text: `${who(e.player)} built a research station in ${e.city}${e.relocated_from ? ` (moved from ${e.relocated_from})` : ""}`,
        tone: "good",
      };
    case "card_discarded":
      return {
        text: `${who(e.player)} discarded ${e.card}${e.reason === "hand_limit" ? " (hand limit)" : ""}`,
        tone: "info",
      };
    case "card_transferred":
      return {
        text: `${who(e.from_player)} gave ${e.card} to ${who(e.to_player)}`,
        tone: "info",
      };
    case "cure_discovered":
      return { text: `${who(e.player)} discovered the ${e.color} cure!`, tone: "good" };
    case "disease_eradicated":
      return { text: `The ${e.color} disease is ERADICATED`, tone: "good" };
    case "event_played":
      return {
        text: `${who(e.player)} played ${e.card}${e.from_stored ? " (stored)" : ""}`,
        tone: "good",
      };
    case "event_stored":
      return { text: `${who(e.player)} stored event card ${e.card}`, tone: "info" };
    case "infection_card_removed":
      return { text: `${e.card} removed from the game`, tone: "info" };
    case "infections_skipped":
      return { text: "One Quiet Night: infection step skipped", tone: "good" };
    case "forecast_arranged":
      return {
        text: `${who(e.player)} rearranged the top of the infection deck`,
        tone: "info",
      };
    case "consent_requested":
      return {
        text: `${c.name(e.requester)} asked ${c.name(e.player)} for consent`,
        tone: "info",
      };
    case "consent_given":
      return {
        text: `${c.name(e.player)} ${e.accepted ? "accepted" : "declined"}`,
        tone: e.accepted ? "info" : "warn",
      };
    case "actions_ended":
      return { text: `${who(e.player)} ended their actions`, tone: "info" };
    case "game_over":
      return {
        text: `GAME OVER: ${e.result === "win" ? "victory" : "defeat"} (${String(e.reason).replace(/_/g, " ")})`,
        tone: e.result === "win" ? "good" : "bad",
      };
    default:
      return null;
  }
}

export function formatEvents(events: GameEvent[], c: LogCtx, startId = 0): LogEntry[] {
  const out: LogEntry[] = [];
  for (const e of events) {
    const f = formatEvent(e, c);
    if (f) out.push({ id: startId + out.length, ...f, ...describeEvent(e) });
  }
  return out;
}
