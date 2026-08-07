"""Ollama LLM provider implementation."""

import json
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from src.llm.base import BaseLLMProvider
from src.llm.config import get_provider_settings, get_text_route
from src.llm.monitoring import monitor_performance
from src.llm.provider_config import TextModelCandidate
from src.llm.request_queue import queued_ollama_request


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, candidate: TextModelCandidate | None = None):
        """Initialize Ollama provider."""
        self.candidate = candidate or get_text_route("chat").primary
        if self.candidate.connection.provider != "ollama":
            raise ValueError("OllamaProvider requires an Ollama text candidate")
        self.base_url = self.candidate.connection.base_url
        self.timeout = aiohttp.ClientTimeout(total=self.candidate.connection.timeout_seconds)
        self.default_model = self.candidate.model

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

    def get_model_info(self) -> dict[str, Any]:
        """Get current model configuration."""
        settings = get_provider_settings()
        return {
            "provider": "ollama",
            "chat_model": settings.text_route("chat").primary.model,
            "creative_model": settings.text_route("creative").primary.model,
            "reasoning_model": settings.text_route("reasoning").primary.model,
            "embedding_model": settings.embedding_profile.model,
            "base_url": self.base_url,
            "max_context_tokens": self.candidate.context_limit,
            "candidate_fingerprint": self.candidate.fingerprint,
        }
