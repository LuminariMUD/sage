"""LLM provider abstraction layer."""

from src.llm.base import BaseEmbedder, BaseLLMProvider
from src.llm.config import (
    get_embedding_config,
    get_embedding_profile,
    get_graphiti_embedding_profile,
    get_graphiti_text_route,
    get_llm_provider_config,
    get_model_for_task,
    get_provider_settings,
    get_text_route,
)
from src.llm.provider_config import (
    EmbeddingProfile,
    ProviderConnection,
    ProviderSettings,
    TextModelCandidate,
    TextRouteProfile,
)
from src.llm.providers import (
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    get_llm_provider,
    get_text_provider,
    reset_provider_cache,
)
from src.llm.routes import (
    TextRouteAttempt,
    TextRouteExecutionError,
    TextRouteExecutor,
    TextRouteResult,
    get_text_route_executor,
)

__all__ = [
    "BaseEmbedder",
    "BaseLLMProvider",
    "EmbeddingProfile",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "ProviderConnection",
    "ProviderSettings",
    "TextModelCandidate",
    "TextRouteAttempt",
    "TextRouteExecutionError",
    "TextRouteExecutor",
    "TextRouteProfile",
    "TextRouteResult",
    "get_embedding_config",
    "get_embedding_profile",
    "get_graphiti_embedding_profile",
    "get_graphiti_text_route",
    "get_llm_provider",
    "get_llm_provider_config",
    "get_model_for_task",
    "get_provider_settings",
    "get_text_provider",
    "get_text_route",
    "get_text_route_executor",
    "reset_provider_cache",
]
