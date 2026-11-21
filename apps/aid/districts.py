"""Approximate local district lookup; these are search areas, not legal boundaries."""
from math import cos, radians, hypot

DISTRICT_AREAS = [
    {'value': 'central', 'latitude': 69.349, 'longitude': 88.201, 'radius_km': 8},
    {'value': 'talnakh', 'latitude': 69.500, 'longitude': 88.400, 'radius_km': 7},
    {'value': 'kayerkan', 'latitude': 69.354, 'longitude': 87.760, 'radius_km': 6},
    {'value': 'oganer', 'latitude': 69.358, 'longitude': 88.380, 'radius_km': 3},
]


def district_at(latitude, longitude):
    if latitude is None or longitude is None:
        return None
    latitude, longitude = float(latitude), float(longitude)
    matches = []
    for area in DISTRICT_AREAS:
        distance = hypot((latitude-area['latitude'])*111.32,
                         (longitude-area['longitude'])*111.32*cos(radians(latitude)))
        if distance <= area['radius_km']:
            matches.append((distance, area['value']))
    return min(matches)[1] if matches else None
