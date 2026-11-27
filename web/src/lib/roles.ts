/**
 * Plain-language explanations of each role's special abilities, shown in the players panel.
 * Wording follows the rulebook's Roles section and how the engine applies it.
 */
export interface RoleInfo {
  /** One-line gist. */
  summary: string;
  /** The abilities, one per bullet. */
  abilities: string[];
}

export const ROLE_INFO: Record<string, RoleInfo> = {
  contingency_planner: {
    summary: "Keeps a used Event card ready to play again.",
    abilities: [
      "As an action, take any Event card from the player discard pile and store it on your role card.",
      "You can store only 1 Event at a time, and it doesn't count toward your hand limit.",
      "When you play the stored Event, it's removed from the game instead of discarded.",
    ],
  },
  dispatcher: {
    summary: "Moves other players' pawns around the board.",
    abilities: [
      "As an action, move any pawn to a city that already has another pawn in it.",
      "As an action, move another player's pawn as if it were your own (drive, direct, charter or shuttle flight), paying with cards from your hand. A charter flight needs the card of the city that pawn is leaving.",
      "Moving another player's pawn needs their permission (when the game asks for consent).",
    ],
  },
  medic: {
    summary: "Clears whole cities and protects them once a disease is cured.",
    abilities: [
      "Treat Disease removes all cubes of one colour, not just 1.",
      "Once a disease is cured, its cubes are removed automatically from any city you're in or move into (no action needed, even on other players' turns).",
      "Cubes of a cured disease can't be placed in your city.",
    ],
  },
  operations_expert: {
    summary: "Builds research stations easily and jumps between them.",
    abilities: [
      "As an action, build a research station in your city without discarding a card.",
      "Once per turn, as an action, move from a research station to any city by discarding any City card.",
    ],
  },
  quarantine_specialist: {
    summary: "Shields the cities around her from infection.",
    abilities: [
      "No disease cubes are placed, and no outbreaks happen, in your city and every city connected to it.",
      "This doesn't affect the cubes placed during setup.",
    ],
  },
  researcher: {
    summary: "Shares any city card, making cures much easier to collect.",
    abilities: [
      "When sharing knowledge, you can give any City card, not just the one for the city you're in.",
      "Another player in your city can take any City card from you, on their turn or yours.",
    ],
  },
  scientist: {
    summary: "Discovers cures with fewer cards.",
    abilities: ["Needs only 4 City cards of the same colour (instead of 5) to discover a cure."],
  },
};
