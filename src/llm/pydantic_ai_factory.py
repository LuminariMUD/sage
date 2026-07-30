"""Create PydanticAI OpenAI models without mutating process environment."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


def create_openai_chat_model(
    api_key: str,
    model_name: str = "gpt-4o",
) -> OpenAIChatModel:
    """Bind a credential directly to an OpenAI provider instance."""
    if not api_key:
        raise ValueError("OpenAI API key is required")

    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(api_key=api_key),
    )
