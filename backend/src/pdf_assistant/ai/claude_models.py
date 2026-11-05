"""Claude through the Anthropic SDK: the Claude API (``anthropic``) or Claude deployed in
Microsoft Foundry (``anthropic-foundry``, the SDK's ``AnthropicFoundry`` client). Claude has
no embeddings endpoint, so it is only a chat model here.

- Thinking is left to the model (adaptive on current models); ``effort`` controls depth
  and cost. ``low`` suits grounded chat.
- Safety classifiers can decline a request with ``stop_reason == "refusal"``. On the Claude
  API, models that support it get the server-side fallback (``fallbacks="default"``): the
  same request continues on another model inside the same call. Foundry has no
  server-side fallback, so a refusal there surfaces as ``AiError``.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Any

import anthropic
import httpx2

from pdf_assistant.ai.base import AiError, ChatMessage, redact

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept ``fallbacks: "default"`` on the Claude API.
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})

# Streaming has no HTTP timeout risk, so the answer cap is generous. One-shot calls
# (the follow-up rewrite) are not streamed, so the whole generation must fit in the
# client's read timeout.
STREAM_MAX_TOKENS = 64_000
SHORT_MAX_TOKENS = 4_096

# anthropic 2.x wraps errors raised while a request is made, but not those raised while
# a stream is being read (a timeout or dropped connection after the first token).
_ERRORS = (anthropic.AnthropicError, httpx2.HTTPError)


def _describe(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    detail = redact(str(exc))
    return f"Claude request failed ({status}): {detail}" if status else f"Claude request failed: {detail}"


def claude_messages(messages: Sequence[ChatMessage]) -> list[Any]:
    """Claude wants a user turn first and no empty turns."""
    turns = [{"role": m["role"], "content": m["content"]} for m in messages if m["content"].strip()]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


class _ClaudeRequests:
    def __init__(self, *, model: str, effort: str | None, fallbacks: bool) -> None:
        self.model = model
        # "" or "default": send no effort and let the model use its own default.
        self.effort = effort if effort and effort != "default" else None
        self.fallbacks = fallbacks

    def params(self, *, max_tokens: int, messages: list[Any], system: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            params["system"] = system
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        if self.fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params


def _text(response: Any) -> str:
    if response.stop_reason == "refusal":
        raise AiError("Claude declined this request (stop_reason=refusal)")
    return "".join(block.text for block in response.content if block.type == "text")


class ClaudeChat:
    def __init__(
        self, client: anthropic.AsyncAnthropic, *, model: str, effort: str | None = "low", fallbacks: bool = False
    ) -> None:
        self._client = client
        self._requests = _ClaudeRequests(model=model, effort=effort, fallbacks=fallbacks)

    @property
    def name(self) -> str:
        return self._requests.model

    def _messages_api(self) -> Any:
        # Any: the beta and the stable namespaces have different static types.
        return self._client.beta.messages if self._requests.fallbacks else self._client.messages

    async def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        params = self._requests.params(max_tokens=STREAM_MAX_TOKENS, messages=claude_messages(messages), system=system)
        try:
            async with self._messages_api().stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
        except _ERRORS as exc:
            raise AiError(_describe(exc)) from exc
        if final.stop_reason == "refusal":
            # Everything that could rescue the request already ran; the partial answer
            # the user saw is not trustworthy.
            raise AiError("Claude declined to finish this answer (stop_reason=refusal)")

    async def complete(self, *, system: str, messages: Sequence[ChatMessage]) -> str:
        params = self._requests.params(max_tokens=SHORT_MAX_TOKENS, messages=claude_messages(messages), system=system)
        try:
            response = await self._messages_api().create(**params)
        except _ERRORS as exc:
            raise AiError(_describe(exc)) from exc
        return _text(response).strip()
