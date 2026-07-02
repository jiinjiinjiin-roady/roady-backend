from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response

from app.api.dependencies import AppSettings
from app.integrations.tmap import MissingTmapAppKeyError, TmapProxyClient
from app.services.navigation_tmap_service import (
    InvalidTmapCoordinateError,
    InvalidTmapRouteRequest,
    NavigationTmapService,
)

router = APIRouter(include_in_schema=False)


def get_navigation_tmap_service(settings: AppSettings) -> NavigationTmapService:
    client = TmapProxyClient(
        app_key=settings.tmap_app_key,
        timeout_seconds=settings.tmap_request_timeout_seconds,
        cache_ttl_ms=settings.tmap_proxy_cache_ttl_ms,
    )
    return NavigationTmapService(client=client)


NavigationTmapServiceDep = Annotated[
    NavigationTmapService,
    Depends(get_navigation_tmap_service),
]


async def call_tmap(operation: Callable[[], Awaitable[object]]) -> object | JSONResponse:
    try:
        return await operation()
    except MissingTmapAppKeyError:
        return JSONResponse(
            {"message": "TMAP app key is not configured."},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            {"message": "TMAP proxy request failed.", "detail": str(exc)},
            status_code=exc.response.status_code,
        )
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"message": "TMAP proxy request failed.", "detail": str(exc)},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


def to_json_response(result: object | JSONResponse) -> JSONResponse:
    if isinstance(result, JSONResponse):
        return result
    return JSONResponse(result)


@router.get("/api/tmap/sdk.js", response_model=None)
async def get_tmap_sdk(service: NavigationTmapServiceDep):
    result = await call_tmap(service.fetch_sdk_script)
    if isinstance(result, JSONResponse):
        return result
    return Response(content=result, media_type="application/javascript")


@router.get("/api/tmap/vendor/{asset_path:path}", response_model=None)
async def get_tmap_vendor_asset(
    asset_path: str,
    service: NavigationTmapServiceDep,
):
    result = await call_tmap(lambda: service.fetch_vendor_asset(asset_path))
    if isinstance(result, JSONResponse):
        return result
    return Response(content=result.data, media_type=result.content_type)


@router.get("/api/tmap/pois")
async def search_tmap_pois(
    service: NavigationTmapServiceDep,
    keyword: str = "",
) -> JSONResponse:
    result = await call_tmap(lambda: service.search_pois(keyword))
    return to_json_response(result)


@router.post("/api/tmap/routes")
async def get_tmap_route(
    request: Request,
    service: NavigationTmapServiceDep,
) -> JSONResponse:
    body = await request.json()

    try:
        result = await call_tmap(lambda: service.get_route(body if isinstance(body, dict) else {}))
    except InvalidTmapRouteRequest:
        return JSONResponse(
            {"message": "origin and destination coordinates are required."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return to_json_response(result)


@router.post("/api/tmap/road-match")
async def match_tmap_road(
    request: Request,
    service: NavigationTmapServiceDep,
) -> JSONResponse:
    body = await request.json()
    coordinates = body.get("coordinates") if isinstance(body, dict) else []
    result = await call_tmap(lambda: service.match_roads(coordinates))
    return to_json_response(result)


@router.get("/api/tmap/reverse-geocode")
async def reverse_geocode_tmap(
    service: NavigationTmapServiceDep,
    lat: str | None = None,
    lng: str | None = None,
) -> JSONResponse:
    try:
        result = await call_tmap(lambda: service.reverse_geocode(lat=lat, lng=lng))
    except InvalidTmapCoordinateError:
        return JSONResponse(
            {"message": "lat and lng query params are required."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return to_json_response(result)
