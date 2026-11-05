"""Langfuse tracing, off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.

Each chat turn and each PDF indexing run is one trace: a root observation with child
observations for the follow-up rewrite, the retrieval, the answer and the embedding
calls. User and conversation ids become Langfuse's user and session, so a conversation
reads as one session.

Observations are started and ended explicitly instead of through the "current
observation" context managers, because a chat turn is an async generator that yields
between steps; OpenTelemetry context set before a ``yield`` and reset after it can be
reset from another context when the client disconnects.
"""

import logging
from collections.abc import Mapping
from typing import Any, Literal, Protocol

from pdf_assistant.settings import Settings

logger = logging.getLogger(__name__)

ObservationType = Literal["span", "generation", "embedding", "retriever", "chain"]


class Observation(Protocol):
    def child(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        input: Any = None,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Observation: ...

    def end(
        self, *, output: Any = None, error: str | None = None, metadata: Mapping[str, Any] | None = None
    ) -> None: ...


class Tracer(Protocol):
    def start(
        self,
        name: str,
        *,
        user_id: str,
        session_id: str | None = None,
        input: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Observation: ...

    def shutdown(self) -> None: ...


class _NoObservation:
    def child(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        input: Any = None,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> _NoObservation:
        return self

    def end(self, *, output: Any = None, error: str | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        pass


class NoTracer:
    def start(
        self,
        name: str,
        *,
        user_id: str,
        session_id: str | None = None,
        input: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Observation:
        return _NoObservation()

    def shutdown(self) -> None:
        pass


class _LangfuseObservation:
    def __init__(self, observation: Any, attributes: Mapping[str, Any]) -> None:
        self._observation = observation  # a Langfuse span/generation wrapper
        self._attributes = attributes

    def child(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        input: Any = None,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Observation:
        try:
            from langfuse import propagate_attributes

            kwargs: dict[str, Any] = {"name": name, "as_type": as_type, "input": input, "metadata": metadata}
            if model:
                kwargs["model"] = model
            with propagate_attributes(**self._attributes):
                return _LangfuseObservation(self._observation.start_observation(**kwargs), self._attributes)
        except Exception:
            logger.warning("langfuse: could not start observation %s", name, exc_info=True)
            return _NoObservation()

    def end(self, *, output: Any = None, error: str | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        try:
            update: dict[str, Any] = {}
            if output is not None:
                update["output"] = output
            if metadata:
                update["metadata"] = dict(metadata)
            if error:
                update["level"] = "ERROR"
                update["status_message"] = error
            if update:
                self._observation.update(**update)
            self._observation.end()
        except Exception:
            logger.warning("langfuse: could not end observation", exc_info=True)


class LangfuseTracer:
    def __init__(self, client: Any) -> None:
        self._client = client  # langfuse.Langfuse

    def start(
        self,
        name: str,
        *,
        user_id: str,
        session_id: str | None = None,
        input: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Observation:
        attributes: dict[str, Any] = {"user_id": user_id, "trace_name": name}
        if session_id:
            attributes["session_id"] = session_id
        try:
            from langfuse import propagate_attributes

            with propagate_attributes(**attributes):
                root = self._client.start_observation(
                    name=name, as_type="chain", input=input, metadata=dict(metadata or {})
                )
            return _LangfuseObservation(root, attributes)
        except Exception:
            logger.warning("langfuse: could not start trace %s", name, exc_info=True)
            return _NoObservation()

    def shutdown(self) -> None:
        try:
            self._client.shutdown()
        except Exception:
            logger.warning("langfuse: shutdown failed", exc_info=True)


def build_tracer(settings: Settings) -> Tracer:
    if not settings.tracing_enabled:
        return NoTracer()
    from langfuse import Langfuse

    assert settings.langfuse_secret_key is not None  # tracing_enabled checked it
    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment=settings.environment.value,
        timeout=10,
    )
    logger.info("Langfuse tracing on (%s)", settings.langfuse_base_url or "Langfuse Cloud")
    return LangfuseTracer(client)
