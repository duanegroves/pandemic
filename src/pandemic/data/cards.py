from enum import Enum


class EventCard(str, Enum):
    AIRLIFT = "Airlift"
    ONE_QUIET_NIGHT = "One Quiet Night"
    RESILIENT_POPULATION = "Resilient Population"
    GOVERNMENT_GRANT = "Government Grant"
    FORECAST = "Forecast"


EPIDEMIC = "Epidemic"
CUBES_PER_COLOR = 24
MAX_RESEARCH_STATIONS = 6
MAX_OUTBREAKS = 8
HAND_LIMIT = 7
INFECTION_RATE_TRACK = (2, 2, 2, 3, 3, 4, 4)
STARTING_HAND_SIZE = {2: 4, 3: 3, 4: 2}
EPIDEMICS_BY_DIFFICULTY = {"introductory": 4, "standard": 5, "heroic": 6}
