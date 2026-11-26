"""Compare map data with the official board."""

from pandemic.data.cities import CITIES, CITY_NAMES, neighbors

ADJ = """San Francisco: Tokyo, Manila, Los Angeles, Chicago
Chicago: San Francisco, Los Angeles, Mexico City, Atlanta, Montréal
Montréal: Chicago, Washington, New York
New York: Montréal, Washington, London, Madrid
Washington: Atlanta, Montréal, New York, Miami
Atlanta: Chicago, Washington, Miami
Los Angeles: San Francisco, Chicago, Mexico City, Sydney
Mexico City: Los Angeles, Chicago, Miami, Bogotá, Lima
Miami: Atlanta, Washington, Mexico City, Bogotá
Bogotá: Miami, Mexico City, Lima, São Paulo, Buenos Aires
Lima: Mexico City, Bogotá, Santiago
Santiago: Lima
Buenos Aires: Bogotá, São Paulo
São Paulo: Bogotá, Buenos Aires, Madrid, Lagos
Lagos: São Paulo, Khartoum, Kinshasa
Kinshasa: Lagos, Khartoum, Johannesburg
Khartoum: Lagos, Kinshasa, Johannesburg, Cairo
Johannesburg: Kinshasa, Khartoum
Madrid: New York, São Paulo, London, Paris, Algiers
London: New York, Madrid, Paris, Essen
Paris: London, Madrid, Essen, Milan, Algiers
Essen: London, Paris, Milan, St. Petersburg
St. Petersburg: Essen, Istanbul, Moscow
Milan: Essen, Paris, Istanbul
Algiers: Madrid, Paris, Istanbul, Cairo
Cairo: Algiers, Istanbul, Baghdad, Riyadh, Khartoum
Istanbul: Milan, St. Petersburg, Moscow, Baghdad, Cairo, Algiers
Moscow: St. Petersburg, Istanbul, Tehran
Baghdad: Tehran, Istanbul, Cairo, Riyadh, Karachi
Tehran: Moscow, Baghdad, Karachi, Delhi
Riyadh: Cairo, Baghdad, Karachi
Karachi: Tehran, Baghdad, Riyadh, Mumbai, Delhi
Mumbai: Karachi, Delhi, Chennai
Delhi: Tehran, Karachi, Mumbai, Chennai, Kolkata
Chennai: Mumbai, Delhi, Kolkata, Bangkok, Jakarta
Kolkata: Delhi, Chennai, Bangkok, Hong Kong
Bangkok: Kolkata, Chennai, Jakarta, Ho Chi Minh City, Hong Kong
Jakarta: Chennai, Bangkok, Ho Chi Minh City, Sydney
Ho Chi Minh City: Jakarta, Bangkok, Hong Kong, Manila
Hong Kong: Kolkata, Bangkok, Ho Chi Minh City, Manila, Taipei, Shanghai
Shanghai: Beijing, Seoul, Tokyo, Taipei, Hong Kong
Beijing: Shanghai, Seoul
Seoul: Beijing, Shanghai, Tokyo
Tokyo: Seoul, Shanghai, Osaka, San Francisco
Osaka: Tokyo, Taipei
Taipei: Osaka, Shanghai, Hong Kong, Manila
Manila: Taipei, Hong Kong, Ho Chi Minh City, Sydney, San Francisco
Sydney: Jakarta, Manila, Los Angeles"""


def test_adjacency_matches_official_board():
    exp = {}
    for line in ADJ.splitlines():
        a, b = line.split(": ")
        exp[a] = set(b.split(", "))
    assert set(exp) == set(CITY_NAMES)
    for a, bs in exp.items():
        assert set(neighbors(a)) == bs, (a, set(neighbors(a)) ^ bs)


def test_colors_and_populations():
    from collections import Counter

    c = Counter(CITIES[n].color.value for n in CITY_NAMES)
    assert c == {"blue": 12, "yellow": 12, "black": 12, "red": 12}, c
    assert len(CITY_NAMES) == 48
