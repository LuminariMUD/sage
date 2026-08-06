"""Backward-compatible name for the unified LangChain chat service."""

from .chat_service import LangChainChatService as ModernLangChainService

__all__ = ["ModernLangChainService"]
