"""Baseline agents. An agent exposes ``act(core) -> action_index`` where ``core`` is a
:class:`pandemic.ai.env.PandemicCore` (``env.core`` for either env)."""

from __future__ import annotations

from collections import deque

import numpy as np

from pandemic.ai.encoding import SEGMENTS, encode
from pandemic.data.cities import CITIES, CITY_INDEX
from pandemic.engine import (
    BuildResearchStation,
    CharterFlight,
    Consent,
    DirectFlight,
    Discard,
    DiscoverCure,
    DriveFerry,
    EndActions,
    GiveCard,
    OperationsMove,
    Pass,
    ShuttleFlight,
    TakeCard,
    TreatDisease,
    current_decision,
    legal_actions,
)
from pandemic.engine.state import COLOR_INDEX


class RandomAgent:
    """Uniformly random among masked-legal action indices."""

    def __init__(self, seed: int | None = None):
        self.rng = np.random.default_rng(seed)

    def act(self, core) -> int:
        return int(self.rng.choice(np.flatnonzero(core.mask())))


def _bfs(sources: list[str]) -> dict[str, int]:
    dist = {s: 0 for s in sources}
    q = deque(sources)
    while q:
        c = q.popleft()
        for nb in CITIES[c].neighbors:
            if nb not in dist:
                dist[nb] = dist[c] + 1
                q.append(nb)
    return dist


class HeuristicAgent:
    """Simple scripted player (uses the true state only through the acting player's legal
    actions and public/own information)."""

    def __init__(self, seed: int | None = None):
        self.rng = np.random.default_rng(seed)

    def act(self, core) -> int:
        s = core.state
        d = current_decision(s)
        if d.kind == "forecast_order":
            off = SEGMENTS["forecast_slot"][0]
            return off + next(i for i in range(len(d.context["cards"]))
                              if i not in core.forecast_picks)
        acts = legal_actions(s)
        me = d.player
        if d.kind == "event_window":
            return encode(next(a for a in acts if isinstance(a, Pass)), s, me)
        if d.kind == "consent":
            return encode(next(a for a in acts if isinstance(a, Consent) and a.accept), s, me)
        if d.kind == "discard":
            return encode(self._discard(s, me, acts), s, me)
        return encode(self._turn_action(s, me, acts), s, me)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _color_counts(hand: list[str]) -> list[int]:
        cnt = [0, 0, 0, 0]
        for c in hand:
            if c in CITIES:
                cnt[COLOR_INDEX[CITIES[c].color]] += 1
        return cnt

    def _share(self, s, me, acts):
        """Share Knowledge when it moves a city card to the teammate holding more cards of
        that color than the current owner."""
        best, best_gain = None, 0
        for a in acts:
            if isinstance(a, GiveCard):
                giver, recv, card = me, a.to_player, a.card
            elif isinstance(a, TakeCard):
                giver, recv, card = a.from_player, me, a.card
            else:
                continue
            ci = COLOR_INDEX[CITIES[card].color]
            g = self._color_counts(s.players[giver].hand)[ci]
            r = self._color_counts(s.players[recv].hand)[ci]
            gain = r - g + 1 if r >= g and r >= 2 else 0
            if gain > best_gain:
                best, best_gain = a, gain
        return best

    def _discard(self, s, me, acts):
        hand = s.players[me].hand
        cnt = self._color_counts(hand)
        best, best_key = None, None
        for a in acts:
            if not isinstance(a, Discard) or a.card not in CITIES:
                continue
            key = (cnt[COLOR_INDEX[CITIES[a.card].color]], self.rng.random())
            if best_key is None or key < best_key:
                best, best_key = a, key
        return best or next(a for a in acts if isinstance(a, Discard))

    def _turn_action(self, s, me, acts):
        p = s.players[me]
        need = 4 if p.role.value == "scientist" else 5
        cures = [a for a in acts if isinstance(a, DiscoverCure)]
        if cures:
            return cures[0]
        here = s.cubes[p.location]
        treats = [a for a in acts if isinstance(a, TreatDisease)]
        if treats:
            best = max(treats, key=lambda a: here[COLOR_INDEX[a.color]])
            n = here[COLOR_INDEX[best.color]]
            if n >= 2 or s.cures[COLOR_INDEX[best.color]] != "none" or p.role.value == "medic":
                return best
        cnt = self._color_counts(p.hand)
        share = self._share(s, me, acts)
        if share is not None:
            return share
        stations = list(s.stations)
        dist_station = _bfs(stations)
        if max(cnt) >= need:
            target = stations
        else:
            # most infected city, weighted by cubes
            target = None
        if target is None:
            # build a station if far from any and holding the local card
            builds = [a for a in acts if isinstance(a, BuildResearchStation)
                      and a.relocate_from is None]
            if builds and dist_station.get(p.location, 99) >= 4 and len(stations) < 6:
                return builds[0]
            if treats:
                return max(treats, key=lambda a: here[COLOR_INDEX[a.color]])
            weights = {c: sum(v) for c, v in s.cubes.items() if sum(v) > 0}
            if weights:
                dist_me = _bfs([p.location])
                top = max(weights, key=lambda c: (weights[c] * 3 - dist_me[c], -CITY_INDEX[c]))
                target = [top]
        if target is not None:
            if p.location in target:
                pass
            else:
                dist = _bfs(target)
                here_d = dist[p.location]
                moves = [a for a in acts if isinstance(a, (DriveFerry, DirectFlight, ShuttleFlight))
                         and a.pawn == me]
                best, best_d = None, here_d
                for a in moves:
                    dd = dist[a.destination]
                    if isinstance(a, ShuttleFlight):
                        dd = min(dd, 0) if a.destination in target else dd
                    if isinstance(a, (DirectFlight,)) and here_d - dd < 3:
                        continue
                    if dd < best_d or (dd == best_d and best is not None
                                       and isinstance(a, DriveFerry)
                                       and not isinstance(best, DriveFerry)):
                        best, best_d = a, dd
                if best is not None:
                    return best
        if treats:
            return treats[0]
        drives = [a for a in acts if isinstance(a, DriveFerry) and a.pawn == me]
        if drives:
            return drives[int(self.rng.integers(len(drives)))]
        for a in acts:
            if isinstance(a, EndActions):
                return a
        non_ops = [a for a in acts if not isinstance(a, (OperationsMove, CharterFlight))]
        return (non_ops or acts)[0]
