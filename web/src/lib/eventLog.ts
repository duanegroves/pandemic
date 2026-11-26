import type { GameEvent } from "../types";
import { METHOD_LABEL } from "./actions";

export type Tone = "info" | "bad" | "good" | "warn" | "turn";
export interface LogEntry {
  id: number;
  text: string;
  tone: Tone;
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
    if (f) out.push({ id: startId + out.length, ...f });
  }
  return out;
}
