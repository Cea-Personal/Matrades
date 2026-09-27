import httpx
import pytest

from modules.knowledge.youtube import (
    YouTubeVideo,
    fetch_video_transcripts,
    serpapi_discover,
    serpapi_search,
)


async def test_serpapi_search_only_discovers_video_metadata():
    async def handler(request):
        assert request.url.params["engine"] == "google"
        assert request.url.params["q"] == "site:youtube.com forex trading strategy"
        return httpx.Response(
            200,
            json={
                "video_results": [
                    {
                        "video_id": "abc123_XY",
                        "title": "Forex trading strategy",
                        "link": "https://www.youtube.com/watch?v=abc123_XY",
                        "snippet": "A trading overview",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await serpapi_search("serp-key", "forex trading strategy", client=client)
    assert result == [
        YouTubeVideo(
            video_id="abc123_XY",
            url="https://www.youtube.com/watch?v=abc123_XY",
            title="Forex trading strategy",
            description="A trading overview",
        )
    ]


async def test_transcript_stage_accepts_only_discovered_videos(monkeypatch):
    seen: list[str] = []

    async def fetch(video_id, languages):
        seen.append(video_id)
        return f"caption for {video_id}", languages[0]

    monkeypatch.setattr("modules.knowledge.youtube.fetch_transcript", fetch)
    videos = [
        YouTubeVideo("abc123_XY", "https://www.youtube.com/watch?v=abc123_XY", "One"),
        YouTubeVideo("def456_ZZ", "https://www.youtube.com/watch?v=def456_ZZ", "Two"),
    ]
    results = await fetch_video_transcripts(videos, languages=["en"], skip_video_ids={"def456_ZZ"})
    assert seen == ["abc123_XY"]
    assert results[0]["transcript"] == "caption for abc123_XY"
    assert results[1]["error"] == "already_scraped"


async def test_discovery_paginates_past_known_videos_without_following_provider_urls():
    calls = []

    async def handler(request):
        start = int(request.url.params["start"])
        calls.append(start)
        assert request.url.host == "serpapi.com"
        video_id = "known_123" if start == 0 else "fresh_456"
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "link": f"https://www.youtube.com/watch?v={video_id}",
                        "title": "Strategy",
                    }
                ],
                "serpapi_pagination": {"next": "https://example.invalid/search?start=20"}
                if start == 0
                else {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        batch = await serpapi_discover(
            "key",
            "forex",
            skip_video_ids={"known_123"},
            client=client,
        )
    assert calls == [0, 20]
    assert [video.video_id for video in batch.videos] == ["fresh_456"]
    assert batch.exhausted and batch.next_start == 0


async def test_discovery_resumes_without_discarding_unused_results_on_same_page():
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"link": f"https://youtu.be/video_{index:03}", "title": str(index)}
                    for index in range(8)
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await serpapi_discover("key", "forex", limit=5, client=client)
        second = await serpapi_discover(
            "key",
            "forex",
            limit=5,
            start=first.next_start,
            skip_video_ids={item.video_id for item in first.videos},
            client=client,
        )
    assert first.next_start == 0
    assert len(first.videos) == 5 and len(second.videos) == 3
    assert not {item.video_id for item in first.videos} & {item.video_id for item in second.videos}


async def test_discovery_stops_at_page_budget_and_saves_next_offset():
    calls = []

    async def handler(request):
        start = int(request.url.params["start"])
        calls.append(start)
        return httpx.Response(
            200,
            json={
                "organic_results": [],
                "serpapi_pagination": {"next": f"https://serpapi.com/search?start={start + 20}"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        batch = await serpapi_discover("key", "forex", client=client)
    assert calls == [0, 20, 40]
    assert batch.videos == [] and batch.next_start == 60 and not batch.exhausted


async def test_discovery_rejects_repeating_pagination_without_looping():
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "serpapi_pagination": {"next": "https://serpapi.com/search?start=0"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        batch = await serpapi_discover("key", "forex", client=client)
    assert batch.exhausted and batch.videos == []


@pytest.mark.parametrize("mode", ["http_error", "malformed_json"])
async def test_discovery_failures_are_provider_neutral(mode):
    async def handler(request):
        return httpx.Response(503) if mode == "http_error" else httpx.Response(200, text="not JSON")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="SerpApi discovery is unavailable or timed out"):
            await serpapi_discover("credential-must-not-leak", "forex", client=client)
