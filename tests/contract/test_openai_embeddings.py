import httpx

from modules.knowledge.openai_embeddings import openai_embeddings


async def test_openai_embedding_adapter_sends_ui_model_and_dimensions() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["model"] == "text-embedding-3-small"
        assert body["dimensions"] == 3
        assert body["input"] == ["knowledge query"]
        assert request.headers["Authorization"] == "Bearer project-key"
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vectors = await openai_embeddings(
            "project-key",
            ["knowledge query"],
            model="text-embedding-3-small",
            dimensions=3,
            client=client,
        )

    assert vectors == [[0.1, 0.2, 0.3]]
