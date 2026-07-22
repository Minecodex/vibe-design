import pytest

from app.services import search_runtime


class _FakeDDGS:
    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def text(self, query, *, region, safesearch, timelimit, max_results, backend):
        assert query == "latest ai search"
        assert region == "wt-wt"
        assert safesearch == "moderate"
        assert timelimit is None
        assert max_results == 3
        assert backend == "auto"
        return [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
            {"title": "Result 3", "href": "https://example.com/3", "body": "Snippet 3"},
        ]

    def images(self, query, *, region, safesearch, timelimit, max_results, backend):
        assert query == "nietzsche portrait"
        assert region == "wt-wt"
        assert safesearch == "moderate"
        assert timelimit is None
        assert max_results == 2
        assert backend == "auto"
        return [
            {
                "title": "Nietzsche Portrait 1",
                "image": "https://images.example.com/1.jpg",
                "thumbnail": "https://images.example.com/thumb1.jpg",
                "url": "https://source.example.com/1",
                "width": 1024,
                "height": 768,
            },
            {
                "title": "Nietzsche Portrait 2",
                "image": "https://images.example.com/2.jpg",
                "thumbnail": "https://images.example.com/thumb2.jpg",
                "url": "https://source.example.com/2",
            },
        ]


@pytest.mark.asyncio
async def test_search_web_uses_duckduckgo_runtime(monkeypatch):
    monkeypatch.setattr(search_runtime.settings, "SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.setattr(search_runtime.settings, "SEARCH_MAX_RESULTS", 10)
    monkeypatch.setattr(search_runtime.settings, "SEARCH_TIMEOUT_SECONDS", 8)
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_REGION", "wt-wt")
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_SAFESEARCH", "moderate")
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_TIME_LIMIT", "")
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_BACKEND", "auto")

    monkeypatch.setattr(
        search_runtime,
        "_run_duckduckgo_search",
        lambda query, num_results: [
            {
                "title": item["title"],
                "url": item["href"],
                "snippet": item["body"],
            }
            for item in _FakeDDGS(timeout=8).text(
                query,
                region="wt-wt",
                safesearch="moderate",
                timelimit=None,
                max_results=num_results,
                backend="auto",
            )
        ],
    )

    result = await search_runtime.search_web("latest ai search", num_results=3)

    assert result["provider"] == "duckduckgo"
    assert result["query"] == "latest ai search"
    assert len(result["results"]) == 3
    assert result["results"][0]["url"] == "https://example.com/1"
    assert result["search_type"] == "text"


@pytest.mark.asyncio
async def test_search_web_supports_image_results(monkeypatch):
    monkeypatch.setattr(search_runtime.settings, "SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.setattr(search_runtime.settings, "SEARCH_MAX_RESULTS", 10)
    monkeypatch.setattr(search_runtime.settings, "SEARCH_TIMEOUT_SECONDS", 8)
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_REGION", "wt-wt")
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_SAFESEARCH", "moderate")
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_TIME_LIMIT", "")
    monkeypatch.setattr(search_runtime.settings, "DUCKDUCKGO_BACKEND", "auto")

    monkeypatch.setattr(
        search_runtime,
        "_run_duckduckgo_image_search",
        lambda query, num_results: [
            {
                "title": item["title"],
                "image_url": item["image"],
                "thumbnail_url": item["thumbnail"],
                "source_url": item["url"],
                "width": item.get("width"),
                "height": item.get("height"),
            }
            for item in _FakeDDGS(timeout=8).images(
                query,
                region="wt-wt",
                safesearch="moderate",
                timelimit=None,
                max_results=num_results,
                backend="auto",
            )
        ],
    )

    result = await search_runtime.search_web(
        "nietzsche portrait",
        num_results=2,
        search_type="image",
    )

    assert result["provider"] == "duckduckgo"
    assert result["search_type"] == "image"
    assert len(result["results"]) == 2
    assert result["results"][0]["image_url"] == "https://images.example.com/1.jpg"
    assert result["results"][0]["source_url"] == "https://source.example.com/1"


@pytest.mark.asyncio
async def test_search_web_retries_transient_text_errors(monkeypatch):
    monkeypatch.setattr(search_runtime.settings, "SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.setattr(search_runtime.settings, "SEARCH_MAX_RESULTS", 10)
    monkeypatch.setattr(search_runtime.random, "uniform", lambda *_args: 0)

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(search_runtime.asyncio, "sleep", fake_sleep)

    attempts = 0

    class ConnectError(Exception):
        pass

    def flaky_text_search(query: str, num_results: int):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectError("tls handshake eof")
        return [{"title": "ok", "url": "https://example.com", "snippet": "done"}]

    monkeypatch.setattr(search_runtime, "_run_duckduckgo_search", flaky_text_search)

    result = await search_runtime.search_web("latest ai search", num_results=3, search_type="text")

    assert attempts == 3
    assert sleeps == [0.5, 1.0]
    assert result["search_type"] == "text"
    assert result["results"][0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_search_web_retries_transient_image_errors(monkeypatch):
    monkeypatch.setattr(search_runtime.settings, "SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.setattr(search_runtime.settings, "SEARCH_MAX_RESULTS", 10)
    monkeypatch.setattr(search_runtime.random, "uniform", lambda *_args: 0)

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(search_runtime.asyncio, "sleep", fake_sleep)

    attempts = 0

    def flaky_image_search(query: str, num_results: int):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("timed out")
        return [{"title": "portrait", "image_url": "https://images.example.com/nietzsche.jpg"}]

    monkeypatch.setattr(search_runtime, "_run_duckduckgo_image_search", flaky_image_search)

    result = await search_runtime.search_web("nietzsche portrait", num_results=2, search_type="image")

    assert attempts == 2
    assert sleeps == [0.5]
    assert result["search_type"] == "image"
    assert result["results"][0]["image_url"] == "https://images.example.com/nietzsche.jpg"


@pytest.mark.asyncio
async def test_search_web_rejects_empty_queries():
    with pytest.raises(ValueError, match="cannot be empty"):
        await search_runtime.search_web("   ")


@pytest.mark.asyncio
async def test_search_web_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(search_runtime.settings, "SEARCH_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported search provider"):
        await search_runtime.search_web("latest ai search")


@pytest.mark.asyncio
async def test_search_web_rejects_unsupported_search_type():
    with pytest.raises(ValueError, match="Unsupported search type"):
        await search_runtime.search_web("latest ai search", search_type="video")
