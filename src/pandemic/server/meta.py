"""Static board data served at ``GET /meta`` so clients need not duplicate the map."""

from __future__ import annotations

from pandemic.data.cards import EventCard
from pandemic.data.cities import CITIES
from pandemic.engine.config import ROLES


def meta_dict() -> dict:
    return {
        "cities": [
            {"name": c.name, "color": c.color.value, "population": c.population,
             "neighbors": list(c.neighbors)}
            for c in CITIES.values()
        ],
        "roles": [r.value for r in ROLES],
        "events": [e.value for e in EventCard],
    }
