from dataclasses import dataclass
from enum import Enum


class Color(str, Enum):
    BLUE = "blue"
    YELLOW = "yellow"
    BLACK = "black"
    RED = "red"


@dataclass(frozen=True)
class City:
    name: str
    color: Color
    population: int
    neighbors: tuple[str, ...]


# (name, population) grouped by color, alphabetical within color.
_RAW: dict[Color, list[tuple[str, int]]] = {
    Color.BLUE: [
        ("Atlanta", 4_715_000),
        ("Chicago", 9_121_000),
        ("Essen", 575_000),
        ("London", 8_586_000),
        ("Madrid", 5_427_000),
        ("Milan", 5_232_000),
        ("Montréal", 3_429_000),
        ("New York", 20_464_000),
        ("Paris", 10_755_000),
        ("San Francisco", 5_864_000),
        ("St. Petersburg", 4_879_000),
        ("Washington", 4_679_000),
    ],
    Color.YELLOW: [
        ("Bogotá", 8_702_000),
        ("Buenos Aires", 13_639_000),
        ("Johannesburg", 3_888_000),
        ("Khartoum", 4_887_000),
        ("Kinshasa", 9_046_000),
        ("Lagos", 11_547_000),
        # Printed card value is 9,121,000, tied with Chicago; nudged by 1,000 to break the tie.
        ("Lima", 9_120_000),
        ("Los Angeles", 14_900_000),
        ("Mexico City", 19_463_000),
        ("Miami", 5_582_000),
        ("Santiago", 6_015_000),
        ("São Paulo", 20_186_000),
    ],
    Color.BLACK: [
        ("Algiers", 2_946_000),
        ("Baghdad", 6_204_000),
        ("Cairo", 14_718_000),
        ("Chennai", 8_865_000),
        ("Delhi", 22_242_000),
        ("Istanbul", 13_576_000),
        ("Karachi", 20_711_000),
        ("Kolkata", 14_374_000),
        ("Moscow", 15_512_000),
        ("Mumbai", 16_910_000),
        ("Riyadh", 5_037_000),
        ("Tehran", 7_419_000),
    ],
    Color.RED: [
        ("Bangkok", 7_151_000),
        ("Beijing", 17_311_000),
        ("Ho Chi Minh City", 8_314_000),
        ("Hong Kong", 7_106_000),
        ("Jakarta", 26_063_000),
        ("Manila", 20_767_000),
        ("Osaka", 2_871_000),
        ("Seoul", 22_547_000),
        ("Shanghai", 13_482_000),
        ("Sydney", 3_785_000),
        ("Taipei", 8_338_000),
        ("Tokyo", 13_189_000),
    ],
}

EDGES: list[tuple[str, str]] = [
    ("Atlanta", "Chicago"), ("Atlanta", "Washington"), ("Atlanta", "Miami"),
    ("Chicago", "San Francisco"), ("Chicago", "Los Angeles"),
    ("Chicago", "Mexico City"), ("Chicago", "Montréal"),
    ("Montréal", "New York"), ("Montréal", "Washington"),
    ("New York", "Washington"), ("New York", "London"), ("New York", "Madrid"),
    ("Washington", "Miami"),
    ("San Francisco", "Los Angeles"), ("San Francisco", "Tokyo"),
    ("San Francisco", "Manila"),
    ("Los Angeles", "Mexico City"), ("Los Angeles", "Sydney"),
    ("Mexico City", "Miami"), ("Mexico City", "Bogotá"), ("Mexico City", "Lima"),
    ("Miami", "Bogotá"),
    ("Bogotá", "Lima"), ("Bogotá", "São Paulo"), ("Bogotá", "Buenos Aires"),
    ("Lima", "Santiago"),
    ("Buenos Aires", "São Paulo"),
    ("São Paulo", "Madrid"), ("São Paulo", "Lagos"),
    ("London", "Madrid"), ("London", "Paris"), ("London", "Essen"),
    ("Madrid", "Paris"), ("Madrid", "Algiers"),
    ("Paris", "Essen"), ("Paris", "Milan"), ("Paris", "Algiers"),
    ("Essen", "Milan"), ("Essen", "St. Petersburg"),
    ("Milan", "Istanbul"),
    ("St. Petersburg", "Istanbul"), ("St. Petersburg", "Moscow"),
    ("Lagos", "Kinshasa"), ("Lagos", "Khartoum"),
    ("Kinshasa", "Khartoum"), ("Kinshasa", "Johannesburg"),
    ("Khartoum", "Johannesburg"), ("Khartoum", "Cairo"),
    ("Algiers", "Istanbul"), ("Algiers", "Cairo"),
    ("Istanbul", "Cairo"), ("Istanbul", "Baghdad"), ("Istanbul", "Moscow"),
    ("Cairo", "Baghdad"), ("Cairo", "Riyadh"),
    ("Moscow", "Tehran"),
    ("Baghdad", "Tehran"), ("Baghdad", "Karachi"), ("Baghdad", "Riyadh"),
    ("Riyadh", "Karachi"),
    ("Tehran", "Karachi"), ("Tehran", "Delhi"),
    ("Karachi", "Delhi"), ("Karachi", "Mumbai"),
    ("Delhi", "Mumbai"), ("Delhi", "Chennai"), ("Delhi", "Kolkata"),
    ("Mumbai", "Chennai"),
    ("Chennai", "Kolkata"), ("Chennai", "Bangkok"), ("Chennai", "Jakarta"),
    ("Kolkata", "Bangkok"), ("Kolkata", "Hong Kong"),
    ("Bangkok", "Hong Kong"), ("Bangkok", "Ho Chi Minh City"), ("Bangkok", "Jakarta"),
    ("Jakarta", "Ho Chi Minh City"), ("Jakarta", "Sydney"),
    ("Ho Chi Minh City", "Hong Kong"), ("Ho Chi Minh City", "Manila"),
    ("Hong Kong", "Shanghai"), ("Hong Kong", "Taipei"), ("Hong Kong", "Manila"),
    ("Shanghai", "Beijing"), ("Shanghai", "Seoul"), ("Shanghai", "Tokyo"),
    ("Shanghai", "Taipei"),
    ("Beijing", "Seoul"),
    ("Seoul", "Tokyo"),
    ("Tokyo", "Osaka"),
    ("Osaka", "Taipei"),
    ("Taipei", "Manila"),
    ("Manila", "Sydney"),
]


def _build() -> dict[str, City]:
    adj: dict[str, set[str]] = {n: set() for g in _RAW.values() for n, _ in g}
    for a, b in EDGES:
        adj[a].add(b)
        adj[b].add(a)
    cities: dict[str, City] = {}
    for color, group in _RAW.items():
        for name, pop in group:
            cities[name] = City(name, color, pop, tuple(sorted(adj[name])))
    return cities


CITIES: dict[str, City] = _build()
CITY_NAMES: tuple[str, ...] = tuple(n for g in _RAW.values() for n, _ in g)
CITY_INDEX: dict[str, int] = {n: i for i, n in enumerate(CITY_NAMES)}

assert len(CITIES) == 48
assert len({c.population for c in CITIES.values()}) == 48, "city populations must be unique"


def neighbors(name: str) -> tuple[str, ...]:
    return CITIES[name].neighbors
