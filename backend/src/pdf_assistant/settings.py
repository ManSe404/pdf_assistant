"""All configuration comes from environment variables (or ``backend/.env``).

Every default works for local development without any service running: SQLite, PDFs on
disk and an embedded Qdrant under ``data/``. Only the model keys have to be set (or switch
the providers to Ollama). Supabase (local or cloud) can hold the database and the PDFs.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from pdf_assistant.ai.base import Provider

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class PdfStorageKind(StrEnum):
    DISK = "disk"
    SUPABASE = "supabase"


class VectorStoreKind(StrEnum):
    QDRANT = "qdrant"
    PINECONE = "pinecone"


def _csv(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    environment: Environment = Environment.DEV
    # Signs the session cookie. Required outside dev.
    secret_key: SecretStr = SecretStr(DEV_SECRET)
    session_days: int = 14
    allow_signup: bool = True

    data_dir: Path = BACKEND_DIR / "data"
    database_url: str = ""  # default: SQLite in data_dir; Supabase: its Postgres URL
    max_upload_mb: int = 50

    # Uploaded PDFs: data_dir/pdfs, or a private Supabase Storage bucket.
    pdf_storage: PdfStorageKind = PdfStorageKind.DISK
    supabase_url: str | None = None  # http://127.0.0.1:54321 locally, https://<ref>.supabase.co
    supabase_secret_key: SecretStr | None = None  # sb_secret_... (or a legacy service_role key)
    supabase_bucket: str = "pdfs"
    # The built web client (served at /); missing in development, where Vite serves it.
    client_dir: Path = BACKEND_DIR.parent / "client" / "build"

    # Models. CHAT_MODELS is the list the experiment picks from; each entry is a model
    # name for CHAT_PROVIDER, or "provider:model" to mix providers.
    chat_provider: Provider = Provider.ANTHROPIC
    chat_models: Annotated[list[str], NoDecode] = ["claude-opus-5-5", "claude-sonnet-5-5"]
    claude_effort: str = "low"
    embedding_provider: Provider = Provider.OPENAI
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int | None = None
    # Some embedding models want a task prefix (nomic-embed-text: "search_document: ").
    embed_document_prefix: str = ""
    embed_query_prefix: str = ""
    llm_timeout_seconds: float = 120

    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_foundry_resource: str | None = None
    anthropic_foundry_api_key: SecretStr | None = None
    ollama_url: str = "http://127.0.0.1:11434"

    # The other two experiment components.
    retriever_top_k: Annotated[list[int], NoDecode] = [3, 5, 8]
    memory_turns: Annotated[list[int], NoDecode] = [0, 2]  # 0 = all history that fits
    experiments: bool = True  # false: every conversation uses the first of each list

    rewrite_followups: bool = True
    max_prompt_tokens: int = 24_000
    chunk_size: int = 1000
    chunk_overlap: int = 150
    embed_batch_size: int = 64
    index_workers: int = 1

    vector_store: VectorStoreKind = VectorStoreKind.QDRANT
    qdrant_url: str | None = None  # default: embedded Qdrant in data_dir
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "pdf_chunks"
    pinecone_api_key: SecretStr | None = None
    pinecone_index: str = "pdf-assistant"
    pinecone_host: str | None = None  # an index host, e.g. Pinecone Local
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # Tracing is on when both keys are set.
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str | None = None  # default: Langfuse Cloud (EU)

    @field_validator("chat_models", "retriever_top_k", "memory_turns", mode="before")
    @classmethod
    def _split(cls, value: object) -> object:
        return _csv(value)

    @field_validator("chat_models", "retriever_top_k", "memory_turns")
    @classmethod
    def _not_empty(cls, value: list[object]) -> list[object]:
        if not value:
            raise ValueError("needs at least one value")
        return value

    @field_validator("retriever_top_k")
    @classmethod
    def _positive(cls, value: list[int]) -> list[int]:
        if any(k < 1 for k in value):
            raise ValueError("every top_k must be at least 1")
        return value

    @model_validator(mode="after")
    def _secret_outside_dev(self) -> Settings:
        if self.environment is not Environment.DEV and self.secret_key.get_secret_value() == DEV_SECRET:
            raise ValueError("SECRET_KEY must be set outside the dev environment")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url or f"sqlite:///{self.data_dir / 'pdf_assistant.db'}"
        # The URL Supabase and most hosts hand out names no driver; psycopg 3 is the one
        # installed.
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdfs"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def secure_cookies(self) -> bool:
        return self.environment is not Environment.DEV

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
