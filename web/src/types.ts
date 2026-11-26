export type Color = "blue" | "yellow" | "black" | "red";
export const COLORS: Color[] = ["blue", "yellow", "black", "red"];

/** Engine action JSON. Always has `type`; other fields depend on the type (see ENGINE_API.md). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Action = { type: string; [k: string]: any };

export interface GameEvent {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [k: string]: any;
}

export interface PlayerObs {
  index: number;
  role: string;
  location: string;
  hand: string[] | null;
  hand_size: number;
  stored_event: string | null;
  ops_move_used: boolean;
}

export interface Decision {
  kind: string;
  player: number | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  context: Record<string, any>;
}

export interface Observation {
  viewer: number | null;
  config: {
    num_players: number;
    difficulty: string;
    roles: string[] | null;
    open_hands: boolean | null;
    auto_consent: boolean;
    event_windows: string;
    open_hands_effective: boolean;
  };
  turn: number;
  current_player: number;
  phase: string;
  actions_remaining: number;
  decision: Decision;
  cubes: Record<string, Partial<Record<Color, number>>>;
  supply: Record<Color, number>;
  cures: Record<Color, "none" | "cured" | "eradicated">;
  research_stations: string[];
  outbreaks: number;
  infection_rate_index: number;
  infection_rate: number;
  one_quiet_night: boolean;
  players: PlayerObs[];
  player_deck: {
    size: number;
    piles: { size: number; epidemic_remaining: boolean }[];
    epidemics_remaining: number;
  };
  player_discard: string[];
  player_removed: string[];
  infection_deck: {
    size: number;
    known_top: string[][];
    forecast: null | { cards_above: number; order: string[] };
  };
  infection_discard: string[];
  infection_removed: string[];
  game_over: boolean;
  outcome: Outcome | null;
}

export interface Outcome {
  result: "win" | "loss";
  reason: string;
}

export interface StateMsg {
  type: "state";
  you: number;
  phase: "playing" | "over";
  observation: Observation;
  decision: Decision;
  legal_actions: Action[];
  events: GameEvent[];
  deadline_in: number | null;
  outcome: Outcome | null;
}

export interface Seat {
  seat: number;
  name: string;
  ready: boolean;
  connected: boolean;
  host: boolean;
}

export interface LobbyMsg {
  type: "lobby";
  room_id: string;
  phase: "lobby" | "playing" | "over";
  config: Record<string, unknown>;
  timeout: number | null;
  capacity: number;
  seats: Seat[];
  you: number;
}

export interface ChatMsg {
  type: "chat";
  seat: number;
  name: string;
  text: string;
}

export interface CityMeta {
  name: string;
  color: Color;
  population: number;
  neighbors: string[];
}

export interface Meta {
  cities: CityMeta[];
  roles: string[];
  events: string[];
}
