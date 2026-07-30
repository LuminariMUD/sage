"""Ollama LLM provider implementation."""

import json
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from src.llm.base import BaseLLMProvider
from src.llm.config import get_llm_provider_config
from src.llm.monitoring import monitor_performance
from src.llm.request_queue import queued_ollama_request


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(self):
        """Initialize Ollama provider."""
        self.config = get_llm_provider_config()
        self.base_url = self.config["base_url"]
        self.timeout = aiohttp.ClientTimeout(total=self.config["timeout"])
        self.default_model = self.config["chat_model"]

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """Generate completion using Ollama with queue management."""
        return await queued_ollama_request(
            self._generate_impl, prompt, model, temperature, max_tokens, **kwargs
        )

    @monitor_performance
    async def _generate_impl(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """Internal generation implementation."""
        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False,
            **kwargs,
        }

        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama generation request failed with status {response.status}"
                    )

                result = await response.json()
                return result["response"]

    async def stream(
        self, prompt: str, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream completion tokens using Ollama."""
        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama generation request failed with status {response.status}"
                    )

                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                yield data["response"]
                        except json.JSONDecodeError:
                            continue

    async def embed(self, text: str | list[str], **kwargs) -> list[float] | list[list[float]]:
        """Generate embeddings using Ollama."""
        model = self.config["embedding_model"]
        is_batch = isinstance(text, list)

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            if is_batch:
                # Batch processing
                embeddings = []
                for t in text:
                    async with session.post(
                        f"{self.base_url}/api/embeddings", json={"model": model, "prompt": t}
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(
                                f"Ollama embedding request failed with status {response.status}"
                            )
                        result = await response.json()
                        embeddings.append(result["embedding"])
                return embeddings
            else:
                async with session.post(
                    f"{self.base_url}/api/embeddings", json={"model": model, "prompt": text}
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(
                            f"Ollama embedding request failed with status {response.status}"
                        )
                    result = await response.json()
                    return result["embedding"]

    def get_model_info(self) -> dict[str, Any]:
        """Get current model configuration."""
        return {
            "provider": "ollama",
            "chat_model": self.config["chat_model"],
            "creative_model": self.config["creative_model"],
            "reasoning_model": self.config["reasoning_model"],
            "embedding_model": self.config["embedding_model"],
            "base_url": self.base_url,
            "max_context_tokens": self.config["max_context_tokens"],
        }
