# Pandemic Engine API (`pandemic.engine`)

The engine is a pure-Python, deterministic state machine. It does not depend on any UI, RL or
server code. Everything below is re-exported from `pandemic.engine`.

```python
from pandemic.engine import GameConfig, new_game, current_decision, legal_actions, step, observe

state = new_game(GameConfig(num_players=3, difficulty="standard"), seed=42)
while not is_over(state):
    d = current_decision(state)        # PendingDecision(kind, player, context)
    acts = legal_actions(state)        # list[Action] for d.player; never empty unless over
    state, events = step(state, acts[0])
print(outcome(state))                  # {"result": "win"|"loss", "reason": ...}
```

## Core functions

| Function | Description |
|---|---|
| `new_game(config: GameConfig, seed: int) -> GameState` | Full rulebook setup, then advances to the first decision. |
| `current_decision(state) -> PendingDecision` | Who must act now, the decision kind and its context. |
| `legal_actions(state) -> list[Action]` | Every legal action for the owner of the current decision. It is empty only when the game is over. The order is deterministic. |
| `step(state, action, validate=True) -> (GameState, list[GameEvent])` | **Mutates `state` in place** and returns the same object plus the domain events. Raises `IllegalActionError` if the game is over or the action is not in `legal_actions(state)`. Pass `validate=False` to skip the check (about 1.5x faster) when the action came from `legal_actions`. Use `state.clone()` to branch. |
| `observe(state, player_index: int \| None) -> dict` | JSON-serializable redacted view (`None` = spectator). |
| `redact_event(event, state, player_index) -> dict` | `event.to_dict()` with the information hidden from that player removed. |
| `is_over(state) -> bool`, `outcome(state) -> dict \| None` | Terminal check and result. |
| `state.clone()` | Fast deep copy, including the RNG. |
| `state.to_dict()` / `GameState.from_dict(d)` | Full JSON round-trip, including the RNG state. `state_to_json` / `state_from_json` wrap these as strings. |
| `action_to_dict(a)` / `action_from_dict(d)` | Action JSON. `action_from_dict` raises `IllegalActionError` on an unknown type or bad fields. |

**The actor is always the owner of the current decision.** Actions carry no "player" field.
A server must check that the sender is `current_decision(state).player` before calling `step`.

**Determinism:** all randomness comes from `state.rng` (`random.Random(seed)`). The same
`seed` plus the same action sequence gives an identical `to_dict()`. The RNG is used only during
setup and when shuffling for Intensify.

## GameConfig

| Field | Type / default | Meaning |
|---|---|---|
| `num_players` | `int = 2` | 2 to 4 |
| `difficulty` | `"introductory" \| "standard" \| "heroic"`, default `"standard"` | 4 / 5 / 6 epidemics |
| `roles` | `list[Role \| str] \| None = None` | One per seat, distinct. `None` deals random roles from the seed. |
| `open_hands` | `bool \| None = None` | `None` follows the rulebook: open for introductory, closed otherwise. `config.hands_open` gives the effective value. |
| `auto_consent` | `bool = True` | When False, a `consent` decision is created (see below). |
| `event_windows` | `"full" \| "checkpoints" \| "off"`, default `"checkpoints"` | See *Event windows*. |

`Role` values: `contingency_planner`, `dispatcher`, `medic`, `operations_expert`,
`quarantine_specialist`, `researcher`, `scientist`.

## Identifiers

- **Cities**: the exact names in `pandemic.data.cities.CITY_NAMES` (for example `"Montréal"`, `"Bogotá"`, `"São Paulo"`).
  Seats are `0..num_players-1`, and "left" is `seat+1`.
- **Colors**: `"blue" | "yellow" | "black" | "red"`. In Python, actions use the `Color` enum.
- **Player cards**: a city name, an event name (`"Airlift"`, `"One Quiet Night"`,
  `"Resilient Population"`, `"Government Grant"`, `"Forecast"`), or `"Epidemic"`.
- **Infection cards**: city names.
- **Cure status**: `"none" | "cured" | "eradicated"`.

## Decisions (`PendingDecision`)

`PendingDecision(kind: str, player: int | None, context: dict)`

| kind | owner | context | legal actions |
|---|---|---|---|
| `actions` | current player | `{"actions_remaining": n}` | turn actions, the player's own event plays (hand and stored), `EndActions` |
| `event_window` | a player holding a playable event | `{"checkpoint": str, "queue": [seats still to be asked]}` | event plays allowed at that checkpoint, plus `Pass` |
| `discard` | the player over the hand limit (may not be the current player) | `{"reason": "hand_limit", "limit": 7}` | `Discard(card)` for every card in hand, plus plays of event cards **from hand** |
| `consent` | the player whose permission is needed | `{"requester": seat, "request": <action dict>}` | `Consent(True)`, `Consent(False)` |
| `forecast_order` | whoever played Forecast | `{"cards": [up to 6 cards, top first]}` | `ForecastOrder(order)` for every permutation (up to 720) |
| `game_over` | `None` | `{"outcome": {...}}` | none |

Decisions nest. A `discard`, `consent` or `forecast_order` interrupts whatever was in
progress, and play then resumes where it left off. For example, the receiver discards in the
middle of the giver's actions, and the giver then continues.

### Turn flow and event windows

```
actions (4, or EndActions) -> [window before_draw] -> draw 2
  -> for each Epidemic: Increase+Infect -> [window epidemic_intensify] -> Intensify
       ([window between_epidemics] between two epidemics)
  -> hand limit (discard decisions) -> [window before_infection]
  -> start infections (One Quiet Night checked here) -> flip 1
     -> [window before_infection] -> flip 2 -> ... -> next player's turn
```

Checkpoints:

| checkpoint | allowed events |
|---|---|
| `actions` | all (`full` mode only, offered to the **other** players before each of the active player's actions) |
| `before_draw` | all |
| `epidemic_intensify` | Resilient Population only |
| `between_epidemics` | all |
| `before_infection` | all (before every infection flip) |

Modes:

- `"off"`: there are no windows. Events can be played only by the active player during their
  `actions` decision, and in a `discard` decision instead of discarding.
- `"checkpoints"`: windows open at the checkpoints above except `actions`. They are offered in
  turn order starting with the current player, and only to players who hold an event
  playable there.
- `"full"`: the same as `checkpoints`, plus an `actions` window for the other players before
  each action of the active player.

A window with no eligible player is skipped automatically. When a player plays an event in a
window, they keep the decision while they still hold a playable event. `Pass` moves to the
next eligible player in `queue`. A player whose events become unplayable is skipped
automatically.

### Consent (`auto_consent=False`)

These actions create a `consent` decision for the other player:

- `GiveCard` and `TakeCard`: the other player.
- Dispatcher moves of another pawn (`DriveFerry`, `DirectFlight`, `CharterFlight`, `ShuttleFlight` and `DispatcherMove` with `pawn != actor`): the pawn's owner.
- `PlayAirlift` with `pawn != actor`: the pawn's owner.

If consent is refused, nothing happens: no action point is spent, no card is used and the
requester decides again. Note that a requester can keep re-requesting.

## Actions

Every action is a frozen, hashable dataclass with a class attribute `type`. Its JSON form is
`{"type": ..., <fields>}`, where tuples become lists and colors become strings. The fields
listed are the JSON keys.

**Turn actions.** These cost 1 action and are available only in the `actions` decision:

| type | fields | notes |
|---|---|---|
| `drive_ferry` | `pawn`, `destination` | move to an adjacent city |
| `direct_flight` | `pawn`, `destination` | discard the destination card from the **actor's** hand |
| `charter_flight` | `pawn`, `destination` | discard the card of the **pawn's current** city from the actor's hand |
| `shuttle_flight` | `pawn`, `destination` | from a station to a station |
| `dispatcher_move` | `pawn`, `destination` | Dispatcher only: any pawn to a city containing another pawn |
| `operations_move` | `destination`, `card` | Operations Expert only: once per turn, from a station to any city, discarding any city card |
| `build_research_station` | `relocate_from: str \| null` | in the actor's city; discards that city card (the Operations Expert discards nothing); `relocate_from` is required if and only if 6 stations exist |
| `treat_disease` | `color` | removes 1 cube; removes all if the disease is cured or the actor is the Medic |
| `give_card` | `to_player`, `card` | the matching city card; the Researcher may give any city card |
| `take_card` | `from_player`, `card` | the matching city card, or any city card from the Researcher |
| `discover_cure` | `color`, `cards: [..]` | at any station; the exact cards (5, or 4 for the Scientist), sorted by `CITY_INDEX`; one action per combination |
| `take_event_card` | `card` | Contingency Planner only: store an event from the player discard pile (at most 1 stored) |

For `pawn`, ordinary players always use their own seat. The Dispatcher may use any seat, and
his Direct and Charter flights use the Dispatcher's cards.

**Free actions:**

| type | fields | when |
|---|---|---|
| `end_actions` | none | `actions`: forfeit the remaining actions |
| `discard` | `card` | `discard` |
| `pass` | none | `event_window` |
| `consent` | `accept: bool` | `consent` |
| `forecast_order` | `order: [cards]` | `forecast_order`; `order[0]` becomes the top card |

**Event plays.** These do not cost an action. The engine finds the card in the actor's hand
or in the Contingency Planner's stored slot. A stored card is removed from the game after
play; a card from the hand goes to the player discard pile.

| type | fields | effect |
|---|---|---|
| `play_airlift` | `pawn`, `destination` | move any pawn anywhere (the Medic auto-clears) |
| `play_one_quiet_night` | none | skip the next "start infections" step; not offered while already pending |
| `play_resilient_population` | `card` | remove an infection discard card from the game |
| `play_government_grant` | `city`, `relocate_from: str \| null` | build a station in any city without one; `relocate_from` is required if and only if 6 stations exist |
| `play_forecast` | none | opens a `forecast_order` decision for the actor with the top 6 cards (fewer if the deck is smaller) |

## Domain events

`step` returns a list of event dataclasses. Each has a class attribute `type`, and
`e.to_dict()` gives `{"type": ..., ...fields}`. `EVENT_TYPES` maps each type name to its
class.

| type | fields |
|---|---|
| `cubes_placed` | `city, color, count, source` (`setup\|infection\|epidemic\|outbreak`) |
| `cubes_removed` | `city, color, count, player, reason` (`treat\|medic`) |
| `placement_prevented` | `city, color, reason` (`eradicated\|medic\|quarantine_specialist`) |
| `outbreak` | `city, color, total` |
| `infection_card_drawn` | `card, source` (`infection\|epidemic`) |
| `epidemic` | `player, infection_rate_index, infection_rate` |
| `intensify` | `count` |
| `player_cards_drawn` | `player, cards` (**private**: see `redact_event`) |
| `pawn_moved` | `pawn, from_city, to_city, method, by_player` |
| `station_built` | `city, relocated_from, player` |
| `card_discarded` | `player, card, reason` (the action type or `hand_limit`) |
| `card_transferred` | `from_player, to_player, card` |
| `cure_discovered` | `color, player` |
| `disease_eradicated` | `color` |
| `event_played` | `player, card, from_stored` |
| `event_stored` | `player, card` |
| `infection_card_removed` | `card` |
| `infections_skipped` | none (One Quiet Night consumed) |
| `forecast_arranged` | `player, order` (**private** to `player`) |
| `consent_requested` | `player, requester, request` |
| `consent_given` | `player, accepted` |
| `actions_ended` | `player` |
| `turn_started` | `player, turn` |
| `game_over` | `result` (`win\|loss`), `reason` |

`redact_event` hides the cards in another player's `player_cards_drawn` when hands are closed.
Epidemic cards stay visible and the others become `null`. It also sets `order` to `null` in
another player's `forecast_arranged`.

## `observe(state, player_index)` schema

```jsonc
{
  "viewer": 0,
  "config": {"num_players", "difficulty", "roles", "open_hands", "auto_consent",
             "event_windows", "open_hands_effective"},
  "turn": 1, "current_player": 0,
  "phase": "actions" | "draw" | "infect" | "over",
  "actions_remaining": 4,
  "decision": {"kind": "...", "player": 0, "context": {...}},
      // forecast_order context for non-owners is {"num_cards": n};
      // event_window "queue" is removed (it would reveal who holds events)
  "cubes": {"Atlanta": {"blue": 2}, ...},          // only cities with cubes
  "supply": {"blue": 22, "yellow": 24, "black": 24, "red": 24},
  "cures": {"blue": "none", ...},
  "research_stations": ["Atlanta", ...],
  "outbreaks": 0, "infection_rate_index": 0, "infection_rate": 2,
  "one_quiet_night": false,
  "players": [{"index", "role", "location",
               "hand": [...] | null,                 // null if hidden from the viewer
               "hand_size", "stored_event": str|null, "ops_move_used": bool}],
  "player_deck": {"size": 40,
                  "piles": [{"size": 9, "epidemic_remaining": true}, ...],  // top first
                  "epidemics_remaining": 5},
  "player_discard": [...], "player_removed": [...],  // removed = epidemics, stored events played
  "infection_deck": {"size": 39,
                     "known_top": [[cards], [cards], ...],  // sets, top first (see below)
                     "forecast": null | {"cards_above": k, "order": [...]}},  // viewer's own Forecast
  "infection_discard": [...],                         // in discard order
  "infection_removed": [...],                         // Resilient Population
  "game_over": false, "outcome": null | {"result", "reason"}
}
```

- **Known infection deck top:** each Intensify pushes the set of shuffled cards onto the
  top of this stack. Drawn cards are removed from their set, and empty sets disappear. After
  a Forecast, the sets overlapping the top 6 merge into one set. If the known sets did not
  cover the top 6 cards, they are dropped, because they are no longer reliable. Every listed
  set is always exactly the set of cards in those positions.
- **Forecast knowledge:** only the player who arranged the cards sees `forecast`. `order` is
  the exact sequence starting `cards_above` cards below the top. It shrinks as those cards are
  drawn, grows `cards_above` on Intensify, and is discarded when another Forecast is played.
- Deck orders and the RNG are never included.

## Rule interpretations

- **Event timing:** the rulebook forbids playing an event between drawing a card and
  resolving it. For that reason the "after the draw, before epidemic resolution" window from
  the plan is a `before_draw` window, placed after the actions and before drawing. Events
  are allowed between two epidemics, and Resilient Population between Infect and Intensify.
- **One Quiet Night** played in the `before_infection` window before the first flip skips
  this turn's infections. Played later in the infection phase, it skips the next turn's.
- **Infection deck empty** (not covered by the rules): the flip or epidemic infect does
  nothing.
- **Medic** auto-clears whenever his pawn moves for any reason, and after any cure. **Quarantine
  Specialist and Medic** prevention does not apply during setup.
- **Outbreak chain:** chain reactions are processed breadth-first. Cities that already
  outbroke while resolving the current card are skipped.
- **First player:** the seat with the highest-population city card. Ties break toward the
  lower `CITY_INDEX`, and events count as no population.
- **Hand-limit discards** may be replaced by playing events from the hand. A Contingency
  Planner's stored card does not count toward the limit and does not satisfy it.
- **Event windows:** being offered a window reveals that a player holds a playable event.
  This is inherent to the window design.
