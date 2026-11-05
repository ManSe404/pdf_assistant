"""Models behind two small interfaces; see base.py for the contract and factory.py for how
settings pick a provider.

Ported from document-buddy (common/ai, 2026-11-05) without the vision OCR part. Keep the
two copies in step when a provider changes.
"""

from pdf_assistant.ai.base import AiConfigError, AiError, ChatMessage, ChatModel, Embedder, Provider

__all__ = ["AiConfigError", "AiError", "ChatMessage", "ChatModel", "Embedder", "Provider"]
