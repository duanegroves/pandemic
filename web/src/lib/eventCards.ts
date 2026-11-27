/**
 * Plain-language explanations of the Event cards, shown in the players panel, the
 * "play an event or pass" prompt, and as tooltips on event card chips.
 */

/** What every Event card has in common. */
export const EVENT_RULES =
  "Event cards are free: playing one doesn't use an action, and anyone can play theirs at any time, even on another player's turn.";

export const EVENT_INFO: Record<string, string> = {
  Airlift: "Move any 1 pawn to any city. Moving another player's pawn needs their permission.",
  "One Quiet Night": "Skip the next Infect Cities step: no infection cards are flipped.",
  "Resilient Population":
    "Remove 1 card in the infection discard pile from the game, so that city won't be infected by it again. Can be played during an epidemic, before the discard pile is shuffled back on top.",
  "Government Grant":
    "Build a research station in any city, without discarding a City card. If all 6 are built, move one.",
  Forecast:
    "Look at the top 6 cards of the infection deck and put them back in any order you choose.",
};

/** Description for a card, or undefined if it isn't an Event card. */
export function eventInfo(card: string): string | undefined {
  return EVENT_INFO[card];
}
