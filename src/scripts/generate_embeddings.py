#!/usr/bin/env python3
"""Generate embeddings using configured provider.

This script generates vector embeddings for episodes that don't have them yet,
using the configured embedding provider (Ollama, OpenAI, or sentence-transformers).
"""

import asyncio
import sys

from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, "/app")

from src.db import get_postgres_db
from src.db.embedding_profiles import (
    EPISODE_EMBEDDING_SPACE,
    EmbeddingSpaceError,
    preflight_embedding_space,
    require_embedding_space,
)
from src.llm.config import get_embedding_profile
from src.llm.embeddings.factory import get_embedder

load_dotenv()


async def generate_embeddings(
    *,
    database_getter=get_postgres_db,
    profile_resolver=get_embedding_profile,
    embedder_factory=get_embedder,
):
    """Generate embeddings for all episodes without embeddings."""
    print("🔢 Starting embedding generation...")

    # Prove the configured profile matches the active physical vector space before
    # constructing an adapter or sending source text to any provider.
    profile = profile_resolver()
    db = await database_getter()
    preflight = await preflight_embedding_space(
        db,
        EPISODE_EMBEDDING_SPACE,
        configured_profile=profile,
        require_active=True,
    )
    require_embedding_space(preflight)

    embedder = embedder_factory(profile=profile)
    print(f"Using embedder: {embedder.__class__.__name__}")
    print(f"Embedding dimension: {embedder.get_dimension()}")

    # Fetch episodes without embeddings
    episodes = await db.fetch("""
        SELECT id, text
        FROM episodes
        WHERE embedding IS NULL
        ORDER BY id
    """)

    if not episodes:
        print("✅ All episodes already have embeddings!")
        return

    print(f"📝 Found {len(episodes)} episodes to process")

    # Process in batches
    batch_size = 32
    total_processed = 0

    for i in range(0, len(episodes), batch_size):
        batch = episodes[i : i + batch_size]
        texts = [ep["text"] for ep in batch]

        print(f"Processing batch {i // batch_size + 1}/{(len(episodes) - 1) // batch_size + 1}...")

        # Generate embeddings
        try:
            embeddings = await embedder.embed_batch(texts)
        except Exception as e:
            print(f"❌ Error generating embeddings ({type(e).__name__})")
            continue

        # Update database
        for episode, embedding in zip(batch, embeddings):
            # Convert embedding to string format for pgvector
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            await db.execute(
                "UPDATE episodes SET embedding = $1::vector WHERE id = $2",
                embedding_str,
                episode["id"],
            )
            total_processed += 1

        print(f"✅ Processed {total_processed}/{len(episodes)} episodes")

    print(f"\n🎉 Embedding generation complete! Processed {total_processed} episodes")


def main() -> int:
    try:
        asyncio.run(generate_embeddings())
    except EmbeddingSpaceError as error:
        print(f"❌ {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"❌ Embedding generation failed ({type(error).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
