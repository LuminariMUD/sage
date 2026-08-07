"""Helper functions for LangChain integration with provider abstraction.

This module provides factory functions to create LangChain chat models that
automatically use the configured LLM provider (OpenAI, Ollama, etc.) instead
of hardcoding specific providers.
"""

from typing import Any

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.llm.config import get_text_route


def get_chat_model(
    task: str = "chat",
    temperature: float | None = None,
    streaming: bool = True,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
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
        reasoning_effort: Optional OpenRouter reasoning level, including ``none``
            for concise calls that must reserve the output budget for final content.
        **kwargs: Additional arguments passed to the model constructor

    Returns:
        LangChain chat model instance (ChatOllama or ChatOpenAI)

    Raises:
        ValueError: If the configured provider is unknown

    Example:
        >>> llm = get_chat_model(task="creative", temperature=0.9)
        >>> response = llm.invoke("Tell me a story about crystal dwarves")
    """
    route = get_text_route(task)
    candidate = route.primary
    provider = candidate.connection.provider

    # Use optimal temperature for task if not specified
    if temperature is None:
        temperature = candidate.temperature
    if reasoning_effort not in {
        None,
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }:
        raise ValueError("Reasoning effort is invalid")

    if provider == "ollama":
        # langchain-ollama's ChatOllama has no `streaming` field (it would be silently
        # dropped); streaming is expressed via `disable_streaming` on BaseChatModel.
        return ChatOllama(
            model=candidate.model,
            base_url=candidate.connection.base_url,
            temperature=temperature,
            num_ctx=candidate.context_limit,
            disable_streaming=not streaming,
            **kwargs,
        )
    elif provider in {"openrouter", "openai"}:
        secret = candidate.connection.api_key
        if secret is None:  # Protected by ProviderConnection validation.
            raise ValueError(f"{provider.title()} API credentials are required")
        model_kwargs: dict[str, Any] = {
            "model": candidate.model,
            "temperature": temperature,
            "streaming": streaming,
            "api_key": secret,
            "base_url": candidate.connection.base_url,
            "default_headers": candidate.connection.default_headers,
            "timeout": candidate.connection.timeout_seconds,
            # Keep SDK calls observable. Bounded retries belong to the explicit
            # provider adapter/route executor, not a framework-internal loop.
            "max_retries": 0,
            "use_responses_api": False,
        }
        if provider == "openrouter":
            configured_body = candidate.provider_request_body()
            supplied_body = kwargs.pop("extra_body", None)
            if supplied_body is not None and supplied_body != configured_body:
                raise ValueError("OpenRouter routing cannot override the configured policy")
            # Current ChatOpenAI serializes its ``max_tokens`` constructor field as
            # ``max_completion_tokens``.  OpenRouter's strict Qwen route advertises
            # and accepts ``max_tokens`` instead, so preserve the public helper's
            # limit through the SDK's root-level extra-body merge.
            if max_tokens is not None:
                configured_body = dict(configured_body)
                configured_body["max_tokens"] = max_tokens
            if reasoning_effort is not None:
                configured_body = dict(configured_body)
                configured_body["reasoning"] = {"effort": reasoning_effort}
            model_kwargs["extra_body"] = configured_body
        elif max_tokens is not None:
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
