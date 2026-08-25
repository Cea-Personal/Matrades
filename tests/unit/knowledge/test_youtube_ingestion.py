from modules.knowledge.ingestion import build_source_data, token_embedding
from modules.knowledge.youtube import video_id_from_url


def test_youtube_video_id_normalization_and_invalid_urls() -> None:
    assert video_id_from_url("https://www.youtube.com/watch?v=abc123_XY") == "abc123_XY"
    assert video_id_from_url("https://youtu.be/abc123_XY?t=30") == "abc123_XY"
    assert video_id_from_url("https://example.com/watch?v=abc123_XY") is None


def test_ingestion_is_deterministic_and_indexes_vectors() -> None:
    first = build_source_data(name="strategy", content="Trend following with moving average")
    second = build_source_data(name="strategy", content="Trend following with moving average")
    assert first["content_hash"] == second["content_hash"]
    assert first["segments"][0]["embedding"] == second["segments"][0]["embedding"]
    assert first["vector_index_state"] == "INDEXED"
    assert len(token_embedding("trend following")) == 64
