"""Models that speak the OpenAI API: OpenAI itself, Azure OpenAI / Microsoft Foundry
(the ``/openai/v1`` endpoint, where ``model`` is the deployment name) and Ollama's
``/v1``. One implementation covers all three; only the client's base URL and key differ.

Chat Completions is used rather than the Responses API because every one of these
servers implements it, including Foundry's non-OpenAI models.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Any

import openai

from pdf_assistant.ai.base import AiError, ChatMessage, redact


def _describe(exc: openai.OpenAIError) -> str:
    status = getattr(exc, "status_code", None)
    detail = redact(str(exc))
    return f"model request failed ({status}): {detail}" if status else f"model request failed: {detail}"


def _with_system(system: str, messages: Sequence[ChatMessage]) -> list[Any]:
    # Any: the SDK's message param is a union of TypedDicts that plain dicts don't satisfy.
    return [{"role": "system", "content": system}, *messages]


class OpenAIChat:
    def __init__(self, client: openai.AsyncOpenAI, *, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return self._model

    async def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=self._model, messages=_with_system(system, messages), stream=True
            )
        except openai.OpenAIError as exc:
            raise AiError(_describe(exc)) from exc
        try:
            async for chunk in stream:
                if chunk.choices and (piece := chunk.choices[0].delta.content):
                    yield piece
        except openai.OpenAIError as exc:
            raise AiError(_describe(exc)) from exc
        finally:
            # Also runs when the caller stops early (the browser went away): the HTTP
            # response is closed and the server stops generating.
            await stream.close()

    async def complete(self, *, system: str, messages: Sequence[ChatMessage]) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model, messages=_with_system(system, messages)
            )
        except openai.OpenAIError as exc:
            raise AiError(_describe(exc)) from exc
        if not response.choices:
            raise AiError("the model returned no answer")
        return (response.choices[0].message.content or "").strip()


class OpenAIEmbedder:
    def __init__(
        self,
        client: openai.OpenAI,
        *,
        model: str,
        dimensions: int | None = None,
        document_prefix: str = "",
        query_prefix: str = "",
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._document_prefix = document_prefix
        self._query_prefix = query_prefix

    @property
    def name(self) -> str:
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed([self._document_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query_prefix + text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        extra: dict[str, Any] = {"dimensions": self._dimensions} if self._dimensions else {}
        try:
            response = self._client.embeddings.create(
                model=self._model,
                # Empty strings are rejected by some servers; a space embeds as "nothing".
                input=[t if t.strip() else " " for t in texts],
                # Every OpenAI-compatible server supports floats; base64 is not universal.
                encoding_format="float",
                **extra,
            )
        except openai.OpenAIError as exc:
            raise AiError(_describe(exc)) from exc
        data = sorted(response.data, key=lambda item: item.index)
        if len(data) != len(texts):
            raise AiError(f"expected {len(texts)} embeddings, got {len(data)}")
        return [list(item.embedding) for item in data]
