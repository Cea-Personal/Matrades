"""SerpApi discovery and YouTube transcript ingestion primitives."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    url: str
    title: str
    description: str = ""


def video_id_from_url(value: str) -> str | None:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    else:
        match = re.search(r"/(?:shorts|embed)/([^/?]+)", parsed.path)
        candidate = match.group(1) if match else ""
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", candidate) else None


async def serpapi_search(
    api_key: str,
    query: str,
    *,
    limit: int = 5,
    client: httpx.AsyncClient | None = None,
) -> list[YouTubeVideo]:
    if not api_key:
        raise ValueError("SerpApi credential unavailable")
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=15, headers={"User-Agent": "Matrades/1"})
    try:
        response = await http.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": f"site:youtube.com {query}",
                "api_key": api_key,
                "num": min(max(limit * 2, 1), 20),
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("error"):
            raise RuntimeError("SerpApi rejected the search request")
        candidates = [*(body.get("video_results") or []), *(body.get("organic_results") or [])]
        results: list[YouTubeVideo] = []
        seen: set[str] = set()
        for item in candidates:
            link = str(item.get("link") or item.get("url") or "")
            video_id = str(item.get("video_id") or video_id_from_url(link) or "")
            if not video_id or video_id in seen:
                continue
            normalized_url = f"https://www.youtube.com/watch?v={video_id}"
            seen.add(video_id)
            results.append(
                YouTubeVideo(
                    video_id=video_id,
                    url=normalized_url,
                    title=str(item.get("title") or video_id),
                    description=str(item.get("snippet") or item.get("description") or ""),
                )
            )
            if len(results) >= limit:
                break
        return results
    finally:
        if owns_client:
            await http.aclose()


def _fetch_transcript_sync(video_id: str, languages: list[str]) -> tuple[str, str | None]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is not installed") from exc
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=languages)
    snippets: list[str] = []
    language = getattr(transcript, "language_code", None)
    for snippet in transcript:
        value = getattr(snippet, "text", None)
        if value is None and isinstance(snippet, dict):
            value = snippet.get("text")
        if value:
            snippets.append(str(value))
    text = " ".join(snippets).strip()
    if not text:
        raise RuntimeError("YouTube transcript was empty")
    return text, str(language) if language else None


async def fetch_transcript(
    video_id: str, languages: list[str] | None = None
) -> tuple[str, str | None]:
    return await asyncio.to_thread(_fetch_transcript_sync, video_id, languages or ["en"])


async def fetch_video_transcripts(
    videos: list[YouTubeVideo],
    *,
    languages: list[str] | None = None,
    skip_video_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch transcripts for an already-discovered, bounded video set."""
    results: list[dict[str, Any]] = []
    skipped = skip_video_ids or set()
    for video in videos:
        if video.video_id in skipped:
            results.append(
                {"video": video, "transcript": None, "language": None, "error": "already_scraped"}
            )
            continue
        try:
            transcript, language = await fetch_transcript(video.video_id, languages)
            results.append(
                {"video": video, "transcript": transcript, "language": language, "error": None}
            )
        except Exception as exc:  # noqa: BLE001 - one unavailable video must not stop the cycle
            results.append(
                {
                    "video": video,
                    "transcript": None,
                    "language": None,
                    "error": type(exc).__name__,
                }
            )
    return results


async def scrape_youtube_transcripts(
    api_key: str,
    query: str,
    *,
    limit: int = 5,
    languages: list[str] | None = None,
    skip_video_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    videos = await serpapi_search(api_key, query, limit=limit)
    return await fetch_video_transcripts(videos, languages=languages, skip_video_ids=skip_video_ids)
