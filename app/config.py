"""
Application configuration — configurable LLM & embedding providers.

Defines Protocol interfaces (LLMProvider, EmbeddingProvider) so all
downstream modules depend on abstractions, never on Mistral SDK directly.
Default implementation uses Mistral, swappable via .env alone.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol, runtime_checkable, Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Provider Protocols (abstract interfaces)
# ──────────────────────────────────────────────

@runtime_checkable
class LLMProvider(Protocol):
    """Abstract LLM provider — structured output via Pydantic schema."""

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], system_prompt: str = ""
    ) -> BaseModel:
        """Generate structured output bound to a Pydantic schema."""
        ...

    async def generate_text(
        self, prompt: str, system_prompt: str = "", temperature: float = 0.7
    ) -> str:
        """Generate free-form text response."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Abstract embedding provider."""

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string into a vector."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        ...


# ──────────────────────────────────────────────
# Settings (loaded from .env)
# ──────────────────────────────────────────────

class Settings(BaseSettings):
    """Central configuration for all services and database connections."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- LLM Provider ---
    LLM_PROVIDER: str = "mistral"
    LLM_MODEL: str = "mistral-small-2506"
    EMBEDDING_MODEL: str = "mistral-embed"
    EMBEDDING_DIMENSION: int = 1024

    # --- Mistral AI (default provider credentials) ---
    MISTRAL_API_KEY: str = ""

    # --- MongoDB ---
    MONGODB_URI: str
    MONGODB_DATABASE: str = "memorae_ai"

    # --- Neo4j ---
    NEO4J_URI: str
    NEO4J_USERNAME: str
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str

    # --- Qdrant ---
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # --- App Settings ---
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:3000"

    # --- Memory Tuning ---
    DEDUP_SIMILARITY_THRESHOLD: float = 0.90
    CONFIDENCE_THRESHOLD: float = 0.6
    MIN_IMPORTANCE_SCORE: int = 3

    # --- Forgetting Parameters ---
    DECAY_LAMBDA: float = 0.05
    FORGETTING_THRESHOLD: float = 0.15
    HARD_FORGET_IMPORTANCE_THRESHOLD: int = 3
    HARD_FORGET_EPISODIC_DAYS: int = 30
    HARD_FORGET_SEMANTIC_DAYS: int = 60

    # --- Retrieval ---
    RETRIEVAL_TOP_K: int = 5

    # --- Context Builder ---
    CONTEXT_TOKEN_BUDGET: int = 2000
    CONTEXT_CONVERSATION_TURNS: int = 6

    # --- Qdrant Collection Names ---
    QDRANT_EPISODIC_COLLECTION: str = "episodic_memories"
    QDRANT_SEMANTIC_COLLECTION: str = "semantic_facts"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()  # pyrefly: ignore


# ──────────────────────────────────────────────
# Default Mistral Implementations
# ──────────────────────────────────────────────

class MistralLLMProvider:
    """Default LLM provider using Mistral AI via LangChain."""

    def __init__(self, api_key: str, model: str) -> None:
        from langchain_mistralai import ChatMistralAI  # pyrefly: ignore

        self._model = model
        self._llm = ChatMistralAI(
            model=model,
            api_key=api_key,
            temperature=0.0,
            max_tokens=2500,
        )
        self._chat_llm = ChatMistralAI(
            model=model,
            api_key=api_key,
            temperature=0.7,
            max_tokens=1000,
        )

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], system_prompt: str = ""
    ) -> BaseModel:
        """Generate structured output bound to a Pydantic schema."""
        from langchain_core.messages import SystemMessage, HumanMessage  # pyrefly: ignore

        structured_llm = self._llm.with_structured_output(schema)
        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        result = await structured_llm.ainvoke(messages)
        return result  # pyrefly: ignore

    async def generate_text(
        self, prompt: str, system_prompt: str = "", temperature: float = 0.7
    ) -> str:
        """Generate free-form text response."""
        from langchain_core.messages import SystemMessage, HumanMessage  # pyrefly: ignore

        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        response = await self._chat_llm.ainvoke(messages)
        return str(response.content) if hasattr(response, "content") else str(response)


class MistralEmbeddingProvider:
    """Default embedding provider using Mistral AI via LangChain."""

    def __init__(self, api_key: str, model: str) -> None:
        from langchain_mistralai import MistralAIEmbeddings  # pyrefly: ignore

        self._embeddings = MistralAIEmbeddings(
            model=model,
            api_key=api_key,
        )

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        return await self._embeddings.aembed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        return await self._embeddings.aembed_documents(texts)


# ──────────────────────────────────────────────
# Provider Factory
# ──────────────────────────────────────────────

_llm_provider: LLMProvider | None = None
_embedding_provider: EmbeddingProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Get or create the singleton LLM provider based on .env config."""
    global _llm_provider
    if _llm_provider is None:
        settings = get_settings()
        if settings.LLM_PROVIDER.lower() == "mistral":
            _llm_provider = MistralLLMProvider(
                api_key=settings.MISTRAL_API_KEY,
                model=settings.LLM_MODEL,
            )
        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}. "
                f"Supported: 'mistral'. Add new providers in config.py."
            )
        logger.info(
            "LLM provider initialized: %s (model=%s)",
            settings.LLM_PROVIDER, settings.LLM_MODEL,
        )
    return _llm_provider


def get_embedding_provider() -> EmbeddingProvider:
    """Get or create the singleton embedding provider based on .env config."""
    global _embedding_provider
    if _embedding_provider is None:
        settings = get_settings()
        if settings.LLM_PROVIDER.lower() == "mistral":
            _embedding_provider = MistralEmbeddingProvider(
                api_key=settings.MISTRAL_API_KEY,
                model=settings.EMBEDDING_MODEL,
            )
        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER for embeddings: {settings.LLM_PROVIDER}. "
                f"Supported: 'mistral'. Add new providers in config.py."
            )
        logger.info(
            "Embedding provider initialized: %s (model=%s)",
            settings.LLM_PROVIDER, settings.EMBEDDING_MODEL,
        )
    return _embedding_provider
