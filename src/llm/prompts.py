"""Optimized prompts for different models."""

from src.llm.config import get_llm_provider_config


def get_optimized_prompt(task: str, context: str = "", question: str = "") -> str:
    """
    Get prompt optimized for current model and task.

    Args:
        task: Task type (qa, creative, extraction, reasoning)
        context: Context text (for RAG)
        question: User question

    Returns:
        Optimized prompt string
    """
    config = get_llm_provider_config()
    provider = config["provider"]

    if provider == "ollama":
        model = config.get("chat_model", "")

        if "qwen" in model.lower():
            return get_qwen_prompt(task, context, question)
        elif "deepseek" in model.lower():
            return get_deepseek_prompt(task, context, question)
        elif "llama" in model.lower():
            return get_llama_prompt(task, context, question)
        else:
            return get_generic_ollama_prompt(task, context, question)
    else:
        return get_openai_prompt(task, context, question)


def get_qwen_prompt(task: str, context: str, question: str) -> str:
    """Qwen-optimized prompts (prefers structured, explicit instructions)."""

    if task == "qa":
        return f"""TASK: Answer the question using the provided context.

CONTEXT:
{context}

QUESTION: {question}

INSTRUCTIONS:
- Use only information from the context
- Be concise and factual
- If unsure, say "I don't know"

ANSWER:"""

    elif task == "creative":
        return f"""TASK: Generate creative fantasy content.

CONTEXT:
{context}

REQUEST: {question}

INSTRUCTIONS:
- Create engaging, immersive narrative
- Stay consistent with provided lore
- Use vivid descriptions
- Maintain fantasy tone

OUTPUT:"""

    elif task == "extraction":
        return f"""TASK: Extract structured information.

TEXT:
{context}

INSTRUCTIONS:
- Identify entities (characters, locations, items)
- Extract relationships between entities
- Output in JSON format
- Be precise and deterministic

OUTPUT:"""

    elif task == "reasoning":
        return f"""TASK: Solve this problem step-by-step.

CONTEXT:
{context}

PROBLEM: {question}

INSTRUCTIONS:
- Break down the problem
- Apply logical reasoning
- Show your work
- Provide clear answer

SOLUTION:"""

    else:
        # Default chat format
        return f"""CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""


def get_deepseek_prompt(task: str, context: str, question: str) -> str:
    """DeepSeek-R1 optimized prompts (excels at reasoning)."""

    if task == "reasoning":
        return f"""Let's solve this step-by-step.

CONTEXT:
{context}

PROBLEM: {question}

APPROACH:
1. Analyze the given information
2. Apply logical reasoning
3. Draw conclusions
4. Provide clear answer

SOLUTION:"""

    elif task == "extraction":
        return f"""Analyze this text and extract structured data.

TEXT:
{context}

EXTRACT:
- Entities with types
- Relationships with confidence
- Attributes and properties

Use precise, deterministic extraction:"""

    elif task == "qa":
        return f"""Answer this question using the provided context.

CONTEXT:
{context}

QUESTION: {question}

Let's think through this carefully:"""

    elif task == "creative":
        return f"""Create engaging fantasy content based on this context.

CONTEXT:
{context}

REQUEST: {question}

Story:"""

    else:
        # Default
        return f"""CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""


def get_llama_prompt(task: str, context: str, question: str) -> str:
    """Llama3-optimized prompts (prefers conversational style)."""

    if task == "qa":
        return f"""<|system|>
You are a helpful assistant with expertise in fantasy lore.
<|user|>
Context:
{context}

Question: {question}
<|assistant|>
"""

    elif task == "creative":
        return f"""<|system|>
You are a creative storyteller specializing in fantasy narratives.
<|user|>
Context:
{context}

Request: {question}
<|assistant|>
"""

    elif task == "extraction":
        return f"""<|system|>
You are an expert at extracting structured information from text.
<|user|>
Extract entities and relationships from this text:

{context}
<|assistant|>
"""

    else:
        # Default chat
        return f"""<|system|>
You are a helpful assistant.
<|user|>
{context}

{question}
<|assistant|>
"""


def get_generic_ollama_prompt(task: str, context: str, question: str) -> str:
    """Generic prompt for unknown Ollama models."""
    if not context:
        return question

    return f"""Context:
{context}

Question: {question}

Answer:"""


def get_openai_prompt(task: str, context: str, question: str) -> str:
    """OpenAI-optimized prompts (works well with system messages in practice)."""
    if task == "qa":
        return f"""Use the following context to answer the question.

Context:
{context}

Question: {question}

Answer:"""

    elif task == "creative":
        return f"""Based on the following lore context, create engaging fantasy content.

Context:
{context}

Request: {question}

Response:"""

    elif task == "extraction":
        return f"""Extract structured information (entities and relationships) from the following text.

Text:
{context}

Output in JSON format:"""

    else:
        # Default
        if not context:
            return question
        return f"""Context:
{context}

Question: {question}

Answer:"""
