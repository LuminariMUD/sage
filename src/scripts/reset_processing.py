#!/usr/bin/env python3
"""
Reset processing flags in PostgreSQL database.

This utility script allows selective resetting of various processing flags and data
in the PostgreSQL database, supporting incremental processing and pipeline recovery.

Environment variables used (from Docker container):
- POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

Available reset targets:
- sync: Reset Graphiti sync flags (allows re-sync to Neo4j)
- embeddings: Clear episode embeddings (allows re-generation)
- documents: Reset document processing status (allows re-processing)
- all: Reset everything above
"""

import argparse
import asyncio
import sys

# Add src to path for imports
sys.path.insert(0, "/app")

from src.db import get_postgres_db


async def get_processing_stats():
    """Get current processing statistics"""
    try:
        postgres = await get_postgres_db()

        # Episode statistics
        episode_stats = await postgres.fetchrow("""
            SELECT
                COUNT(*) as total_episodes,
                COUNT(*) FILTER (WHERE graphiti_synced = TRUE) as synced_episodes,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) as episodes_with_embeddings
            FROM episodes
        """)

        # Document statistics
        doc_stats = await postgres.fetchrow("""
            SELECT
                COUNT(*) as total_documents,
                COUNT(*) FILTER (WHERE processing_status = 'completed') as completed_documents,
                COUNT(*) FILTER (WHERE processing_status = 'pending') as pending_documents,
                COUNT(*) FILTER (WHERE processing_status = 'failed') as failed_documents
            FROM lore_documents
        """)

        # Chunk statistics
        chunk_stats = await postgres.fetchrow("""
            SELECT
                COUNT(*) as total_chunks,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) as chunks_with_embeddings
            FROM chunks
        """)

        await postgres.disconnect()

        return {"episodes": episode_stats, "documents": doc_stats, "chunks": chunk_stats}

    except Exception as e:
        print(f"❌ Failed to get processing statistics ({type(e).__name__})")
        return None


def format_processing_stats(stats: dict):
    """Format processing statistics for display"""
    print("📊 Current Processing Status:")

    # Episodes
    episodes = stats["episodes"]
    print("\n  Episodes:")
    print(f"    Total: {episodes['total_episodes']}")
    print(f"    Synced to Graphiti: {episodes['synced_episodes']}")
    print(f"    With embeddings: {episodes['episodes_with_embeddings']}")

    # Documents
    documents = stats["documents"]
    print("\n  Documents:")
    print(f"    Total: {documents['total_documents']}")
    print(f"    Completed: {documents['completed_documents']}")
    print(f"    Pending: {documents['pending_documents']}")
    print(f"    Failed: {documents['failed_documents']}")

    # Chunks
    chunks = stats["chunks"]
    print("\n  Chunks:")
    print(f"    Total: {chunks['total_chunks']}")
    print(f"    With embeddings: {chunks['chunks_with_embeddings']}")


async def reset_sync_flags(debug: bool = False) -> bool:
    """Reset Graphiti sync flags"""
    try:
        postgres = await get_postgres_db()

        # Count episodes that will be reset
        count_result = await postgres.fetchrow("""
            SELECT COUNT(*) as count
            FROM episodes
            WHERE graphiti_synced = TRUE
        """)

        episodes_to_reset = count_result["count"] if count_result else 0

        if episodes_to_reset == 0:
            print("  ℹ️  No synced episodes to reset")
            await postgres.disconnect()
            return True

        print(f"  🔄 Resetting {episodes_to_reset} episode sync flags...")

        # Reset sync flags
        await postgres.execute("""
            UPDATE episodes
            SET graphiti_synced = FALSE,
                graphiti_synced_at = NULL
            WHERE graphiti_synced = TRUE
        """)

        await postgres.disconnect()

        print(f"  ✅ Reset sync flags for {episodes_to_reset} episodes")
        return True

    except Exception as e:
        print(f"  ❌ Failed to reset sync flags ({type(e).__name__})")
        return False


async def clear_embeddings(target: str = "episodes", debug: bool = False) -> bool:
    """Clear embeddings from episodes or chunks"""
    try:
        postgres = await get_postgres_db()

        if target == "episodes":
            # Count episodes with embeddings
            count_result = await postgres.fetchrow("""
                SELECT COUNT(*) as count
                FROM episodes
                WHERE embedding IS NOT NULL
            """)

            items_to_clear = count_result["count"] if count_result else 0

            if items_to_clear == 0:
                print("  ℹ️  No episode embeddings to clear")
                await postgres.disconnect()
                return True

            print(f"  🔄 Clearing {items_to_clear} episode embeddings...")

            # Clear embeddings
            await postgres.execute("""
                UPDATE episodes
                SET embedding = NULL,
                    updated_at = NOW()
                WHERE embedding IS NOT NULL
            """)

            print(f"  ✅ Cleared embeddings for {items_to_clear} episodes")

        elif target == "chunks":
            # Count chunks with embeddings
            count_result = await postgres.fetchrow("""
                SELECT COUNT(*) as count
                FROM chunks
                WHERE embedding IS NOT NULL
            """)

            items_to_clear = count_result["count"] if count_result else 0

            if items_to_clear == 0:
                print("  ℹ️  No chunk embeddings to clear")
                await postgres.disconnect()
                return True

            print(f"  🔄 Clearing {items_to_clear} chunk embeddings...")

            # Clear embeddings
            await postgres.execute("""
                UPDATE chunks
                SET embedding = NULL,
                    updated_at = NOW()
                WHERE embedding IS NOT NULL
            """)

            print(f"  ✅ Cleared embeddings for {items_to_clear} chunks")

        await postgres.disconnect()
        return True

    except Exception as e:
        print(f"  ❌ Failed to clear {target} embeddings ({type(e).__name__})")
        return False


async def reset_document_processing(debug: bool = False) -> bool:
    """Reset document processing status"""
    try:
        postgres = await get_postgres_db()

        # Count documents that will be reset
        count_result = await postgres.fetchrow("""
            SELECT COUNT(*) as count
            FROM lore_documents
            WHERE processing_status IS NOT NULL
                AND processing_status != 'pending'
        """)

        docs_to_reset = count_result["count"] if count_result else 0

        if docs_to_reset == 0:
            print("  ℹ️  No processed documents to reset")
            await postgres.disconnect()
            return True

        print(f"  🔄 Resetting {docs_to_reset} document processing flags...")

        # Reset document processing
        await postgres.execute("""
            UPDATE lore_documents
            SET processed_at = NULL,
                processing_status = 'pending',
                updated_at = NOW()
            WHERE processing_status IS NOT NULL
                AND processing_status != 'pending'
        """)

        await postgres.disconnect()

        print(f"  ✅ Reset processing status for {docs_to_reset} documents")
        return True

    except Exception as e:
        print(f"  ❌ Failed to reset document processing ({type(e).__name__})")
        return False


async def reset_processing(targets: list[str], debug: bool = False, confirm: bool = False) -> bool:
    """Reset processing flags based on targets"""

    print("🔄 Processing Reset Utility")
    print("=" * 30)

    # Get current stats
    if debug:
        print("🔍 Checking current processing state...")
        stats = await get_processing_stats()
        if stats:
            format_processing_stats(stats)

    # Confirm destructive operations
    if not confirm and ("embeddings" in targets or "all" in targets):
        print("\n⚠️  WARNING: This will delete embedding data!")
        print(f"   Targets: {', '.join(targets)}")
        print("\n   Embeddings will need to be regenerated!")

        response = input("\nType 'yes' to proceed: ").strip().lower()
        if response != "yes":
            print("❌ Operation cancelled")
            return False

    print(f"\n🔄 Starting reset for targets: {', '.join(targets)}")

    success = True

    # Process each target
    if "sync" in targets or "all" in targets:
        print("\n📤 Resetting Graphiti sync flags...")
        if not await reset_sync_flags(debug):
            success = False

    if "embeddings" in targets or "all" in targets:
        print("\n🧮 Clearing embeddings...")
        if not await clear_embeddings("episodes", debug):
            success = False
        if not await clear_embeddings("chunks", debug):
            success = False

    if "documents" in targets or "all" in targets:
        print("\n📄 Resetting document processing...")
        if not await reset_document_processing(debug):
            success = False

    print("\n📊 Reset Summary:")
    if success:
        print(f"  ✅ Successfully reset: {', '.join(targets)}")
    else:
        print(f"  ❌ Some operations failed for: {', '.join(targets)}")

    # Show final stats if debug
    if debug:
        print("\n🔍 Final processing state...")
        final_stats = await get_processing_stats()
        if final_stats:
            format_processing_stats(final_stats)

    return success


async def show_status():
    """Show current processing status"""
    print("📊 Processing Status Check")
    print("=" * 25)

    stats = await get_processing_stats()
    if stats:
        format_processing_stats(stats)
    else:
        print("❌ Failed to retrieve processing statistics")


async def main():
    parser = argparse.ArgumentParser(
        description="Reset processing flags in PostgreSQL database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reset_processing.py --status                    # Check current status
  python reset_processing.py --target sync              # Reset only sync flags
  python reset_processing.py --target embeddings        # Clear only embeddings
  python reset_processing.py --target documents         # Reset only document processing
  python reset_processing.py --target all               # Reset everything
  python reset_processing.py --target sync,embeddings   # Reset multiple targets
  python reset_processing.py --target all --yes         # Skip confirmation

Available targets:
  sync        - Reset Graphiti sync flags (allows re-sync to Neo4j)
  embeddings  - Clear episode and chunk embeddings (allows re-generation)
  documents   - Reset document processing status (allows re-processing)
  all         - Reset everything above
        """,
    )

    parser.add_argument(
        "--target", help="Reset targets (comma-separated): sync, embeddings, documents, all"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show current processing status and exit"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")

    args = parser.parse_args()

    try:
        if args.status:
            await show_status()
            return

        if not args.target:
            parser.print_help()
            print("\nError: --target is required (unless using --status)")
            sys.exit(1)

        # Parse targets
        targets = [t.strip() for t in args.target.split(",")]
        valid_targets = {"sync", "embeddings", "documents", "all"}

        invalid_targets = set(targets) - valid_targets
        if invalid_targets:
            print(f"❌ Invalid targets: {', '.join(invalid_targets)}")
            print(f"Valid targets: {', '.join(sorted(valid_targets))}")
            sys.exit(1)

        success = await reset_processing(targets, args.debug, args.yes)
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error type: {type(e).__name__}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
