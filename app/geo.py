import math
import random

EARTH_RADIUS_M = 6_371_000
MOCK_LOCATION = {"latitude": 40.7128, "longitude": -74.0060}


def haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    to_rad = math.radians
    d_lat = to_rad(lat2 - lat1)
    d_lng = to_rad(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def random_offset(max_meters: float, origin: dict[str, float]) -> dict[str, float]:
    angle = random.random() * 2 * math.pi
    dist = random.random() * max_meters
    lat_offset = (dist * math.cos(angle)) / 111_320
    lng_offset = (dist * math.sin(angle)) / (
        111_320 * math.cos(origin["latitude"] * math.pi / 180)
    )
    return {
        "latitude": origin["latitude"] + lat_offset,
        "longitude": origin["longitude"] + lng_offset,
    }
