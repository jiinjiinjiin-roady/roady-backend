from collections.abc import Mapping, Sequence

import pytest

from app.services.navigation_tmap_service import (
    InvalidTmapCoordinateError,
    InvalidTmapRouteRequest,
    NavigationTmapService,
)


class FakeTmapClient:
    def __init__(self) -> None:
        self.routes: list[dict[str, object]] = []
        self.road_matches: list[list[dict[str, float]]] = []
        self.reverse_geocodes: list[tuple[float, float]] = []

    async def fetch_sdk_script(self) -> str:
        return "script"

    async def fetch_vendor_asset(self, asset_path: str) -> object:
        return {"assetPath": asset_path}

    async def search_pois(self, keyword: str) -> object:
        return {"keyword": keyword}

    async def get_route(self, route_request: Mapping[str, object]) -> object:
        self.routes.append(dict(route_request))
        return {"features": []}

    async def match_roads(self, coordinates: Sequence[dict[str, float]]) -> object:
        self.road_matches.append(list(coordinates))
        return {"matchedPoints": []}

    async def reverse_geocode(self, lat: float, lng: float) -> object:
        self.reverse_geocodes.append((lat, lng))
        return {"addressInfo": {"fullAddress": "서울"}}


async def test_search_pois_returns_empty_response_for_blank_keyword() -> None:
    service = NavigationTmapService(client=FakeTmapClient())  # type: ignore[arg-type]

    assert await service.search_pois(" ") == {"searchPoiInfo": {"pois": {"poi": []}}}


async def test_search_pois_passes_keyword_to_client() -> None:
    service = NavigationTmapService(client=FakeTmapClient())  # type: ignore[arg-type]

    assert await service.search_pois("서울역") == {"keyword": "서울역"}


async def test_get_route_rejects_missing_coordinates() -> None:
    service = NavigationTmapService(client=FakeTmapClient())  # type: ignore[arg-type]

    with pytest.raises(InvalidTmapRouteRequest):
        await service.get_route(
            {"origin": {"lat": 37.0}, "destination": {"lat": 37.1, "lng": 127.1}}
        )


async def test_get_route_passes_normalized_coordinates_and_search_option() -> None:
    client = FakeTmapClient()
    service = NavigationTmapService(client=client)  # type: ignore[arg-type]

    await service.get_route(
        {
            "origin": {"lat": "37.0", "lng": "127.0"},
            "destination": {"lat": 37.1, "lng": 127.1},
            "searchOption": "10",
        }
    )

    assert client.routes == [
        {
            "origin": {"lat": 37.0, "lng": 127.0},
            "destination": {"lat": 37.1, "lng": 127.1},
            "searchOption": "10",
        }
    ]


async def test_match_roads_returns_empty_for_less_than_two_coordinates() -> None:
    service = NavigationTmapService(client=FakeTmapClient())  # type: ignore[arg-type]

    assert await service.match_roads([{"lat": 37.0, "lng": 127.0}]) == {"matchedPoints": []}


async def test_match_roads_passes_normalized_coordinates() -> None:
    client = FakeTmapClient()
    service = NavigationTmapService(client=client)  # type: ignore[arg-type]

    await service.match_roads(
        [{"lat": "37.0", "lng": "127.0"}, {"lat": 37.1, "lng": 127.1}]
    )

    assert client.road_matches == [
        [{"lat": 37.0, "lng": 127.0}, {"lat": 37.1, "lng": 127.1}]
    ]


async def test_reverse_geocode_rejects_invalid_lat_lng() -> None:
    service = NavigationTmapService(client=FakeTmapClient())  # type: ignore[arg-type]

    with pytest.raises(InvalidTmapCoordinateError):
        await service.reverse_geocode(lat=None, lng="127.0")


async def test_reverse_geocode_passes_normalized_lat_lng() -> None:
    client = FakeTmapClient()
    service = NavigationTmapService(client=client)  # type: ignore[arg-type]

    await service.reverse_geocode(lat="37.5665", lng="126.978")

    assert client.reverse_geocodes == [(37.5665, 126.978)]
