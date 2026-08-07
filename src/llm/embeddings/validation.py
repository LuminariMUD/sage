"""Shared fail-closed validation for every embedding transport."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


class EmbeddingValidationError(ValueError):
    """Raised when a provider response cannot belong to the active profile."""


def validate_embedding_batch(
    vectors: Iterable[Sequence[float]],
    *,
    expected_count: int,
    dimensions: int,
) -> list[list[float]]:
    """Validate cardinality, type, finiteness, dimensions, and non-zero norm."""
    materialized = list(vectors)
    if len(materialized) != expected_count:
        raise EmbeddingValidationError("Embedding response count does not match request count")
    validated: list[list[float]] = []
    for vector in materialized:
        if isinstance(vector, (str, bytes)) or not isinstance(vector, Sequence):
            raise EmbeddingValidationError("Embedding response contains a non-vector value")
        if len(vector) != dimensions:
            raise EmbeddingValidationError("Embedding response dimension does not match profile")
        converted: list[float] = []
        squared_norm = 0.0
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingValidationError("Embedding vector contains a non-numeric value")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise EmbeddingValidationError("Embedding vector contains a non-finite value")
            converted.append(numeric)
            squared_norm += numeric * numeric
        if squared_norm == 0:
            raise EmbeddingValidationError("Embedding vector has zero norm")
        validated.append(converted)
    return validated
