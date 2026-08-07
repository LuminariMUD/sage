"""OpenAI LLM provider implementation."""

from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from src.llm.base import BaseLLMProvider
from src.llm.config import get_text_route
from src.llm.monitoring import monitor_performance
from src.llm.provider_config import TextModelCandidate


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, candidate: TextModelCandidate | None = None):
        """Initialize OpenAI provider."""
        self.candidate = candidate or get_text_route("chat").primary
        if self.candidate.connection.provider != "openai":
            raise ValueError("OpenAIProvider requires a direct OpenAI text candidate")
        secret = self.candidate.connection.api_key
        if secret is None:  # Protected by ProviderConnection validation.
            raise ValueError("OpenAI API credentials are required")
        retry_policy = self.candidate.connection.transport_retry
        self.client = AsyncOpenAI(
            api_key=secret.get_secret_value(),
            base_url=self.candidate.connection.base_url,
            timeout=self.candidate.connection.timeout_seconds,
            max_retries=retry_policy.maximum_attempts - 1,
            default_headers=self.candidate.connection.default_headers,
        )
        self.default_model = self.candidate.model

    @monitor_performance
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """Generate completion using OpenAI."""
        model = model or self.default_model

        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return response.choices[0].message.content or ""

    async def stream(
        self, prompt: str, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream completion tokens using OpenAI."""
        model = model or self.default_model

        stream = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def get_model_info(self) -> dict[str, Any]:
        """Get current model configuration."""
        return {
            "provider": "openai",
            "chat_model": self.default_model,
            "candidate_fingerprint": self.candidate.fingerprint,
        }
