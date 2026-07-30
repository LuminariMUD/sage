"""Helper functions for LangChain integration with provider abstraction.

This module provides factory functions to create LangChain chat models that
automatically use the configured LLM provider (OpenAI, Ollama, etc.) instead
of hardcoding specific providers.
"""

from typing import Any

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.llm.config import get_llm_provider_config, get_model_for_task, get_temperature_for_task


def get_chat_model(
    task: str = "chat",
    temperature: float | None = None,
    streaming: bool = True,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> Any:
    """
    Get configured LangChain chat model based on provider and task.

    This function automatically selects the appropriate LangChain model class
    based on the LLM_PROVIDER environment variable and returns a configured
    instance for the specified task.

    Args:
        task: Task type (chat, creative, reasoning, extraction)
        temperature: Sampling temperature (0.0-2.0, lower = more deterministic).
                    If None, uses optimal temperature for the task.
        streaming: Enable streaming responses
        max_tokens: Maximum tokens to generate (None = no limit)
        **kwargs: Additional arguments passed to the model constructor

    Returns:
        LangChain chat model instance (ChatOllama or ChatOpenAI)

    Raises:
        ValueError: If the configured provider is unknown

    Example:
        >>> llm = get_chat_model(task="creative", temperature=0.9)
        >>> response = llm.invoke("Tell me a story about crystal dwarves")
    """
    config = get_llm_provider_config()
    provider = config["provider"]

    # Use optimal temperature for task if not specified
    if temperature is None:
        temperature = get_temperature_for_task(task)

    if provider == "ollama":
        model = get_model_for_task(task)
        # langchain-ollama's ChatOllama has no `streaming` field (it would be silently
        # dropped); streaming is expressed via `disable_streaming` on BaseChatModel.
        return ChatOllama(
            model=model,
            base_url=config["base_url"],
            temperature=temperature,
            num_ctx=config.get("max_context_tokens", 4096),
            disable_streaming=not streaming,
            **kwargs,
        )
    elif provider == "openai":
        # For OpenAI, use the configured chat model
        # OpenAI typically uses the same model for different tasks
        model = config["chat_model"]
        model_kwargs = {
            "model": model,
            "temperature": temperature,
            "streaming": streaming,
        }
        if max_tokens is not None:
            model_kwargs["max_tokens"] = max_tokens
        model_kwargs.update(kwargs)
        return ChatOpenAI(**model_kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_chat_model_for_task(task: str, **kwargs: Any) -> Any:
    """
    Convenience wrapper for get_chat_model with task-specific defaults.

    This function provides sensible default temperatures for common tasks:
    - chat: 0.7 (balanced)
    - creative: 0.9 (high creativity)
    - reasoning: 0.5 (more focused)
    - extraction: 0.3 (deterministic)

    Args:
        task: Task type
        **kwargs: Override default parameters (e.g., temperature, streaming)

    Returns:
        Configured chat model

    Example:
        >>> # Gets a creative model with temperature=0.9
        >>> creative_llm = get_chat_model_for_task("creative")
        >>>
        >>> # Override the default temperature
        >>> focused_creative = get_chat_model_for_task("creative", temperature=0.7)
    """
    # Task-specific temperature defaults
    temp_defaults = {
        "chat": 0.7,
        "creative": 0.9,
        "reasoning": 0.5,
        "extraction": 0.3,
    }

    temperature = kwargs.pop("temperature", temp_defaults.get(task, 0.7))
    return get_chat_model(task=task, temperature=temperature, **kwargs)
