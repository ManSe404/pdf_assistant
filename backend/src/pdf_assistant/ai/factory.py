"""Build the chat models and the embedder from settings.

A missing key or an impossible combination (Claude for embeddings) fails here, at
start-up, with the name of the variable to set.
"""

from dataclasses import dataclass

import anthropic
import openai
from pydantic import SecretStr

from pdf_assistant.ai.base import AiConfigError, ChatModel, Embedder, Provider
from pdf_assistant.ai.claude_models import FALLBACK_MODELS, ClaudeChat
from pdf_assistant.ai.openai_models import OpenAIChat, OpenAIEmbedder
from pdf_assistant.settings import Settings

_CLAUDE = (Provider.ANTHROPIC, Provider.ANTHROPIC_FOUNDRY)
_PROVIDERS = {p.value: p for p in Provider}


@dataclass(frozen=True)
class ModelRef:
    provider: Provider
    model: str

    @property
    def key(self) -> str:
        """Stable name stored with each conversation: ``provider:model``."""
        return f"{self.provider}:{self.model}"


def parse_model_ref(entry: str, default: Provider) -> ModelRef:
    """``claude-opus-5-5`` or ``openai:gpt-5.1``. Ollama tags have colons of their own
    (``gemma4:31b-cloud``), so only a known provider name counts as a prefix."""
    head, sep, tail = entry.partition(":")
    if sep and head in _PROVIDERS and tail:
        return ModelRef(_PROVIDERS[head], tail)
    return ModelRef(default, entry)


def chat_model_refs(settings: Settings) -> list[ModelRef]:
    refs = [parse_model_ref(entry, settings.chat_provider) for entry in settings.chat_models]
    keys = [r.key for r in refs]
    if len(set(keys)) != len(keys):
        raise AiConfigError(f"CHAT_MODELS lists a model twice: {', '.join(keys)}")
    return refs


def build_chat_models(settings: Settings) -> dict[str, ChatModel]:
    """Every model in CHAT_MODELS, keyed by ``ModelRef.key``; one client per provider."""
    async_openai: dict[Provider, openai.AsyncOpenAI] = {}
    async_claude: dict[Provider, anthropic.AsyncAnthropic] = {}
    models: dict[str, ChatModel] = {}
    for ref in chat_model_refs(settings):
        if ref.provider in _CLAUDE:
            if ref.provider not in async_claude:
                async_claude[ref.provider] = _anthropic_client(ref.provider, settings)
            models[ref.key] = ClaudeChat(
                async_claude[ref.provider],
                model=ref.model,
                effort=settings.claude_effort,
                fallbacks=ref.provider is Provider.ANTHROPIC and ref.model in FALLBACK_MODELS,
            )
        else:
            if ref.provider not in async_openai:
                async_openai[ref.provider] = _openai_client(ref.provider, settings, async_client=True)  # type: ignore[assignment]
            models[ref.key] = OpenAIChat(async_openai[ref.provider], model=ref.model)
    return models


def build_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider
    if provider in _CLAUDE:
        raise AiConfigError("Claude has no embeddings API: set EMBEDDING_PROVIDER to openai, azure-openai or ollama")
    return OpenAIEmbedder(
        _openai_client(provider, settings, async_client=False),  # type: ignore[arg-type]
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        document_prefix=settings.embed_document_prefix,
        query_prefix=settings.embed_query_prefix,
    )


def _require(value: str | SecretStr | None, variable: str, provider: Provider) -> str:
    secret = value.get_secret_value() if isinstance(value, SecretStr) else value
    if not secret:
        raise AiConfigError(f"{variable} must be set to use the '{provider}' provider")
    return secret


def azure_v1_url(endpoint: str) -> str:
    """Accept the resource URL or the full v1 URL; return the v1 base URL."""
    base = endpoint.rstrip("/")
    if not base.endswith("/openai/v1"):
        base += "/openai/v1"
    return base + "/"


def _openai_client(provider: Provider, settings: Settings, *, async_client: bool) -> openai.OpenAI | openai.AsyncOpenAI:
    if provider is Provider.OPENAI:
        api_key = _require(settings.openai_api_key, "OPENAI_API_KEY", provider)
        base_url = settings.openai_base_url
    elif provider is Provider.AZURE_OPENAI:
        api_key = _require(settings.azure_openai_api_key, "AZURE_OPENAI_API_KEY", provider)
        base_url = azure_v1_url(_require(settings.azure_openai_endpoint, "AZURE_OPENAI_ENDPOINT", provider))
    elif provider is Provider.OLLAMA:
        api_key = "ollama"  # Ollama ignores the key, the SDK requires one
        base_url = settings.ollama_url.rstrip("/") + "/v1"
    else:
        raise AiConfigError(f"'{provider}' is not an OpenAI-compatible provider")
    cls = openai.AsyncOpenAI if async_client else openai.OpenAI
    return cls(api_key=api_key, base_url=base_url, timeout=settings.llm_timeout_seconds)


def _anthropic_client(provider: Provider, settings: Settings) -> anthropic.AsyncAnthropic:
    timeout = settings.llm_timeout_seconds
    if provider is Provider.ANTHROPIC_FOUNDRY:
        return anthropic.AsyncAnthropicFoundry(
            resource=_require(settings.anthropic_foundry_resource, "ANTHROPIC_FOUNDRY_RESOURCE", provider),
            api_key=_require(settings.anthropic_foundry_api_key, "ANTHROPIC_FOUNDRY_API_KEY", provider),
            timeout=timeout,
        )
    return anthropic.AsyncAnthropic(
        api_key=_require(settings.anthropic_api_key, "ANTHROPIC_API_KEY", provider), timeout=timeout
    )
