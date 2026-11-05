"""Ported from document-buddy (tests/test_ai_providers.py) without the vision OCR cases.

Provider adapters against mock HTTP transports: the requests they send and how they read
streams, answers and errors. No network; the wire formats are the providers' own."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx
import httpx2
import openai
import pytest

from pdf_assistant.ai import AiConfigError, AiError, Provider
from pdf_assistant.ai.claude_models import FALLBACK_BETA, ClaudeChat, claude_messages
from pdf_assistant.ai.factory import (
    ModelRef,
    azure_v1_url,
    build_chat_models,
    build_embedder,
    chat_model_refs,
    parse_model_ref,
)
from pdf_assistant.ai.openai_models import OpenAIChat, OpenAIEmbedder
from pdf_assistant.settings import Settings

Seen = list[dict[str, Any]]


def _sse(events: list[tuple[str | None, dict[str, Any] | str]]) -> bytes:
    lines = []
    for name, data in events:
        if name:
            lines.append(f"event: {name}")
        lines.append(f"data: {data if isinstance(data, str) else json.dumps(data)}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode()


def _recorder(seen: Seen, respond: Callable[[dict[str, Any]], tuple[int, bytes, str]]) -> Callable[..., Any]:
    def handler(request: Any) -> Any:
        body = json.loads(request.content or b"{}")
        seen.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        status, content, content_type = respond(body)
        response_cls = httpx2.Response if isinstance(request, httpx2.Request) else httpx.Response
        return response_cls(status, content=content, headers={"content-type": content_type})

    return handler


# ------------------------------------------------------------------ OpenAI-compatible


def _openai(seen: Seen, respond: Callable[[dict[str, Any]], tuple[int, bytes, str]], *, async_client: bool) -> Any:
    transport = httpx.MockTransport(_recorder(seen, respond))
    if async_client:
        return openai.AsyncOpenAI(
            api_key="k", base_url="http://test/v1", max_retries=0, http_client=httpx.AsyncClient(transport=transport)
        )
    return openai.OpenAI(
        api_key="k", base_url="http://test/v1", max_retries=0, http_client=httpx.Client(transport=transport)
    )


def _chunk(content: str) -> dict[str, Any]:
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }


def _completion(content: str) -> bytes:
    return json.dumps(
        {
            "id": "c",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        }
    ).encode()


async def _collect(stream: Any) -> list[str]:
    return [piece async for piece in stream]


def test_openai_chat_streams_with_the_system_prompt_first() -> None:
    seen: Seen = []
    stream = _sse([(None, _chunk("Rok je ")), (None, _chunk("30 dana [1].")), (None, "[DONE]")])
    chat = OpenAIChat(_openai(seen, lambda _: (200, stream, "text/event-stream"), async_client=True), model="gpt-x")

    pieces = asyncio.run(_collect(chat.stream(system="S", messages=[{"role": "user", "content": "Rok?"}])))

    assert pieces == ["Rok je ", "30 dana [1]."]
    [request] = seen
    assert request["url"] == "http://test/v1/chat/completions"
    assert request["body"]["stream"] is True and request["body"]["model"] == "gpt-x"
    assert request["body"]["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "Rok?"}]


def test_openai_errors_become_ai_errors_without_the_key() -> None:
    seen: Seen = []
    message = "Incorrect API key provided: sk-proj-abc123****wxyz. You can find your API key at ..."
    error = json.dumps({"error": {"message": message, "type": "invalid_request_error"}}).encode()
    chat = OpenAIChat(_openai(seen, lambda _: (401, error, "application/json"), async_client=True), model="m")
    with pytest.raises(AiError, match="401") as raised:
        asyncio.run(_collect(chat.stream(system="S", messages=[{"role": "user", "content": "x"}])))
    assert "abc123" not in str(raised.value) and "sk-***" in str(raised.value)
    with pytest.raises(AiError, match="401"):
        asyncio.run(chat.complete(system="S", messages=[{"role": "user", "content": "x"}]))


def test_openai_embeddings_keep_input_order_and_send_dimensions() -> None:
    seen: Seen = []
    data = {
        "object": "list",
        "model": "m",
        "data": [
            {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
            {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
        ],
        "usage": {"prompt_tokens": 2, "total_tokens": 2},
    }
    embedder = OpenAIEmbedder(
        _openai(seen, lambda _: (200, json.dumps(data).encode(), "application/json"), async_client=False),
        model="text-embedding-3-small",
        dimensions=2,
        document_prefix="doc: ",
    )

    assert embedder.embed_documents(["prvi", "drugi"]) == [[1.0, 0.0], [0.0, 1.0]]
    body = seen[0]["body"]
    assert body == {
        "model": "text-embedding-3-small",
        "input": ["doc: prvi", "doc: drugi"],
        "encoding_format": "float",
        "dimensions": 2,
    }


# ------------------------------------------------------------------ Claude


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _claude_stream(pieces: list[str], stop_reason: str = "end_turn") -> bytes:
    start = _message("", stop_reason="")
    start["stop_reason"] = None
    events: list[tuple[str | None, dict[str, Any] | str]] = [
        ("message_start", {"type": "message_start", "message": start}),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
    ]
    for piece in pieces:
        delta = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": piece}}
        events.append(("content_block_delta", delta))
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return _sse(events)


def _anthropic(seen: Seen, respond: Callable[[dict[str, Any]], tuple[int, bytes, str]], *, async_client: bool) -> Any:
    transport = httpx2.MockTransport(_recorder(seen, respond))
    if async_client:
        return anthropic.AsyncAnthropic(
            api_key="k", base_url="http://test", max_retries=0, http_client=httpx2.AsyncClient(transport=transport)
        )
    return anthropic.Anthropic(
        api_key="k", base_url="http://test", max_retries=0, http_client=httpx2.Client(transport=transport)
    )


def test_claude_chat_streams_with_effort_and_server_side_fallback() -> None:
    seen: Seen = []
    client = _anthropic(
        seen, lambda _: (200, _claude_stream(["Rok je ", "30 dana."]), "text/event-stream"), async_client=True
    )
    chat = ClaudeChat(client, model="claude-opus-5-5", effort="low", fallbacks=True)

    messages = [{"role": "assistant", "content": "orphan"}, {"role": "user", "content": "Rok?"}]
    assert asyncio.run(_collect(chat.stream(system="S", messages=messages))) == ["Rok je ", "30 dana."]

    [request] = seen
    body = request["body"]
    assert request["url"].startswith("http://test/v1/messages")
    assert FALLBACK_BETA in request["headers"]["anthropic-beta"]
    assert (body["model"], body["system"], body["fallbacks"], body["output_config"]) == (
        "claude-opus-5-5",
        "S",
        "default",
        {"effort": "low"},
    )
    assert body["messages"] == [{"role": "user", "content": "Rok?"}]  # a leading assistant turn is dropped
    assert body["stream"] is True and body["max_tokens"] >= 16000


def test_claude_without_fallbacks_sends_no_beta() -> None:
    seen: Seen = []
    client = _anthropic(seen, lambda _: (200, _claude_stream(["ok"]), "text/event-stream"), async_client=True)
    chat = ClaudeChat(client, model="claude-haiku-5-5", effort="", fallbacks=False)
    asyncio.run(_collect(chat.stream(system="S", messages=[{"role": "user", "content": "x"}])))
    assert "anthropic-beta" not in seen[0]["headers"]
    assert "fallbacks" not in seen[0]["body"] and "output_config" not in seen[0]["body"]


def test_claude_refusal_is_an_error_after_the_partial_answer() -> None:
    seen: Seen = []
    client = _anthropic(
        seen, lambda _: (200, _claude_stream(["Pocetak"], "refusal"), "text/event-stream"), async_client=True
    )
    chat = ClaudeChat(client, model="claude-opus-5-5")
    pieces: list[str] = []

    async def run() -> None:
        async for piece in chat.stream(system="S", messages=[{"role": "user", "content": "x"}]):
            pieces.append(piece)

    with pytest.raises(AiError, match="refusal"):
        asyncio.run(run())
    assert pieces == ["Pocetak"]


def test_claude_complete_returns_the_text_and_refusal_is_an_error() -> None:
    seen: Seen = []
    rewrite = _anthropic(
        seen, lambda _: (200, json.dumps(_message("Koja je kazna?")).encode(), "application/json"), async_client=True
    )
    assert (
        asyncio.run(ClaudeChat(rewrite, model="m").complete(system="S", messages=[{"role": "user", "content": "x"}]))
        == "Koja je kazna?"
    )

    refused = _anthropic(
        seen, lambda _: (200, json.dumps(_message("", "refusal")).encode(), "application/json"), async_client=True
    )
    with pytest.raises(AiError, match="refusal"):
        asyncio.run(ClaudeChat(refused, model="m").complete(system="S", messages=[{"role": "user", "content": "x"}]))


def test_claude_api_errors_become_ai_errors() -> None:
    seen: Seen = []
    error = json.dumps(
        {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    ).encode()
    client = _anthropic(seen, lambda _: (401, error, "application/json"), async_client=True)
    with pytest.raises(AiError, match="401"):
        asyncio.run(
            _collect(ClaudeChat(client, model="m").stream(system="S", messages=[{"role": "user", "content": "x"}]))
        )


class _BrokenBody(httpx2.AsyncByteStream):
    """An SSE body that delivers some events, then the connection fails."""

    def __init__(self, chunks: list[bytes], error: Exception) -> None:
        self.chunks, self.error = chunks, error

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        for chunk in self.chunks:
            yield chunk
        raise self.error


@pytest.mark.parametrize("fallbacks", [False, True])
@pytest.mark.parametrize("error", [httpx2.ReadTimeout("read timed out"), httpx2.RemoteProtocolError("peer closed")])
def test_claude_stream_failing_after_the_first_token_is_an_ai_error(fallbacks: bool, error: Exception) -> None:
    # Regression: anthropic 2.x does not wrap errors raised while reading a stream, so a
    # dropped connection mid-answer escaped as httpx2 and the chat stream ended without
    # an error event.
    body = _claude_stream(["Pocetak"]).split(b"event: content_block_stop")[0]

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=_BrokenBody([body], error))

    client = anthropic.AsyncAnthropic(
        api_key="k",
        base_url="http://test",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    pieces: list[str] = []

    async def run() -> None:
        async for piece in ClaudeChat(client, model="claude-opus-5-5", fallbacks=fallbacks).stream(
            system="S", messages=[{"role": "user", "content": "x"}]
        ):
            pieces.append(piece)

    with pytest.raises(AiError):
        asyncio.run(run())
    assert pieces == ["Pocetak"]


def test_claude_messages_drop_empty_turns() -> None:
    turns = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "  "}, {"role": "user", "content": "b"}]
    assert claude_messages(turns) == [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]


# ------------------------------------------------------------------ factory


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_model_refs_take_an_optional_provider_prefix() -> None:
    assert parse_model_ref("claude-opus-5-5", Provider.ANTHROPIC) == ModelRef(Provider.ANTHROPIC, "claude-opus-5-5")
    assert parse_model_ref("openai:gpt-5.1", Provider.ANTHROPIC) == ModelRef(Provider.OPENAI, "gpt-5.1")
    # Ollama tags have their own colon; only a provider name counts as a prefix.
    assert parse_model_ref("gemma4:31b-cloud", Provider.OLLAMA) == ModelRef(Provider.OLLAMA, "gemma4:31b-cloud")
    assert parse_model_ref("ollama:gemma4:31b-cloud", Provider.OPENAI) == ModelRef(Provider.OLLAMA, "gemma4:31b-cloud")
    with pytest.raises(AiConfigError, match="twice"):
        chat_model_refs(_settings(chat_models="claude-opus-5-5,anthropic:claude-opus-5-5"))


def test_factory_builds_each_provider_and_names_missing_variables() -> None:
    with pytest.raises(AiConfigError, match="ANTHROPIC_API_KEY"):
        build_chat_models(_settings(chat_provider=Provider.ANTHROPIC))
    with pytest.raises(AiConfigError, match="OPENAI_API_KEY"):
        build_embedder(_settings())
    with pytest.raises(AiConfigError, match="AZURE_OPENAI_ENDPOINT"):
        build_embedder(_settings(embedding_provider=Provider.AZURE_OPENAI, azure_openai_api_key="k"))
    with pytest.raises(AiConfigError, match="ANTHROPIC_FOUNDRY_RESOURCE"):
        build_chat_models(_settings(chat_provider=Provider.ANTHROPIC_FOUNDRY, anthropic_foundry_api_key="k"))
    with pytest.raises(AiConfigError, match="no embeddings API"):
        build_embedder(_settings(embedding_provider=Provider.ANTHROPIC, anthropic_api_key="k"))
    with pytest.raises(AiConfigError, match="OPENAI_API_KEY"):
        build_chat_models(_settings(anthropic_api_key="k", chat_models="claude-opus-5-5,openai:gpt-5.1"))

    models = build_chat_models(_settings(anthropic_api_key="k"))
    assert list(models) == ["anthropic:claude-opus-5-5", "anthropic:claude-sonnet-5-5"]
    opus = models["anthropic:claude-opus-5-5"]
    assert isinstance(opus, ClaudeChat) and opus._requests.fallbacks  # Claude API + Opus 5.5
    assert opus.name == "claude-opus-5-5"

    foundry = build_chat_models(
        _settings(
            chat_provider=Provider.ANTHROPIC_FOUNDRY, anthropic_foundry_resource="eg", anthropic_foundry_api_key="k"
        )
    )["anthropic-foundry:claude-opus-5-5"]
    assert isinstance(foundry, ClaudeChat) and not foundry._requests.fallbacks
    assert str(foundry._client.base_url) == "https://eg.services.ai.azure.com/anthropic/"

    azure = build_embedder(
        _settings(
            embedding_provider=Provider.AZURE_OPENAI,
            azure_openai_endpoint="https://eg.openai.azure.com",
            azure_openai_api_key="k",
        )
    )
    assert isinstance(azure, OpenAIEmbedder) and str(azure._client.base_url) == "https://eg.openai.azure.com/openai/v1/"

    mixed = build_chat_models(_settings(chat_provider=Provider.OLLAMA, chat_models="llama3.2,ollama:gemma4:31b-cloud"))
    assert list(mixed) == ["ollama:llama3.2", "ollama:gemma4:31b-cloud"]
    ollama = mixed["ollama:llama3.2"]
    assert isinstance(ollama, OpenAIChat) and str(ollama._client.base_url) == "http://127.0.0.1:11434/v1/"
    assert ollama._client is mixed["ollama:gemma4:31b-cloud"]._client  # type: ignore[attr-defined]


def test_azure_url_accepts_the_resource_or_the_v1_url() -> None:
    for endpoint in (
        "https://eg.openai.azure.com",
        "https://eg.openai.azure.com/",
        "https://eg.openai.azure.com/openai/v1/",
    ):
        assert azure_v1_url(endpoint) == "https://eg.openai.azure.com/openai/v1/"


def test_empty_environment_values_mean_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # docker compose passes unset variables as "": that must not count as a key.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    settings = _settings()
    assert settings.anthropic_api_key is None and settings.qdrant_url is None


def test_list_settings_are_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODELS", "claude-opus-5-5, openai:gpt-5.1")
    monkeypatch.setenv("RETRIEVER_TOP_K", "4,6")
    monkeypatch.setenv("MEMORY_TURNS", "0")
    settings = _settings()
    assert settings.chat_models == ["claude-opus-5-5", "openai:gpt-5.1"]
    assert settings.retriever_top_k == [4, 6] and settings.memory_turns == [0]


def test_secret_key_is_required_outside_dev() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _settings(environment="prod")
    assert _settings(environment="prod", secret_key="x" * 40).secure_cookies
