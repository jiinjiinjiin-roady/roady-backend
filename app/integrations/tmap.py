import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

import httpx

TMAP_BASE_URL = "https://apis.openapi.sk.com/tmap"
TMAP_VENDOR_BASE_URL = "https://topopentile3.tmap.co.kr"
ALLOWED_ROUTE_SEARCH_OPTIONS = {"0", "1", "2", "3", "4", "10", "12", "19", "24"}

T = TypeVar("T")


class MissingTmapAppKeyError(RuntimeError):
    pass


class TtlAsyncRequestCache:
    def __init__(self, *, cache_ttl_ms: int, now: Callable[[], float] | None = None) -> None:
        self._cache_ttl_ms = cache_ttl_ms
        self._now = now or (lambda: time.monotonic() * 1000)
        self._entries: dict[str, tuple[float, asyncio.Task[object]]] = {}

    async def get(self, key: str, load: Callable[[], Awaitable[T]]) -> T:
        current_time = self._now()
        cached = self._entries.get(key)

        if cached is not None:
            expires_at, task = cached
            if expires_at > current_time:
                return await task  # type: ignore[no-any-return]

        task = asyncio.create_task(load())
        self._entries[key] = (current_time + self._cache_ttl_ms, task)  # type: ignore[arg-type]
        try:
            return await task
        except Exception:
            if self._entries.get(key, (None, None))[1] is task:
                self._entries.pop(key, None)
            raise


@dataclass(frozen=True)
class VendorAsset:
    data: bytes
    content_type: str


def create_tmap_sdk_url() -> str:
    return f"{TMAP_BASE_URL}/vectorjs?version=1"


def build_poi_search_params(keyword: str) -> dict[str, object]:
    return {
        "version": 1,
        "format": "json",
        "searchKeyword": keyword.strip(),
        "searchType": "all",
        "count": 20,
        "page": 1,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "multiPoint": "N",
        "searchtypCd": "A",
        "poiGroupYn": "N",
    }


def build_route_payload(
    *,
    origin: Mapping[str, float],
    destination: Mapping[str, float],
    search_option: object | None,
) -> dict[str, object]:
    normalized_search_option = str(search_option or "0")

    return {
        "startX": origin["lng"],
        "startY": origin["lat"],
        "endX": destination["lng"],
        "endY": destination["lat"],
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": (
            normalized_search_option
            if normalized_search_option in ALLOWED_ROUTE_SEARCH_OPTIONS
            else "0"
        ),
        "trafficInfo": "Y",
    }


def build_road_match_payload(coordinates: Sequence[Mapping[str, float]]) -> dict[str, str]:
    return {
        "responseType": "1",
        "coords": "|".join(
            f"{coordinate['lng']},{coordinate['lat']}" for coordinate in coordinates[:100]
        ),
    }


def build_reverse_geocode_params(*, lat: float, lng: float) -> dict[str, object]:
    return {
        "version": 1,
        "lat": lat,
        "lon": lng,
        "coordType": "WGS84GEO",
        "addressType": "A10",
    }


def create_safe_script_loader(src: str) -> str:
    encoded_src = json.dumps(src)
    return "\n".join(
        [
            "(function () {",
            "  if (window.Tmapv3) return;",
            "  var script = document.createElement('script');",
            f"  script.src = {encoded_src};",
            "  script.async = false;",
            "  document.head.appendChild(script);",
            "})();",
        ]
    )


def rewrite_sdk_script(script: str) -> str:
    rewritten_script = re.sub(
        r"https://topopentile[1-3]\.tmap\.co\.kr/",
        "/api/tmap/vendor/",
        script,
    )
    match = re.search(r"tmapjs3\.min\.js\?version=\d+", rewritten_script)

    if "scriptSDKV3" in rewritten_script and match:
        return create_safe_script_loader(f"/api/tmap/vendor/scriptSDKV3/{match.group(0)}")

    return rewritten_script


def normalize_vendor_asset_path(asset_path: str) -> str:
    if asset_path.startswith(("scriptSDKV2/", "scriptSDKV3/")):
        return asset_path

    return f"scriptSDKV3/{asset_path}"


class TmapProxyClient:
    def __init__(self, *, app_key: str, timeout_seconds: float, cache_ttl_ms: int) -> None:
        self._app_key = app_key
        self._timeout = timeout_seconds
        self._cache = TtlAsyncRequestCache(cache_ttl_ms=cache_ttl_ms)

    def _require_app_key(self) -> str:
        app_key = self._app_key.strip()
        if not app_key:
            raise MissingTmapAppKeyError("TMAP app key is not configured.")
        return app_key

    async def fetch_sdk_script(self) -> str:
        async def load() -> str:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    create_tmap_sdk_url(),
                    headers={"appKey": self._require_app_key()},
                )
                response.raise_for_status()
                return rewrite_sdk_script(response.text)

        return await self._cache.get("sdk-script", load)

    async def fetch_vendor_asset(self, asset_path: str) -> VendorAsset:
        normalized_asset_path = normalize_vendor_asset_path(asset_path)

        async def load() -> VendorAsset:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{TMAP_VENDOR_BASE_URL}/{normalized_asset_path}")
                response.raise_for_status()
                return VendorAsset(
                    data=response.content,
                    content_type=response.headers.get("content-type", "application/octet-stream"),
                )

        return await self._cache.get(f"asset:{normalized_asset_path}", load)

    async def search_pois(self, keyword: str) -> object:
        trimmed_keyword = keyword.strip()

        async def load() -> object:
            async with self._json_client() as client:
                response = await client.get(
                    "/pois",
                    params=build_poi_search_params(trimmed_keyword),
                )
                response.raise_for_status()
                return response.json()

        return await self._cache.get(f"pois:{trimmed_keyword}", load)

    async def get_route(self, route_request: Mapping[str, object]) -> object:
        origin = route_request["origin"]
        destination = route_request["destination"]
        if not isinstance(origin, Mapping) or not isinstance(destination, Mapping):
            raise TypeError("origin and destination must be mappings.")

        payload = build_route_payload(
            origin=origin,  # type: ignore[arg-type]
            destination=destination,  # type: ignore[arg-type]
            search_option=route_request.get("searchOption"),
        )

        async def load() -> object:
            async with self._json_client() as client:
                response = await client.post(
                    "/routes",
                    json=payload,
                    params={"version": 1, "format": "json"},
                )
                response.raise_for_status()
                return response.json()

        return await self._cache.get(f"route:{json.dumps(payload, sort_keys=True)}", load)

    async def match_roads(self, coordinates: Sequence[Mapping[str, float]]) -> object:
        payload = build_road_match_payload(coordinates)

        async def load() -> object:
            async with self._json_client() as client:
                response = await client.post(
                    "/road/matchToRoads",
                    data=payload,
                    params={"version": 1},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                return response.json()

        return await self._cache.get(f"road-match:{payload['coords']}", load)

    async def reverse_geocode(self, lat: float, lng: float) -> object:
        params = build_reverse_geocode_params(lat=lat, lng=lng)

        async def load() -> object:
            async with self._json_client() as client:
                response = await client.get("/geo/reversegeocoding", params=params)
                response.raise_for_status()
                return response.json()

        return await self._cache.get(f"reverse:{lat},{lng}", load)

    def _json_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=TMAP_BASE_URL,
            timeout=self._timeout,
            headers={
                "Accept": "application/json",
                "appKey": self._require_app_key(),
            },
        )
