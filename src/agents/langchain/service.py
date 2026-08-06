"""Backward-compatible import for the legacy routed chat service.

New runtime code chooses a service through :mod:`service_selector`, but older
integrations and the repository's legacy workflow tests still import
``src.agents.langchain.service`` directly.
"""

from .legacy_service import LangChainChatService

__all__ = ["LangChainChatService"]
