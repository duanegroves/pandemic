"""Per-player redacted, JSON-serializable views of the game."""

from __future__ import annotations

from pandemic.data.cards import EPIDEMIC
from pandemic.engine.legal import current_decision
from pandemic.engine.state import COLORS, GameState, _copy_json


def _hand_visible(state: GameState, viewer: int | None, owner: int) -> bool:
    return viewer == owner or state.config.hands_open


def observe(state: GameState, player_index: int | None) -> dict:
    """View of the game for seat ``player_index`` (``None`` = spectator: no private info
    except what open hands reveal). See docs/ENGINE_API.md for the schema."""
    d = current_decision(state)
    ctx = _copy_json(d.context)
    if d.kind == "forecast_order" and d.player != player_index:
        ctx = {"num_cards": len(ctx["cards"])}
    ctx.pop("queue", None)  # would reveal who else holds playable events

    players = []
    for i, p in enumerate(state.players):
        vis = _hand_visible(state, player_index, i)
        players.append({
            "index": i,
            "role": p.role.value,
            "location": p.location,
            "hand": list(p.hand) if vis else None,
            "hand_size": len(p.hand),
            "stored_event": p.stored_event,
            "ops_move_used": p.ops_move_used,
        })

    fk = state.forecast_known
    forecast = None
    if fk is not None and fk["player"] == player_index:
        forecast = {"cards_above": fk["above"], "order": list(fk["order"])}

    return {
        "viewer": player_index,
        "config": state.config.to_dict() | {"open_hands_effective": state.config.hands_open},
        "turn": state.turn,
        "current_player": state.current_player,
        "phase": state.phase,
        "actions_remaining": state.actions_remaining,
        "decision": {"kind": d.kind, "player": d.player, "context": ctx},
        "cubes": {city: {COLORS[ci].value: n for ci, n in enumerate(v) if n}
                  for city, v in state.cubes.items() if any(v)},
        "supply": {c.value: state.supply[i] for i, c in enumerate(COLORS)},
        "cures": {c.value: state.cures[i] for i, c in enumerate(COLORS)},
        "research_stations": list(state.stations),
        "outbreaks": state.outbreaks,
        "infection_rate_index": state.infection_rate_index,
        "infection_rate": state.infection_rate,
        "one_quiet_night": state.one_quiet_night,
        "players": players,
        "player_deck": {
            "size": len(state.player_deck),
            "piles": [{"size": s, "epidemic_remaining": e} for s, e in state.player_deck_piles],
            "epidemics_remaining": sum(1 for _, e in state.player_deck_piles if e),
        },
        "player_discard": list(state.player_discard),
        "player_removed": list(state.player_removed),
        "infection_deck": {
            "size": len(state.infection_deck),
            "known_top": [list(s) for s in state.infection_known],
            "forecast": forecast,
        },
        "infection_discard": list(state.infection_discard),
        "infection_removed": list(state.infection_removed),
        "game_over": state.outcome is not None,
        "outcome": _copy_json(state.outcome),
    }


def redact_event(event, state: GameState, player_index: int | None) -> dict:
    """``event.to_dict()`` with information hidden from ``player_index`` removed:
    drawn player cards of other players (closed hands; Epidemics stay visible, others
    become ``None``) and other players' Forecast orders."""
    d = event.to_dict()
    t = d["type"]
    if t == "player_cards_drawn" and not _hand_visible(state, player_index, d["player"]):
        d["cards"] = [c if c == EPIDEMIC else None for c in d["cards"]]
    elif t == "forecast_arranged" and d["player"] != player_index:
        d["order"] = None
    return d
