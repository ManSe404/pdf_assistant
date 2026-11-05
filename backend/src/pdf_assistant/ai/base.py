"""What the rest of the app needs from a model, independent of who serves it.

- ``ChatModel``: answer a conversation (streamed) and run short one-shot prompts.
- ``Embedder``: turn text into vectors.

Messages are plain ``{"role": "user" | "assistant", "content": str}`` dicts; the system
prompt travels separately because Claude takes it as its own field. Every failure a
provider raises is turned into ``AiError`` so callers handle one exception type.
"""

import re
from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Protocol

ChatMessage = dict[str, str]


class Provider(StrEnum):
    OPENAI = "openai"  # api.openai.com, or any OpenAI-compatible server via OPENAI_BASE_URL
    AZURE_OPENAI = "azure-openai"  # Azure OpenAI / Microsoft Foundry, the /openai/v1 endpoint
    ANTHROPIC = "anthropic"  # Claude API
    ANTHROPIC_FOUNDRY = "anthropic-foundry"  # Claude deployed in Microsoft Foundry
    OLLAMA = "ollama"  # Ollama's OpenAI-compatible /v1 (local or Ollama cloud models)


class AiError(Exception):
    """The model provider failed, refused, or returned something unusable."""


class AiConfigError(AiError):
    """The provider settings are incomplete or ask for something the provider cannot do."""


class ChatModel(Protocol):
    @property
    def name(self) -> str:
        """The model name as the provider knows it (a deployment name on Azure)."""
        ...

    def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield the answer piece by piece. Closing the iterator closes the connection."""
        ...

    async def complete(self, *, system: str, messages: Sequence[ChatMessage]) -> str:
        """Return the whole answer to a short prompt."""
        ...


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


# API keys (sk-..., sk-ant-..., sk-proj-...) as providers echo them, masked or not.
_KEY_LIKE = re.compile(r"\bsk-[A-Za-z0-9_*.\-]{4,}")


def redact(text: str) -> str:
    """Remove key-like strings from provider error text before it is logged or stored."""
    return _KEY_LIKE.sub("sk-***", text)
