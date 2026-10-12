import math
import re

from . import http
from .models import ShipError


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def locate(near: str) -> tuple[float, float]:
    """`lat,lon` is used as given; anything else is looked up on OpenStreetMap's Nominatim."""
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", near)
    if m:
        return float(m[1]), float(m[2])
    r = http.get("https://nominatim.openstreetmap.org/search", params={"q": near, "format": "json", "limit": 1},
                 headers={"User-Agent": "shipq"})
    hits = r.json() if r.status_code == 200 else []
    if not hits:
        raise ShipError(f"couldn't find {near!r}; pass coordinates as lat,lon instead")
    return float(hits[0]["lat"]), float(hits[0]["lon"])
