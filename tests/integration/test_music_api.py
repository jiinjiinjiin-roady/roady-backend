import httpx
import pytest


@pytest.mark.asyncio
async def test_music_recommendations_returns_backend_fallback_when_provider_fails(
    client,
    monkeypatch,
) -> None:
    class FailingMusicClient:
        async def search_tracks(self, term: str, limit: int) -> object:
            raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(
        "app.api.v1.endpoints.music.ItunesSearchClient",
        lambda: FailingMusicClient(),
    )

    response = await client.get("/api/v1/music/recommendations?mood=bright&limit=1")

    assert response.status_code == 200
    assert response.json() == {
        "tracks": [
            {
                "id": "demo-fallback-bright-road",
                "title": "Bright Road",
                "artist": "Roady Session",
                "album": "Wake Drive",
                "duration": "2:58",
                "durationSeconds": 178,
                "coverUrl": None,
                "sourceUrl": "",
                "provider": "demo-fallback",
            }
        ]
    }
