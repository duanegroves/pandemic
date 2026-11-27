"""Fixed discrete action space and flat observation encoding.

ACTION SPACE (``ACTION_SPACE_SIZE`` indices, independent of player count)
------------------------------------------------------------------------
Players are addressed *relative to the acting player*: ``rel = (seat - actor) % num_players``
(0 = self, 1 = the player to the left, ...), so a policy is seat-symmetric.

Segments (in order; see ``SEGMENTS`` for exact offsets):

* ``drive``/``direct``/``charter``/``shuttle``/``dispatcher``: ``rel_pawn(4) x destination(48)``
* ``ops_move``: ``destination(48) x card(48)``
* ``build``: ``relocate_from`` city (0..47) or none (48)
* ``treat``: color(4)
* ``give`` / ``take``: ``rel_player(4) x card(48)``
* ``cure``: color(4).  CANONICALIZATION: the engine's DiscoverCure carries an explicit card
  subset (several per color are possible). The index only names the color; ``decode`` picks the
  *first* legal DiscoverCure of that color in ``legal_actions`` order (deterministic).
* ``take_event``: event(5)
* ``end_actions``, ``pass``: 1 each;  ``consent``: no/yes (2)
* ``discard``: any player card (48 cities + 5 events = 53)
* ``forecast_slot``: 6 "pick next card" slots. ForecastOrder (up to 720 permutations) is NOT in
  the action space; the env asks for the order one card at a time, where slot ``k`` means "the
  k-th card of ``decision.context['cards']`` goes next". ``encode`` raises for ForecastOrder;
  use ``forecast_order_from_picks``.
* ``airlift``: ``rel_pawn(4) x destination(48)``; ``one_quiet_night``: 1;
  ``resilient``: infection card(48); ``grant``: ``city(48) x relocate_from(49)``; ``forecast``: 1

OBSERVATION LAYOUT (``OBS_SIZE`` float32, all values in [0, 1]); see ``OBS_LAYOUT`` for offsets.
Player-indexed blocks have 4 rows, ordered relative to the observing player (row 0 = self,
absent seats are zero), so the size is the same for 2-4 players. Built only from ``observe()``.
"""

from __future__ import annotations

import numpy as np

from pandemic.data.cities import CITY_INDEX, CITY_NAMES, Color
from pandemic.engine import (
    Action,
    BuildResearchStation,
    CharterFlight,
    Consent,
    DirectFlight,
    Discard,
    DiscoverCure,
    DispatcherMove,
    DriveFerry,
    EndActions,
    ForecastOrder,
    GameState,
    GiveCard,
    OperationsMove,
    Pass,
    PlayAirlift,
    PlayForecast,
    PlayGovernmentGrant,
    PlayOneQuietNight,
    PlayResilientPopulation,
    ShuttleFlight,
    TakeCard,
    TakeEventCard,
    TreatDisease,
    current_decision,
    legal_actions,
    observe,
)
from pandemic.engine.config import ROLES
from pandemic.engine.state import COLORS, EVENT_NAMES

NC = len(CITY_NAMES)  # 48
NE = len(EVENT_NAMES)  # 5
NCARD = NC + NE  # 53
MAXP = 4
NCOL = 4
MAX_FORECAST = 6
_EVENT_INDEX = {e: i for i, e in enumerate(EVENT_NAMES)}
_COLOR_INDEX = {c: i for i, c in enumerate(COLORS)}

# ----------------------------------------------------------------------------- action layout
_seg_defs = [
    ("drive", MAXP * NC), ("direct", MAXP * NC), ("charter", MAXP * NC),
    ("shuttle", MAXP * NC), ("dispatcher", MAXP * NC), ("ops_move", NC * NC),
    ("build", NC + 1), ("treat", NCOL), ("give", MAXP * NC), ("take", MAXP * NC),
    ("cure", NCOL), ("take_event", NE), ("end_actions", 1), ("discard", NCARD),
    ("pass", 1), ("consent", 2), ("forecast_slot", MAX_FORECAST), ("airlift", MAXP * NC),
    ("one_quiet_night", 1), ("resilient", NC), ("grant", NC * (NC + 1)), ("forecast", 1),
]
SEGMENTS: dict[str, tuple[int, int]] = {}
_off = 0
for _name, _size in _seg_defs:
    SEGMENTS[_name] = (_off, _size)
    _off += _size
ACTION_SPACE_SIZE: int = _off


def _card_index(card: str) -> int:
    if card in CITY_INDEX:
        return CITY_INDEX[card]
    return NC + _EVENT_INDEX[card]


def _card_name(i: int) -> str:
    return CITY_NAMES[i] if i < NC else EVENT_NAMES[i - NC]


def _n(state: GameState) -> int:
    return len(state.players)


def _actor(state: GameState) -> int:
    p = current_decision(state).player
    assert p is not None
    return p


_MOVE_SEGS = {DriveFerry: "drive", DirectFlight: "direct", CharterFlight: "charter",
              ShuttleFlight: "shuttle", DispatcherMove: "dispatcher"}
_MOVE_CLS = {v: k for k, v in _MOVE_SEGS.items()}


def encode(action: Action, state: GameState, actor: int | None = None) -> int:
    """Map an engine Action to its action index (DiscoverCure maps to its color index)."""
    if actor is None:
        actor = _actor(state)
    n = _n(state)
    if isinstance(
        action, DriveFerry | DirectFlight | CharterFlight | ShuttleFlight | DispatcherMove
    ):
        rel = (action.pawn - actor) % n
        return SEGMENTS[_MOVE_SEGS[type(action)]][0] + rel * NC + CITY_INDEX[action.destination]
    if isinstance(action, OperationsMove):
        return (SEGMENTS["ops_move"][0] + CITY_INDEX[action.destination] * NC
                + CITY_INDEX[action.card])
    if isinstance(action, BuildResearchStation):
        r = NC if action.relocate_from is None else CITY_INDEX[action.relocate_from]
        return SEGMENTS["build"][0] + r
    if isinstance(action, TreatDisease):
        return SEGMENTS["treat"][0] + _COLOR_INDEX[action.color]
    if isinstance(action, GiveCard):
        return SEGMENTS["give"][0] + ((action.to_player - actor) % n) * NC + CITY_INDEX[action.card]
    if isinstance(action, TakeCard):
        return (SEGMENTS["take"][0] + ((action.from_player - actor) % n) * NC
                + CITY_INDEX[action.card])
    if isinstance(action, DiscoverCure):
        return SEGMENTS["cure"][0] + _COLOR_INDEX[action.color]
    if isinstance(action, TakeEventCard):
        return SEGMENTS["take_event"][0] + _EVENT_INDEX[action.card]
    if isinstance(action, EndActions):
        return SEGMENTS["end_actions"][0]
    if isinstance(action, Discard):
        return SEGMENTS["discard"][0] + _card_index(action.card)
    if isinstance(action, Pass):
        return SEGMENTS["pass"][0]
    if isinstance(action, Consent):
        return SEGMENTS["consent"][0] + int(action.accept)
    if isinstance(action, PlayAirlift):
        return (SEGMENTS["airlift"][0] + ((action.pawn - actor) % n) * NC
                + CITY_INDEX[action.destination])
    if isinstance(action, PlayOneQuietNight):
        return SEGMENTS["one_quiet_night"][0]
    if isinstance(action, PlayResilientPopulation):
        return SEGMENTS["resilient"][0] + CITY_INDEX[action.card]
    if isinstance(action, PlayGovernmentGrant):
        r = NC if action.relocate_from is None else CITY_INDEX[action.relocate_from]
        return SEGMENTS["grant"][0] + CITY_INDEX[action.city] * (NC + 1) + r
    if isinstance(action, PlayForecast):
        return SEGMENTS["forecast"][0]
    if isinstance(action, ForecastOrder):
        raise ValueError("ForecastOrder is decomposed into forecast_slot picks by the env")
    raise ValueError(f"unknown action {action!r}")


def segment_of(index: int) -> tuple[str, int]:
    for name, (off, size) in SEGMENTS.items():
        if off <= index < off + size:
            return name, index - off
    raise ValueError(f"action index out of range: {index}")


def decode(index: int, state: GameState, actor: int | None = None) -> Action:
    """Inverse of ``encode``. Cure indices resolve to the first legal DiscoverCure of that
    color. Forecast slot indices cannot be decoded (see ``forecast_order_from_picks``)."""
    if actor is None:
        actor = _actor(state)
    n = _n(state)
    seg, k = segment_of(int(index))
    if seg in _MOVE_CLS:
        rel, dest = divmod(k, NC)
        return _MOVE_CLS[seg](pawn=(actor + rel) % n, destination=CITY_NAMES[dest])
    if seg == "ops_move":
        dest, card = divmod(k, NC)
        return OperationsMove(destination=CITY_NAMES[dest], card=CITY_NAMES[card])
    if seg == "build":
        return BuildResearchStation(None if k == NC else CITY_NAMES[k])
    if seg == "treat":
        return TreatDisease(COLORS[k])
    if seg in ("give", "take"):
        rel, card = divmod(k, NC)
        p = (actor + rel) % n
        if seg == "give":
            return GiveCard(to_player=p, card=CITY_NAMES[card])
        return TakeCard(from_player=p, card=CITY_NAMES[card])
    if seg == "cure":
        color = COLORS[k]
        for a in legal_actions(state):
            if isinstance(a, DiscoverCure) and a.color == color:
                return a
        raise ValueError(f"no legal DiscoverCure for {color}")
    if seg == "take_event":
        return TakeEventCard(EVENT_NAMES[k])
    if seg == "end_actions":
        return EndActions()
    if seg == "discard":
        return Discard(_card_name(k))
    if seg == "pass":
        return Pass()
    if seg == "consent":
        return Consent(bool(k))
    if seg == "airlift":
        rel, dest = divmod(k, NC)
        return PlayAirlift(pawn=(actor + rel) % n, destination=CITY_NAMES[dest])
    if seg == "one_quiet_night":
        return PlayOneQuietNight()
    if seg == "resilient":
        return PlayResilientPopulation(CITY_NAMES[k])
    if seg == "grant":
        city, r = divmod(k, NC + 1)
        return PlayGovernmentGrant(CITY_NAMES[city], None if r == NC else CITY_NAMES[r])
    if seg == "forecast":
        return PlayForecast()
    raise ValueError("forecast_slot indices are not engine actions")


def forecast_order_from_picks(state: GameState,
                              picks: tuple[int, ...] | list[int]) -> ForecastOrder:
    cards = current_decision(state).context["cards"]
    return ForecastOrder(tuple(cards[i] for i in picks))


def forecast_mask(state: GameState, picks: tuple[int, ...] | list[int] = ()) -> np.ndarray:
    m = np.zeros(ACTION_SPACE_SIZE, dtype=bool)
    off = SEGMENTS["forecast_slot"][0]
    n = len(current_decision(state).context["cards"])
    for i in range(n):
        if i not in picks:
            m[off + i] = True
    return m


def action_mask(state: GameState, forecast_picks: tuple[int, ...] | list[int] = ()) -> np.ndarray:
    """Boolean mask over the action space for the owner of the current decision."""
    m = np.zeros(ACTION_SPACE_SIZE, dtype=bool)
    d = current_decision(state)
    if d.kind == "game_over":
        return m
    if d.kind == "forecast_order":
        return forecast_mask(state, forecast_picks)
    actor = d.player
    for a in legal_actions(state):
        m[encode(a, state, actor)] = True
    return m


# ----------------------------------------------------------------------------- observation
_KINDS = ("actions", "event_window", "discard", "consent", "forecast_order", "game_over")
_PHASES = ("actions", "draw", "infect", "over")
_CHECKPOINTS = ("actions", "before_draw", "epidemic_intensify", "between_epidemics",
                "before_infection")
_DIFFS = ("introductory", "standard", "heroic")
_CONSENT_TYPES = ("give_card", "take_card", "drive_ferry", "direct_flight", "charter_flight",
                  "shuttle_flight", "dispatcher_move", "play_airlift")

_obs_defs = [
    ("cubes", NC * NCOL), ("supply", NCOL), ("stations", NC),
    ("pawn_loc", MAXP * NC), ("role", MAXP * len(ROLES)),
    ("own_hand", NCARD), ("other_hands", (MAXP - 1) * NCARD), ("hand_known", MAXP),
    ("hand_size", MAXP), ("stored_event", MAXP * NE), ("ops_used", MAXP),
    ("cure_cured", NCOL), ("cure_eradicated", NCOL),
    ("scalars", 8),  # outbreaks, rate idx, rate, one_quiet_night, turn, actions_left, n, open
    ("difficulty", len(_DIFFS)),
    ("infection_discard", NC), ("infection_removed", NC),
    ("known_top", NC), ("infection_deck_size", 1),
    ("forecast_known", NC), ("forecast_above", 1),
    ("deck_size", 1), ("epidemics_remaining", 1), ("piles", MAX_FORECAST * 2),
    ("player_discard", NCARD), ("player_removed", NE),
    ("decision_kind", len(_KINDS)), ("phase", len(_PHASES)),
    ("current_player", MAXP), ("decision_owner", MAXP),
    ("checkpoint", len(_CHECKPOINTS)), ("consent_requester", MAXP),
    ("consent_request", len(_CONSENT_TYPES)),
    ("forecast_cards", MAX_FORECAST * NC), ("forecast_picked", MAX_FORECAST),
]
OBS_LAYOUT: dict[str, tuple[int, int]] = {}
_o = 0
for _name, _size in _obs_defs:
    OBS_LAYOUT[_name] = (_o, _size)
    _o += _size
OBS_SIZE: int = _o


def encode_observation(obs: dict, forecast_picks: tuple[int, ...] | list[int] = ()) -> np.ndarray:
    """Flatten an ``observe()`` dict into the float32 vector described in the module docstring.

    ``forecast_picks`` is the in-progress Forecast ordering (slot indices already chosen); it is
    only meaningful for the owner of the forecast_order decision.
    """
    v = np.zeros(OBS_SIZE, dtype=np.float32)
    L = OBS_LAYOUT

    def seg(name: str) -> np.ndarray:
        o, s = L[name]
        return v[o:o + s]

    viewer = obs["viewer"]
    players = obs["players"]
    n = len(players)

    def rel(p: int) -> int:
        return (p - viewer) % n if viewer is not None else p

    cubes = seg("cubes").reshape(NC, NCOL)
    for city, per in obs["cubes"].items():
        for color, c in per.items():
            cubes[CITY_INDEX[city], _COLOR_INDEX[Color(color)]] = c / 3.0
    sup = seg("supply")
    for color, c in obs["supply"].items():
        sup[_COLOR_INDEX[Color(color)]] = c / 24.0
    st = seg("stations")
    for c in obs["research_stations"]:
        st[CITY_INDEX[c]] = 1
    loc = seg("pawn_loc").reshape(MAXP, NC)
    role = seg("role").reshape(MAXP, len(ROLES))
    oth = seg("other_hands").reshape(MAXP - 1, NCARD)
    known = seg("hand_known")
    hsize = seg("hand_size")
    stored = seg("stored_event").reshape(MAXP, NE)
    ops = seg("ops_used")
    own = seg("own_hand")
    role_idx = {r.value: i for i, r in enumerate(ROLES)}
    for p in players:
        r = rel(p["index"])
        loc[r, CITY_INDEX[p["location"]]] = 1
        role[r, role_idx[p["role"]]] = 1
        hsize[r] = p["hand_size"] / 8.0
        if p["stored_event"]:
            stored[r, _EVENT_INDEX[p["stored_event"]]] = 1
        ops[r] = float(p["ops_move_used"])
        if p["hand"] is not None:
            known[r] = 1
            tgt = own if r == 0 else oth[r - 1]
            for c in p["hand"]:
                if c in CITY_INDEX or c in _EVENT_INDEX:
                    tgt[_card_index(c)] = 1
    cc, ce = seg("cure_cured"), seg("cure_eradicated")
    for color, s in obs["cures"].items():
        i = _COLOR_INDEX[Color(color)]
        cc[i] = s in ("cured", "eradicated")
        ce[i] = s == "eradicated"
    cfg = obs["config"]
    seg("scalars")[:] = [
        obs["outbreaks"] / 8.0, obs["infection_rate_index"] / 6.0, obs["infection_rate"] / 4.0,
        float(obs["one_quiet_night"]), min(obs["turn"], 100) / 100.0,
        obs["actions_remaining"] / 4.0, n / 4.0, float(cfg["open_hands_effective"]),
    ]
    seg("difficulty")[_DIFFS.index(cfg["difficulty"])] = 1
    for key, name in (("infection_discard", "infection_discard"),
                      ("infection_removed", "infection_removed")):
        s = seg(name)
        for c in obs[key]:
            s[CITY_INDEX[c]] = 1
    idk = obs["infection_deck"]
    kt = seg("known_top")
    for si, cards in enumerate(idk["known_top"]):
        for c in cards:
            kt[CITY_INDEX[c]] = 1.0 / (1 + si)
    seg("infection_deck_size")[0] = idk["size"] / 48.0
    fk = idk.get("forecast")
    if fk:
        order = fk["order"]
        fv = seg("forecast_known")
        for i, c in enumerate(order):
            fv[CITY_INDEX[c]] = (i + 1) / max(len(order), 1)
        seg("forecast_above")[0] = fk["cards_above"] / 48.0
    pd = obs["player_deck"]
    seg("deck_size")[0] = pd["size"] / 60.0
    seg("epidemics_remaining")[0] = pd["epidemics_remaining"] / 6.0
    piles = seg("piles").reshape(MAX_FORECAST, 2)
    for i, pile in enumerate(pd["piles"][:MAX_FORECAST]):
        piles[i, 0] = pile["size"] / 12.0
        piles[i, 1] = float(pile["epidemic_remaining"])
    pdis = seg("player_discard")
    for c in obs["player_discard"]:
        if c in CITY_INDEX or c in _EVENT_INDEX:
            pdis[_card_index(c)] = 1
    prem = seg("player_removed")
    for c in obs["player_removed"]:
        if c in _EVENT_INDEX:
            prem[_EVENT_INDEX[c]] = 1
    dec = obs["decision"]
    seg("decision_kind")[_KINDS.index(dec["kind"])] = 1
    seg("phase")[_PHASES.index(obs["phase"])] = 1
    seg("current_player")[rel(obs["current_player"])] = 1
    if dec["player"] is not None:
        seg("decision_owner")[rel(dec["player"])] = 1
    ctx = dec["context"]
    if dec["kind"] == "event_window" and ctx.get("checkpoint") in _CHECKPOINTS:
        seg("checkpoint")[_CHECKPOINTS.index(ctx["checkpoint"])] = 1
    if dec["kind"] == "consent":
        seg("consent_requester")[rel(ctx["requester"])] = 1
        rt = ctx["request"].get("type")
        if rt in _CONSENT_TYPES:
            seg("consent_request")[_CONSENT_TYPES.index(rt)] = 1
    if dec["kind"] == "forecast_order" and dec["player"] == viewer and "cards" in ctx:
        fc = seg("forecast_cards").reshape(MAX_FORECAST, NC)
        for i, c in enumerate(ctx["cards"][:MAX_FORECAST]):
            fc[i, CITY_INDEX[c]] = 1
        fp = seg("forecast_picked")
        for rank, slot in enumerate(forecast_picks):
            fp[slot] = (rank + 1) / MAX_FORECAST
    return np.clip(v, 0.0, 1.0, out=v)


def observation_for(state: GameState, player: int,
                    forecast_picks: tuple[int, ...] | list[int] = ()) -> np.ndarray:
    return encode_observation(observe(state, player), forecast_picks)


__all__ = [
    "ACTION_SPACE_SIZE", "OBS_LAYOUT", "OBS_SIZE", "SEGMENTS", "action_mask",
    "decode", "encode", "encode_observation", "forecast_mask", "forecast_order_from_picks",
    "observation_for",
]
