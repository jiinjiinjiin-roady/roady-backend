import math
from collections.abc import Mapping, Sequence

from app.integrations.tmap import TmapProxyClient, VendorAsset


class InvalidTmapRouteRequest(ValueError):
    pass


class InvalidTmapCoordinateError(ValueError):
    pass


class NavigationTmapService:
    def __init__(self, *, client: TmapProxyClient) -> None:
        self._client = client

    async def fetch_sdk_script(self) -> str:
        return await self._client.fetch_sdk_script()

    async def fetch_vendor_asset(self, asset_path: str) -> VendorAsset:
        return await self._client.fetch_vendor_asset(asset_path)

    async def search_pois(self, keyword: str) -> object:
        if not keyword.strip():
            return {"searchPoiInfo": {"pois": {"poi": []}}}
        return await self._client.search_pois(keyword)

    async def get_route(self, body: Mapping[str, object]) -> object:
        origin = normalize_coordinate(body.get("origin"))
        destination = normalize_coordinate(body.get("destination"))

        if origin is None or destination is None:
            raise InvalidTmapRouteRequest

        return await self._client.get_route(
            {
                **body,
                "origin": origin,
                "destination": destination,
            }
        )

    async def match_roads(self, coordinates: object) -> object:
        normalized_coordinates = normalize_coordinate_list(coordinates)

        if len(normalized_coordinates) < 2:
            return {"matchedPoints": []}

        return await self._client.match_roads(normalized_coordinates)

    async def reverse_geocode(self, *, lat: object, lng: object) -> object:
        coordinate = normalize_coordinate({"lat": lat, "lng": lng})

        if coordinate is None:
            raise InvalidTmapCoordinateError

        return await self._client.reverse_geocode(coordinate["lat"], coordinate["lng"])


def normalize_coordinate(value: object) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None

    lat = normalize_coordinate_value(value.get("lat"))
    lng = normalize_coordinate_value(value.get("lng"))

    if lat is None or lng is None:
        return None

    return {"lat": lat, "lng": lng}


def normalize_coordinate_value(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, str) and not value.strip():
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def normalize_coordinate_list(value: object) -> list[dict[str, float]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []

    return [
        coordinate
        for item in value
        if (coordinate := normalize_coordinate(item)) is not None
    ]
