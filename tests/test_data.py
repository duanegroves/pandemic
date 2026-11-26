from pandemic.data.cities import CITIES, CITY_INDEX, CITY_NAMES, EDGES, Color, neighbors


def test_counts():
    assert len(CITIES) == 48
    assert len(CITY_NAMES) == 48
    for color in Color:
        assert sum(1 for c in CITIES.values() if c.color is color) == 12
    assert CITY_INDEX[CITY_NAMES[5]] == 5


def test_edges_valid_and_unique():
    seen = set()
    for a, b in EDGES:
        assert a in CITIES and b in CITIES
        assert a != b
        key = frozenset((a, b))
        assert key not in seen
        seen.add(key)
    assert len(EDGES) == 93


def test_symmetric_no_self_loops():
    for name, city in CITIES.items():
        assert name not in city.neighbors
        for n in city.neighbors:
            assert name in CITIES[n].neighbors


def test_connected():
    seen = {"Atlanta"}
    stack = ["Atlanta"]
    while stack:
        for n in neighbors(stack.pop()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    assert seen == set(CITIES)


def test_spot_checks():
    assert "Tokyo" in neighbors("San Francisco")
    assert "Manila" in neighbors("San Francisco")
    assert "Sydney" in neighbors("Los Angeles")
    assert "Madrid" in neighbors("São Paulo")
    assert "Cairo" not in neighbors("Moscow")
    assert len(neighbors("Chicago")) == 5
    assert len(neighbors("Santiago")) == 1


def test_unique_populations():
    assert len({c.population for c in CITIES.values()}) == 48
