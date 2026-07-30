"""Context window management utilities."""

import tiktoken


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Count tokens in text (approximate for Ollama models).

    Args:
        text: Input text
        model: Model name (uses cl100k_base encoding as approximation)

    Returns:
        Token count
    """
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base for unknown models
        enc = tiktoken.get_encoding("cl100k_base")

    return len(enc.encode(text))


def truncate_text(text: str, max_tokens: int, model: str = "gpt-4") -> str:
    """
    Truncate text to fit within token limit.

    Args:
        text: Input text
        max_tokens: Maximum tokens allowed
        model: Model name

    Returns:
        Truncated text
    """
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    tokens = enc.encode(text)

    if len(tokens) <= max_tokens:
        return text

    # Truncate and decode
    truncated_tokens = tokens[:max_tokens]
    return enc.decode(truncated_tokens)


def select_texts_within_budget(
    scored_texts: list[tuple[str, float]], max_tokens: int, model: str = "gpt-4"
) -> list[int]:
    """
    Choose the highest-scoring texts that fit within a token budget.

    Returns indices into ``scored_texts``, in their original order, so callers can filter
    a parallel list of richer objects (e.g. chunk models) without having to match on text.
    Matching on text is unsafe: joining chunks with a separator and splitting the result
    back apart cannot recover the originals when the chunks themselves contain it.

    Always returns at least one index for a non-empty input, so a single oversized text
    degrades to one (caller-truncated) entry rather than an empty result.

    Args:
        scored_texts: List of (text, relevance_score) tuples
        max_tokens: Maximum tokens for the combined context
        model: Model name used for token counting

    Returns:
        Sorted list of indices to keep
    """
    by_score = sorted(range(len(scored_texts)), key=lambda i: scored_texts[i][1], reverse=True)

    keep: list[int] = []
    total = 0
    for i in by_score:
        tokens = count_tokens(scored_texts[i][0], model)
        if total + tokens <= max_tokens:
            keep.append(i)
            total += tokens

    if not keep and scored_texts:
        keep = [by_score[0]]

    return sorted(keep)


def truncate_context_with_priority(
    context_chunks: list[tuple[str, float]], max_tokens: int, model: str = "gpt-4"
) -> str:
    """
    Truncate context chunks prioritizing by relevance score.

    Args:
        context_chunks: List of (text, relevance_score) tuples
        max_tokens: Maximum tokens for context
        model: Model name

    Returns:
        Truncated context string
    """
    # Sort by relevance (highest first)
    sorted_chunks = sorted(context_chunks, key=lambda x: x[1], reverse=True)

    selected_chunks = []
    total_tokens = 0

    for text, score in sorted_chunks:
        chunk_tokens = count_tokens(text, model)

        if total_tokens + chunk_tokens <= max_tokens:
            selected_chunks.append((text, score))
            total_tokens += chunk_tokens
        else:
            # Try to fit partial chunk
            remaining_tokens = max_tokens - total_tokens
            if remaining_tokens > 100:  # Only add if meaningful
                partial_text = truncate_text(text, remaining_tokens, model)
                selected_chunks.append((partial_text, score))
            break

    # Reorder by original score for coherence
    return "\n\n".join([text for text, _ in selected_chunks])
