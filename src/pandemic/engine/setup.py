"""Game setup exactly as in the rulebook."""

from __future__ import annotations

import random

from pandemic.data.cards import EPIDEMIC, STARTING_HAND_SIZE
from pandemic.data.cities import CITIES, CITY_INDEX, CITY_NAMES
from pandemic.engine.config import ROLES, GameConfig
from pandemic.engine.infection import place_cubes
from pandemic.engine.state import CITY_COLOR, EVENT_NAMES, GameState, PlayerState, is_city_card


def first_player(hands: list[list[str]]) -> int:
    """Seat holding the highest-population city card. Ties (impossible with the shipped
    data) break toward the lower CITY_INDEX card; event cards have no population."""
    best: tuple[int, int] | None = None
    best_seat = 0
    for seat, hand in enumerate(hands):
        for card in hand:
            if not is_city_card(card):
                continue
            key = (CITIES[card].population, -CITY_INDEX[card])
            if best is None or key > best:
                best, best_seat = key, seat
    return best_seat


def pile_sizes(n_cards: int, n_piles: int) -> list[int]:
    """Near-equal pile sizes (excluding the epidemic), larger piles first (= on top)."""
    base, extra = divmod(n_cards, n_piles)
    return [base + 1 if i < extra else base for i in range(n_piles)]


def new_game(config: GameConfig | None = None, seed: int = 0) -> GameState:
    from pandemic.engine.step import advance  # local import to avoid a cycle

    config = config or GameConfig()
    rng = random.Random(seed)

    # Roles (pawns start in Atlanta).
    roles = list(config.roles) if config.roles is not None else rng.sample(ROLES,
                                                                           config.num_players)
    state = GameState(config=config, rng=rng, players=[PlayerState(r) for r in roles])

    # Infect 9 cities: 3x3, 3x2, 3x1.
    deck = list(CITY_NAMES)
    rng.shuffle(deck)
    events: list = []
    for count in (3, 2, 1):
        for _ in range(3):
            card = deck.pop(0)
            place_cubes(state, card, CITY_COLOR[card], count, "setup", events, setup=True)
            state.infection_discard.append(card)
    state.infection_deck = deck

    # Deal hands from shuffled city + event cards.
    pdeck = list(CITY_NAMES) + list(EVENT_NAMES)
    rng.shuffle(pdeck)
    hand_size = STARTING_HAND_SIZE[config.num_players]
    for p in state.players:
        p.hand = pdeck[:hand_size]
        del pdeck[:hand_size]

    # Epidemic piles, smaller piles at the bottom.
    sizes = pile_sizes(len(pdeck), config.num_epidemics)
    final: list[str] = []
    piles: list[list] = []
    pos = 0
    for size in sizes:
        pile = pdeck[pos:pos + size] + [EPIDEMIC]
        pos += size
        rng.shuffle(pile)
        final.extend(pile)
        piles.append([size + 1, True])
    state.player_deck = final
    state.player_deck_piles = piles

    state.current_player = first_player([p.hand for p in state.players])
    advance(state, [])
    return state
