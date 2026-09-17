import httpx

from modules.knowledge.youtube import (
    YouTubeVideo,
    fetch_video_transcripts,
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
