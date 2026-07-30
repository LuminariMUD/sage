"""OpenAI LLM provider implementation."""

from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from src.llm.base import BaseLLMProvider
from src.llm.config import get_llm_provider_config
from src.llm.monitoring import monitor_performance


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider."""

    def __init__(self):
        """Initialize OpenAI provider."""
        self.config = get_llm_provider_config()
        self.client = AsyncOpenAI(api_key=self.config["api_key"])
        self.default_model = self.config["chat_model"]

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

        return response.choices[0].message.content

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
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, text: str | list[str], **kwargs) -> list[float] | list[list[float]]:
        """Generate embeddings using OpenAI."""
        model = self.config["embedding_model"]
        is_batch = isinstance(text, list)

        input_text = text if is_batch else [text]

        response = await self.client.embeddings.create(model=model, input=input_text, **kwargs)

        if is_batch:
            return [item.embedding for item in response.data]
        else:
            return response.data[0].embedding

    def get_model_info(self) -> dict[str, Any]:
        """Get current model configuration."""
        return {
            "provider": "openai",
            "chat_model": self.config["chat_model"],
            "embedding_model": self.config["embedding_model"],
        }
