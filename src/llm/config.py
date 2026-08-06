"""Configuration management for LLM providers."""

import os
from typing import Any

# Task-specific temperature settings
TEMPERATURE_CONFIG = {
    "ollama": {
        "extraction": 0.2,  # Very deterministic
        "factual": 0.5,  # Focused
        "qa": 0.5,  # Focused for question answering
        "chat": 0.7,  # Balanced
        "reasoning": 0.5,  # Focused reasoning
        "tools": 0.5,  # Focused tool selection
        "creative": 0.85,  # Creative but coherent
        "brainstorm": 1.0,  # Diverse ideas
    },
    "openai": {
        "extraction": 0.3,
        "factual": 0.6,
        "qa": 0.6,
        "chat": 0.7,
        "reasoning": 0.6,
        "tools": 0.6,
        "creative": 0.9,
        "brainstorm": 1.1,
    },
}


# Optimal batch sizes based on benchmarking
OPTIMAL_BATCH_SIZES = {
    "embeddings": {
        "ollama": 32,  # Sweet spot for nomic-embed-text
        "openai": 100,  # OpenAI handles larger batches
    },
    "extraction": {
        "ollama": 1,  # Process episodes sequentially
        "openai": 5,  # Can batch more
    },
}


def get_llm_provider_config() -> dict[str, Any]:
    """
    Get LLM provider configuration from environment variables.

    Returns:
        Configuration dictionary
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "ollama":
        return {
            "provider": "ollama",
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            "chat_model": os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b"),
            "creative_model": os.getenv("OLLAMA_CREATIVE_MODEL", "qwen2.5:7b"),
            "reasoning_model": os.getenv("OLLAMA_REASONING_MODEL", "qwen2.5:3b"),
            # Agents that bind tools need a tool-calling model. Pure reasoning models
            # (e.g. deepseek-r1) emit chain-of-thought that Ollama's grammar-constrained
            # tool parser rejects outright, so they cannot be used here.
            "tools_model": os.getenv(
                "OLLAMA_TOOLS_MODEL", os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
            ),
            "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            "temperature": float(os.getenv("OLLAMA_CHAT_TEMPERATURE", "0.7")),
            "max_context_tokens": int(os.getenv("OLLAMA_MAX_CONTEXT_TOKENS", "12288")),
            "timeout": int(os.getenv("OLLAMA_REQUEST_TIMEOUT", "120")),
        }
    elif provider == "openai":
        return {
            "provider": "openai",
            "api_key": os.getenv("OPENAI_API_KEY"),
            "chat_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            "temperature": 0.7,
            "max_tokens": None,
        }
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def get_embedding_config() -> dict[str, Any]:
    """
    Get embedding model configuration.

    Returns:
        Configuration dictionary
    """
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"

    if use_local:
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        if provider == "ollama":
            return {
                "provider": "ollama",
                "model": os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
                "batch_size": int(os.getenv("OLLAMA_EMBEDDING_BATCH_SIZE", "32")),
                "dimension": 768,  # nomic-embed-text dimension
            }
        else:
            return {
                "provider": "sentence-transformers",
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "dimension": 384,
            }
    else:
        return {
            "provider": "openai",
            "model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            "api_key": os.getenv("OPENAI_API_KEY"),
            "dimension": 1536,
        }


def get_model_for_task(task: str) -> str:
    """
    Get the appropriate model for a specific task.

    Args:
        task: Task type (chat, creative, reasoning, tools, embedding)

    Returns:
        Model name for the task
    """
    config = get_llm_provider_config()
    provider = config["provider"]

    if provider == "ollama":
        task_models = {
            "chat": config["chat_model"],
            "creative": config["creative_model"],
            "reasoning": config["reasoning_model"],
            "tools": config["tools_model"],
            "embedding": config["embedding_model"],
        }
        return task_models.get(task, config["chat_model"])
    else:
        # OpenAI uses same model for most tasks
        return config["chat_model"]


def get_temperature_for_task(task: str) -> float:
    """
    Get optimal temperature for task and model.

    Args:
        task: Task type (extraction, factual, qa, chat, reasoning, creative, brainstorm)

    Returns:
        Optimal temperature value for the task
    """
    config = get_llm_provider_config()
    provider = config["provider"]

    temps = TEMPERATURE_CONFIG.get(provider, TEMPERATURE_CONFIG["ollama"])
    return temps.get(task, 0.7)
