import pytest

from app.integrations.tmap import (
    MissingTmapAppKeyError,
    TmapProxyClient,
    build_poi_search_params,
    build_reverse_geocode_params,
    build_road_match_payload,
    build_route_payload,
    normalize_vendor_asset_path,
    rewrite_sdk_script,
)


def test_build_poi_search_params() -> None:
    assert build_poi_search_params(" 서울역 ") == {
        "version": 1,
        "format": "json",
        "searchKeyword": "서울역",
        "searchType": "all",
        "count": 20,
        "page": 1,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "multiPoint": "N",
        "searchtypCd": "A",
        "poiGroupYn": "N",
    }


def test_build_route_payload_preserves_allowed_search_option() -> None:
    payload = build_route_payload(
        origin={"lat": 37.5665, "lng": 126.978},
        destination={"lat": 37.4979, "lng": 127.0276},
        search_option="10",
    )

    assert payload == {
        "startX": 126.978,
        "startY": 37.5665,
        "endX": 127.0276,
        "endY": 37.4979,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "10",
        "trafficInfo": "Y",
    }


def test_build_route_payload_falls_back_to_recommended() -> None:
    payload = build_route_payload(
        origin={"lat": 37.5665, "lng": 126.978},
        destination={"lat": 37.4979, "lng": 127.0276},
        search_option="99",
    )

    assert payload["searchOption"] == "0"
    assert payload["trafficInfo"] == "Y"


def test_build_road_match_payload_limits_to_100_lng_lat_pairs() -> None:
    coordinates = [
        {"lat": float(index), "lng": float(index + 1000)}
        for index in range(101)
    ]

    payload = build_road_match_payload(coordinates)

    assert payload["responseType"] == "1"
    assert payload["coords"].count("|") == 99
    assert payload["coords"].split("|")[0] == "1000.0,0.0"
    assert payload["coords"].split("|")[-1] == "1099.0,99.0"


def test_build_reverse_geocode_params_uses_tmap_lon_name() -> None:
    assert build_reverse_geocode_params(lat=37.5665, lng=126.978) == {
        "version": 1,
        "lat": 37.5665,
        "lon": 126.978,
        "coordType": "WGS84GEO",
        "addressType": "A10",
    }


def test_rewrite_sdk_script_uses_local_vendor_proxy() -> None:
    script = (
        'document.write("<script src=\\"https://topopentile3.tmap.co.kr/scriptSDKV3/'
        'tmapjs3.min.js?version=20231206\\"></script>")'
    )

    rewritten = rewrite_sdk_script(script)

    assert "/api/tmap/vendor/scriptSDKV3/tmapjs3.min.js?version=20231206" in rewritten
    assert "document.write" not in rewritten
    assert "topopentile" not in rewritten


def test_normalize_vendor_asset_path() -> None:
    assert normalize_vendor_asset_path("scriptSDKV3/tmapjs3.min.js") == (
        "scriptSDKV3/tmapjs3.min.js"
    )
    assert normalize_vendor_asset_path("tmapjs3.min.js") == "scriptSDKV3/tmapjs3.min.js"


async def test_tmap_client_rejects_missing_app_key_before_external_request() -> None:
    client = TmapProxyClient(app_key="", timeout_seconds=10, cache_ttl_ms=30_000)

    with pytest.raises(MissingTmapAppKeyError):
        await client.search_pois("서울역")
