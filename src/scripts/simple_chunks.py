#!/usr/bin/env python3
"""Simple chunk generation without Graphiti - for when network is unreachable."""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.db import get_postgres_db


# Simple chunk generation without ML models
class SimpleChunkGenerator:
    """Generate simple text chunks without embeddings."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks_created = 0

    def create_chunks(self, text: str, doc_uuid: str) -> list[dict]:
        """Create text chunks from document."""
        chunks = []
        text = text.strip()

        if len(text) <= self.chunk_size:
            # Document is small enough to be one chunk
            chunks.append(
                {
                    "document_id": doc_uuid,
                    "text": text,
                    "chunk_index": 0,
                    "token_count": len(text.split()),
                    "metadata": {},
                }
            )
        else:
            # Split into overlapping chunks
            start = 0
            chunk_index = 0

            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunk_text = text[start:end]

                chunks.append(
                    {
                        "document_id": doc_uuid,
                        "text": chunk_text,
                        "chunk_index": chunk_index,
                        "token_count": len(chunk_text.split()),
                        "metadata": {"start": start, "end": end},
                    }
                )

                chunk_index += 1
                start += self.chunk_size - self.overlap

                if end >= len(text):
                    break

        return chunks


async def main():
    """Generate simple chunks for canon documents."""
    print("Simple Chunk Generator (No ML Models)")
    print("=" * 50)

    # Connect to database
    db = await get_postgres_db()

    # This legacy utility shares the same hard corpus boundary as production.
    documents = await db.fetch("""
        SELECT id, stable_id, title, body_md, source_file
        FROM lore_documents
        WHERE canonical IS TRUE
          AND source_file LIKE 'canon/%'
        ORDER BY title
    """)

    print(f"Found {len(documents)} documents to process")

    generator = SimpleChunkGenerator()

    # Clear existing chunks
    await db.execute("DELETE FROM chunks")
    print("Cleared existing chunks")

    total_chunks = 0

    for doc in documents:
        print(f"Processing: {doc['title']}")

        # Generate chunks (using document UUID not stable_id)
        chunks = generator.create_chunks(doc["body_md"], doc["id"])

        # Insert chunks into database
        for chunk in chunks:
            await db.execute(
                """
                INSERT INTO chunks (
                    document_id, text, chunk_index,
                    token_count, metadata
                ) VALUES ($1, $2, $3, $4, $5)
            """,
                chunk["document_id"],
                chunk["text"],
                chunk["chunk_index"],
                chunk["token_count"],
                json.dumps(chunk["metadata"]),
            )

        total_chunks += len(chunks)
        print(f"  → Created {len(chunks)} chunks")

    print(f"\n✅ Generated {total_chunks} chunks from {len(documents)} documents!")
    print("\nNote: This simple version creates text chunks without embeddings.")
    print("For full semantic search, you'll need the ML model-based pipeline.")


if __name__ == "__main__":
    asyncio.run(main())
