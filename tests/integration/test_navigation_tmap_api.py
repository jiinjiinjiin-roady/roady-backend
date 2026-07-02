from collections.abc import Mapping

from app.api.navigation_tmap import get_navigation_tmap_service
from app.integrations.tmap import VendorAsset
from app.services.navigation_tmap_service import (
    InvalidTmapCoordinateError,
    InvalidTmapRouteRequest,
)


class FakeNavigationTmapService:
    async def fetch_sdk_script(self) -> str:
        return "window.Tmapv3 = {};"

    async def fetch_vendor_asset(self, asset_path: str) -> VendorAsset:
        return VendorAsset(
            data=f"asset:{asset_path}".encode(),
            content_type="application/javascript",
        )

    async def search_pois(self, keyword: str) -> object:
        return {"searchPoiInfo": {"pois": {"poi": []}}, "keyword": keyword}

    async def get_route(self, body: Mapping[str, object]) -> object:
        origin = body.get("origin")
        if not isinstance(origin, Mapping) or origin.get("lng") is None:
            raise InvalidTmapRouteRequest
        return {"features": [], "searchOption": body.get("searchOption")}

    async def match_roads(self, coordinates: object) -> object:
        return {"matchedPoints": [{"sourceIndex": 0}], "count": len(coordinates)}

    async def reverse_geocode(self, *, lat: object, lng: object) -> object:
        if lat is None or lng is None:
            raise InvalidTmapCoordinateError
        return {"addressInfo": {"fullAddress": f"{lat},{lng}"}}


async def test_tmap_sdk_route_returns_javascript(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.get("/api/tmap/sdk.js")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.text == "window.Tmapv3 = {};"


async def test_tmap_vendor_route_returns_asset(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.get("/api/tmap/vendor/scriptSDKV3/tmapjs3.min.js")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.content == b"asset:scriptSDKV3/tmapjs3.min.js"


async def test_pois_route_returns_service_response(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.get("/api/tmap/pois?keyword=서울역")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["keyword"] == "서울역"
    assert response.json()["searchPoiInfo"]["pois"]["poi"] == []


async def test_routes_rejects_invalid_coordinates(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.post(
            "/api/tmap/routes",
            json={
                "origin": {"lat": 37.0, "lng": None},
                "destination": {"lat": 37.1, "lng": 127.1},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"message": "origin and destination coordinates are required."}


async def test_routes_returns_service_response(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.post(
            "/api/tmap/routes",
            json={
                "origin": {"lat": 37.0, "lng": 127.0},
                "destination": {"lat": 37.1, "lng": 127.1},
                "searchOption": "10",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["searchOption"] == "10"


async def test_road_match_route_returns_service_response(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.post(
            "/api/tmap/road-match",
            json={"coordinates": [{"lat": 37.0, "lng": 127.0}, {"lat": 37.1, "lng": 127.1}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["count"] == 2


async def test_reverse_geocode_rejects_missing_lat_lng(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.get("/api/tmap/reverse-geocode?lat=37.0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"message": "lat and lng query params are required."}


async def test_reverse_geocode_route_returns_service_response(app, client) -> None:
    app.dependency_overrides[get_navigation_tmap_service] = lambda: FakeNavigationTmapService()
    try:
        response = await client.get("/api/tmap/reverse-geocode?lat=37.0&lng=127.0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["addressInfo"]["fullAddress"] == "37.0,127.0"
