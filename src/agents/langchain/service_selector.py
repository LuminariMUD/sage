"""Service selector for choosing the appropriate LangChain chat service.

Supports ReAct-enabled, unified, and legacy services based on configuration.
"""

import logging
import os
from typing import Any

from src.llm.config import text_profile_is_ready

logger = logging.getLogger(__name__)


def get_chat_service(force_legacy: bool = False, enable_react: bool | None = None) -> Any:
    """Get the appropriate chat service.

    Args:
        force_legacy: Force use of legacy service
        enable_react: Enable ReAct mode (None = check env var)

    Returns:
        ReActChatService, LangChainChatService, or LegacyLangChainService
    """
    # Check if we should use legacy
    use_legacy = os.getenv("USE_LEGACY_LANGCHAIN", "false").lower() == "true"

    if force_legacy or use_legacy:
        from .legacy_service import LangChainChatService as LegacyLangChainService

        logger.info("Using legacy keyword-based service")
        return LegacyLangChainService()

    # Check for ReAct mode
    if enable_react is None:
        enable_react = os.getenv("ENABLE_REACT", "true").lower() == "true"

    # Get model configuration
    model = os.getenv("LANGCHAIN_MODEL", "gpt-4o-mini")

    if not text_profile_is_ready("tools"):
        from .legacy_service import LangChainChatService as LegacyLangChainService

        logger.warning("Text tool profile is not ready; falling back to legacy service")
        return LegacyLangChainService()

    try:
        if enable_react:
            # Use THE ONE ReAct service with scratchpad and focused tools
            try:
                from .react_service import ReactService

                logger.info("Initializing ReAct service with scratchpad and focused tools")
                return ReactService(model_name=model, temperature=0.7, max_iterations=20)
            except ImportError as e:
                logger.warning("ReAct service not available (%s)", type(e).__name__)
                logger.info("Falling back to unified service")

        # Fall back to unified service
        from .chat_service import LangChainChatService

        logger.info("Initializing modern unified LangChain service")
        return LangChainChatService(model_name=model)

    except Exception as e:
        from .legacy_service import LangChainChatService as LegacyLangChainService

        logger.error("Failed to initialize service (%s)", type(e).__name__)
        logger.info("Falling back to legacy service")
        return LegacyLangChainService()


async def compare_services(message: str, conversation_history: list[dict[str, str]] | None = None):
    """Compare outputs from modern and legacy services for testing.

    Args:
        message: User message to process
        conversation_history: Optional conversation context

    Returns:
        Dict comparing both service outputs
    """
    # Initialize both services (imported here, as elsewhere in this module, to avoid
    # importing optional service backends at module load time)
    from .chat_service import LangChainChatService
    from .legacy_service import LangChainChatService as LegacyLangChainService

    modern = LangChainChatService()
    legacy = LegacyLangChainService()

    # Get responses from both
    modern_response = await modern.chat(message, conversation_history)
    legacy_response = await legacy.chat(message, conversation_history)

    return {
        "query": message,
        "modern": {
            "tool_calls": [t.get("tool", "unknown") for t in modern_response.get("tool_calls", [])],
            "answer_preview": modern_response.get("answer", "")[:200],
        },
        "legacy": {
            "route": legacy_response.get("route"),
            "answer_preview": legacy_response.get("answer", "")[:200],
            "confidence": legacy_response.get("confidence"),
        },
    }
