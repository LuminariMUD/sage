"""Configuration for LangChain chat service with reflection settings."""

import os

from src.llm.config import text_profile_is_ready


def get_reflection_config() -> dict:
    """Get reflection configuration from environment variables.

    Environment variables:
    - LANGCHAIN_ENABLE_REFLECTION: Enable/disable reflection (default: true)
    - LANGCHAIN_REFLECTION_MODEL: Model to use for reflection (default: gpt-4o-mini)
    - LANGCHAIN_MAX_RETRIEVAL_ROUNDS: Max additional retrieval rounds (default: 2)
    - LANGCHAIN_CONFIDENCE_THRESHOLD: Min confidence before adding notes (default: 0.8)

    Returns:
        Dictionary with reflection configuration
    """
    return {
        "enable_reflection": os.getenv("LANGCHAIN_ENABLE_REFLECTION", "true").lower() == "true",
        "reflection_model": os.getenv("LANGCHAIN_REFLECTION_MODEL", "gpt-4o-mini"),
        "max_retrieval_rounds": int(os.getenv("LANGCHAIN_MAX_RETRIEVAL_ROUNDS", "2")),
        "confidence_threshold": float(os.getenv("LANGCHAIN_CONFIDENCE_THRESHOLD", "0.8")),
    }


def should_enable_reflection() -> bool:
    """Check if reflection should be enabled based on environment.

    Reflection requires:
    - a ready reasoning text profile
    - LANGCHAIN_ENABLE_REFLECTION not set to false

    Returns:
        True if reflection should be enabled
    """
    provider_available = text_profile_is_ready("reasoning")
    reflection_enabled = os.getenv("LANGCHAIN_ENABLE_REFLECTION", "true").lower() != "false"

    return provider_available and reflection_enabled
