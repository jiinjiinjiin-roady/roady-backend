from app.utils.distance import Coordinate, haversine_distance_meters, total_distance_meters


def test_total_distance_requires_at_least_two_distinct_points() -> None:
    assert total_distance_meters([]) == 0
    assert total_distance_meters([Coordinate(37.0, 127.0)]) == 0
    assert total_distance_meters([Coordinate(37.0, 127.0), Coordinate(37.0, 127.0)]) == 0


def test_haversine_distance_for_known_equator_segment() -> None:
    distance = haversine_distance_meters(Coordinate(0.0, 0.0), Coordinate(0.0, 1.0))

    assert round(distance) == 111195


def test_total_distance_sums_multiple_segments_and_skips_repeated_points() -> None:
    points = [
        Coordinate(0.0, 0.0),
        Coordinate(0.0, 1.0),
        Coordinate(0.0, 1.0),
        Coordinate(0.0, 2.0),
    ]

    assert total_distance_meters(points) == 222390
