#!/usr/bin/env python3
"""
Semantic chunking module for creating semantically coherent text chunks.

Uses sentence-transformers for semantic similarity and spaCy for sentence segmentation.
All token counting uses tiktoken for consistency with OpenAI models.
"""

import numpy as np
import spacy
import tiktoken
from sentence_transformers import SentenceTransformer


class SemanticChunker:
    """Create semantically coherent chunks with intelligent overlap."""

    def __init__(
        self,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        base_tokens: int = 400,  # increased from 200
        min_tokens: int = 200,
        max_tokens: int = 600,
        overlap_percentage: float = 0.25,  # 25% overlap
        similarity_threshold: float = 0.7,
        complexity_factor: float = 1.5,
        spacy_model: str = "en_core_web_sm",
    ):
        # Load models
        self.sentence_model = SentenceTransformer(embedding_model)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # Load spaCy for sentence segmentation
        try:
            self.nlp = spacy.load(spacy_model)
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model {spacy_model!r} is not installed; "
                "install and verify it during image/environment provisioning"
            ) from exc

        # Configuration
        self.base_tokens = base_tokens
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.overlap_percentage = overlap_percentage
        self.similarity_threshold = similarity_threshold
        self.complexity_factor = complexity_factor

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken for consistency with OpenAI models."""
        return len(self.tokenizer.encode(text))

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings."""
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def calculate_complexity_score(self, sentence: str) -> float:
        """Calculate complexity score for dynamic chunk sizing."""
        words = sentence.split()
        if not words:
            return 1.0

        # Metrics for complexity
        avg_word_length = sum(len(word) for word in words) / len(words)
        sentence_length = len(words)

        # Normalize and combine metrics
        word_complexity = min(avg_word_length / 6.0, 2.0)  # Cap at 2x
        length_complexity = min(sentence_length / 20.0, 1.5)  # Cap at 1.5x

        return (word_complexity + length_complexity) / 2

    def calculate_dynamic_max_tokens(self, sentences: list[str]) -> int:
        """Calculate dynamic max tokens based on content complexity."""
        if not sentences:
            return self.max_tokens

        # Sample a representative portion of sentences to avoid document-wide averaging
        sample_size = min(20, len(sentences))  # Use first 20 sentences as representative
        sample_sentences = sentences[:sample_size]

        # Calculate average complexity for this sample
        complexities = [self.calculate_complexity_score(sent) for sent in sample_sentences]
        avg_complexity = sum(complexities) / len(complexities)

        # Adjust target upward for complex content, but start from max_tokens as baseline
        if avg_complexity > 1.2:  # High complexity content gets larger chunks
            dynamic_max = int(self.max_tokens * 1.2)
        elif avg_complexity > 1.0:  # Medium complexity gets standard max
            dynamic_max = self.max_tokens
        else:  # Simple content can use smaller chunks but not tiny
            dynamic_max = max(int(self.max_tokens * 0.8), self.base_tokens * 2)

        # Ensure within reasonable bounds (never less than base_tokens * 1.5)
        return max(int(self.base_tokens * 1.5), min(dynamic_max, self.max_tokens * 2))

    def segment_into_sentences(self, text: str) -> list[str]:
        """Segment text into sentences using spaCy."""
        doc = self.nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        return sentences

    def get_overlap_sentences(self, sentences: list[str], target_overlap_tokens: int) -> list[str]:
        """
        Get sentences from end of list that provide target overlap tokens.
        Always returns complete sentences, even if slightly exceeding target.
        """
        if not sentences:
            return []

        overlap_sentences = []
        current_tokens = 0

        # Work backwards from end of sentences
        for sentence in reversed(sentences):
            sentence_tokens = self.count_tokens(sentence)

            # Always include at least one sentence if we haven't started
            if not overlap_sentences:
                overlap_sentences.insert(0, sentence)
                current_tokens += sentence_tokens
            else:
                # Check if adding this sentence would roughly meet our target
                if (
                    current_tokens + sentence_tokens <= target_overlap_tokens * 1.5
                ):  # Allow 50% overage
                    overlap_sentences.insert(0, sentence)
                    current_tokens += sentence_tokens
                else:
                    # Stop adding sentences - we have enough overlap
                    break

        return overlap_sentences

    def should_start_new_chunk(
        self,
        current_sentences: list[str],
        current_embeddings: list[np.ndarray],
        candidate_sentence: str,
        candidate_embedding: np.ndarray,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        """Determine if we should start a new chunk."""

        # Always start new chunk if we're at token limit
        candidate_tokens = self.count_tokens(candidate_sentence)
        if current_tokens + candidate_tokens > max_tokens:
            return True

        # If we don't have previous sentences, don't start new chunk
        if not current_sentences or not current_embeddings:
            return False

        # PRIORITY 1: Don't split until we're at least 70% of base_tokens
        target_threshold = int(self.base_tokens * 0.7)  # e.g., 140 tokens for base=200
        if current_tokens < target_threshold:
            return False

        # Calculate chunk centroid embedding (average of all sentence embeddings)
        chunk_centroid = np.mean(current_embeddings, axis=0)
        similarity = self.cosine_similarity(candidate_embedding, chunk_centroid)

        # PRIORITY 2: If we haven't reached base_tokens, only split on very low similarity
        if current_tokens < self.base_tokens:
            # Use much stricter threshold when below target size
            strict_threshold = max(0.3, self.similarity_threshold - 0.3)
            return similarity < strict_threshold

        # PRIORITY 3: Above base_tokens, use normal semantic threshold
        if similarity < self.similarity_threshold:
            return current_tokens >= self.min_tokens

        return False

    def create_semantic_chunks(self, text: str, title: str = "") -> list[dict]:
        """
        Create semantically coherent chunks with intelligent overlap.

        Returns list of chunk dictionaries with 'text', 'token_count', and 'metadata'.
        """
        if not text.strip():
            return []

        # Segment into sentences
        sentences = self.segment_into_sentences(text)

        if not sentences:
            return []

        # Handle single sentence case
        if len(sentences) == 1:
            return [
                {
                    "text": sentences[0],
                    "token_count": self.count_tokens(sentences[0]),
                    "metadata": {
                        "sentence_count": 1,
                        "has_overlap": False,
                        "complexity_score": self.calculate_complexity_score(sentences[0]),
                    },
                }
            ]

        # Generate embeddings for all sentences
        embeddings = self.sentence_model.encode(sentences)

        # Calculate dynamic max tokens based on content complexity
        dynamic_max_tokens = self.calculate_dynamic_max_tokens(sentences)
        target_overlap_tokens = int(dynamic_max_tokens * self.overlap_percentage)

        chunks = []
        current_sentences = []
        current_embeddings = []
        current_tokens = 0

        for i, (sentence, embedding) in enumerate(zip(sentences, embeddings)):
            sentence_tokens = self.count_tokens(sentence)

            # Check if we should start a new chunk
            if self.should_start_new_chunk(
                current_sentences,
                current_embeddings,
                sentence,
                embedding,
                current_tokens,
                dynamic_max_tokens,
            ):
                # Save current chunk
                if current_sentences:
                    chunk_text = " ".join(current_sentences)

                    # Add title context if this isn't the first chunk
                    if chunks and title:
                        chunk_text = f"[Continuing from {title}]\n\n{chunk_text}"

                    chunks.append(
                        {
                            "text": chunk_text,
                            "token_count": current_tokens,
                            "metadata": {
                                "sentence_count": len(current_sentences),
                                "has_overlap": len(chunks) > 0,  # Has overlap if not first chunk
                                "complexity_score": sum(
                                    self.calculate_complexity_score(s) for s in current_sentences
                                )
                                / len(current_sentences),
                                "dynamic_max_tokens": dynamic_max_tokens,
                            },
                        }
                    )

                # Start new chunk with overlap
                if chunks:  # Only add overlap if this isn't the first chunk
                    overlap_sentences = self.get_overlap_sentences(
                        current_sentences, target_overlap_tokens
                    )
                    overlap_embeddings = [
                        current_embeddings[current_sentences.index(sent)]
                        for sent in overlap_sentences
                        if sent in current_sentences
                    ]

                    current_sentences = [*overlap_sentences, sentence]
                    current_embeddings = [*overlap_embeddings, embedding]
                    current_tokens = sum(self.count_tokens(s) for s in current_sentences)
                else:
                    # First chunk - no overlap needed
                    current_sentences = [sentence]
                    current_embeddings = [embedding]
                    current_tokens = sentence_tokens
            else:
                # Continue current chunk
                current_sentences.append(sentence)
                current_embeddings.append(embedding)
                current_tokens += sentence_tokens

        # Don't forget the last chunk
        if current_sentences:
            chunk_text = " ".join(current_sentences)

            # Add title context if this isn't the first chunk
            if chunks and title:
                chunk_text = f"[Continuing from {title}]\n\n{chunk_text}"

            chunks.append(
                {
                    "text": chunk_text,
                    "token_count": current_tokens,
                    "metadata": {
                        "sentence_count": len(current_sentences),
                        "has_overlap": len(chunks) > 0,
                        "complexity_score": sum(
                            self.calculate_complexity_score(s) for s in current_sentences
                        )
                        / len(current_sentences),
                        "dynamic_max_tokens": dynamic_max_tokens,
                    },
                }
            )

        return chunks


# Convenience function for easy import
def create_semantic_chunks(
    text: str,
    title: str = "",
    base_tokens: int = 200,
    similarity_threshold: float = 0.7,
    overlap_percentage: float = 0.25,
) -> list[dict]:
    """
    Convenience function to create semantic chunks with default parameters.
    """
    chunker = SemanticChunker(
        base_tokens=base_tokens,
        similarity_threshold=similarity_threshold,
        overlap_percentage=overlap_percentage,
    )
    return chunker.create_semantic_chunks(text, title)


if __name__ == "__main__":
    # Test the semantic chunker
    test_text = """
    The Crystal Dwarves of Nagburim are an ancient and mysterious race. They dwell deep beneath the mountains in halls of living crystal. Their bodies are composed of translucent crystal that ranges from diamond-clear nobility to clouded quartz commoners.

    The Crystal Dwarves speak in Tal, a language of harmonic resonance that sounds like living music. Their society operates through a rigid caste system based on crystal purity. The nobles are nearly transparent, while lower castes bear veins of darker minerals.

    Among the lower castes arose the practice of gilding—tracing their flaws with molten gold, silver, or copper. To some, this is an act of aspiration; to others, a mask for imperfection. The gilding tradition reflects their complex relationship with perfection and societal hierarchy.
    """

    chunker = SemanticChunker(base_tokens=150)  # Smaller for testing
    chunks = chunker.create_semantic_chunks(test_text, "Crystal Dwarves")

    print(f"Created {len(chunks)} semantic chunks:")
    for i, chunk in enumerate(chunks):
        print(f"\nChunk {i + 1} ({chunk['token_count']} tokens):")
        print(f"Sentences: {chunk['metadata']['sentence_count']}")
        print(f"Has overlap: {chunk['metadata']['has_overlap']}")
        print(f"Complexity: {chunk['metadata']['complexity_score']:.2f}")
        print(f"Text preview: {chunk['text'][:100]}...")
