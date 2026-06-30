from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float


EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(start: Coordinate, end: Coordinate) -> float:
    start_latitude = math.radians(start.latitude)
    end_latitude = math.radians(end.latitude)
    delta_latitude = math.radians(end.latitude - start.latitude)
    delta_longitude = math.radians(end.longitude - start.longitude)

    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(start_latitude)
        * math.cos(end_latitude)
        * math.sin(delta_longitude / 2) ** 2
    )
    central_angle = 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
    return EARTH_RADIUS_METERS * central_angle


def total_distance_meters(points: Iterable[Coordinate]) -> int:
    total = 0.0
    previous: Coordinate | None = None

    for point in points:
        if previous is None:
            previous = point
            continue

        if point == previous:
            continue

        total += haversine_distance_meters(previous, point)
        previous = point

    return round(total)
