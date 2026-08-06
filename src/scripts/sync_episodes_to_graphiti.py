#!/usr/bin/env python3
"""
Sync episodes from PostgreSQL to Neo4j via Graphiti.

This script implements the hybrid Graph RAG architecture by:
1. Loading unsynced episodes from PostgreSQL
2. Sending them to Graphiti for entity extraction and graph creation
3. Storing UUID metadata to link PostgreSQL episodes with Neo4j episodes
4. Marking episodes as synced with resume capability

Environment variables used (from Docker container):
- POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
- OPENAI_API_KEY (for entity extraction)
"""

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

# Add src to path for imports
sys.path.insert(0, "/app")

from rich.console import Console

from src.db import get_postgres_db
from src.graphiti import initialize_graphiti

console = Console(force_terminal=True, force_interactive=True)


async def sync_episodes_bulk(
    postgres,
    graphiti,
    batch_size: int,
    debug: bool = False,
    max_episodes: int | None = None,
):
    """Bulk sync all pending episodes in bounded, resumable batches."""
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.utils.bulk_utils import RawEpisode

    from src.graphiti.edge_types import EDGE_TYPES
    from src.graphiti.entity_types import ENTITY_TYPES

    total_synced = 0
    total_failed = 0
    batch_size = max(1, batch_size)
    max_entities = max(1, int(os.getenv("GRAPHITI_MAX_ENTITIES_PER_EPISODE", "25")))
    max_relationships = max(1, int(os.getenv("GRAPHITI_MAX_RELATIONSHIPS_PER_EPISODE", "25")))

    console.print("📦 [bold blue]Using bulk sync mode (faster for large datasets)[/bold blue]")

    while max_episodes is None or total_synced < max_episodes:
        remaining = None if max_episodes is None else max_episodes - total_synced
        limit = batch_size if remaining is None else min(batch_size, remaining)
        episodes = await postgres.fetch(
            """
            SELECT id, text, document_id, episode_index, created_at
            FROM episodes
            WHERE graphiti_synced = FALSE
            ORDER BY created_at
            LIMIT $1
        """,
            limit,
        )

        if not episodes:
            print("✅ No unsynced episodes found")
            break

        print(
            f"📊 Preparing batch of {len(episodes)} episodes "
            f"({total_synced} synced this run)..."
        )

        bulk_episodes = []
        episode_ids = []
        episode_props = {}

        for episode in episodes:
            episode_id = episode["id"]
            document_id = episode["document_id"]

            # RawEpisode has no metadata field (pydantic silently drops unknown kwargs), so
            # these properties are written onto the Episodic node after the bulk load below.
            episode_props[episode_id] = {
                "document_id": str(document_id),
                "episode_index": episode["episode_index"],
                "synced_at": datetime.now(UTC).isoformat(),
            }

            # Create RawEpisode for bulk loading
            raw_episode = RawEpisode(
                name=f"episode_{episode_id}",
                content=episode["text"],
                source=EpisodeType.text,
                source_description=f"episode_{episode_id}",  # Use episode format for consistency
                reference_time=episode["created_at"],
            )

            bulk_episodes.append(raw_episode)
            episode_ids.append(episode_id)

        try:
            print(f"🚀 Bulk syncing {len(bulk_episodes)} episodes...")

            # LuminariGraphiti is a wrapper; graphiti-core's bulk API lives on
            # its ``graphiti`` member.
            await graphiti.graphiti.add_episode_bulk(
                bulk_episodes,
                entity_types=ENTITY_TYPES,
                edge_types=EDGE_TYPES,
                edge_type_map={("Entity", "Entity"): list(EDGE_TYPES.keys())},
                custom_extraction_instructions=(
                    "Return only the most important facts from each episode. "
                    f"Extract at most {max_entities} entities and at most "
                    f"{max_relationships} relationships per episode. "
                    "Do not repeat equivalent entities or relationships."
                ),
            )

            print("✅ Bulk sync completed, setting stable_id fields...")

            # Do not mark PostgreSQL rows synced unless cross-store linkage is
            # complete for every episode in this batch.
            linked_episodes = 0
            for episode in episodes:
                episode_id = episode["id"]
                result = await graphiti.driver.execute_query(
                    """
                    MATCH (ep:Episodic {source_description: $source_description})
                    SET ep.stable_id = $stable_id
                    SET ep += $extra_props
                    RETURN COUNT(ep) AS updated_count
                    """,
                    {
                        "source_description": f"episode_{episode_id}",
                        "stable_id": str(episode_id),
                        "extra_props": episode_props[episode_id],
                    },
                )
                records = result.records if hasattr(result, "records") else result
                linked_episodes += records[0]["updated_count"] if records else 0

            if linked_episodes != len(episodes):
                raise RuntimeError(
                    f"Linked {linked_episodes} of {len(episodes)} bulk episodes; "
                    "refusing to mark sync complete"
                )

            print(f"✅ Set stable_id fields for {linked_episodes} episodes")

            for episode_id in episode_ids:
                await postgres.execute(
                    """
                    UPDATE episodes
                    SET graphiti_synced = TRUE,
                        graphiti_synced_at = NOW()
                    WHERE id = $1
                    """,
                    episode_id,
                )

            total_synced += len(episodes)
            print(f"🎉 Batch complete: {total_synced} episodes synced this run")

        except Exception as error:
            total_failed += len(episodes)
            print(f"❌ Bulk sync batch failed ({type(error).__name__})")
            if debug:
                console.print_exception(show_locals=False)
            break

    return total_synced, total_failed


async def sync_episodes_incremental(
    postgres, graphiti, batch_size: int, debug: bool = False, max_episodes: int | None = None
):
    """Incremental sync episodes one by one (with resume capability)"""
    total_synced = 0
    total_failed = 0
    total_attempted = 0
    failed_episode_ids = []

    print("🔄 Using incremental sync mode (with resume capability)")

    while True:
        if max_episodes is not None and total_attempted >= max_episodes:
            print(f"🛑 Reached maximum episode limit ({max_episodes})")
            break

        fetch_limit = batch_size
        if max_episodes is not None:
            fetch_limit = min(fetch_limit, max_episodes - total_attempted)

        # Successful episodes disappear from this query after their status update.
        # Exclude failures seen during this invocation so one bad episode cannot
        # make an unattended resume loop forever.
        episodes = await postgres.fetch(
            """
            SELECT id, text, document_id, episode_index
            FROM episodes
            WHERE graphiti_synced = FALSE
              AND NOT (id = ANY($2::uuid[]))
            ORDER BY created_at
            LIMIT $1
        """,
            fetch_limit,
            failed_episode_ids,
        )

        if not episodes:
            print("✅ No more unsynced episodes found")
            break

        print(f"📦 Processing batch of {len(episodes)} episodes...")

        for episode in episodes:
            # Retry logic with exponential backoff for rate limiting
            max_retries = 5
            base_delay = 1.0  # Start with 1 second

            for attempt in range(max_retries):
                try:
                    episode_id = episode["id"]
                    document_id = episode["document_id"]

                    # Send episode to Graphiti using the working method with custom relationships
                    # This is critical for linking PostgreSQL episodes with Neo4j episodes
                    await graphiti.add_episode_with_lore_relationships(
                        content=episode["text"],
                        source_file=f"episode_{episode_id}",
                        metadata={
                            "episode_uuid": str(episode_id),  # Critical: Store PostgreSQL UUID
                            "document_id": str(document_id),
                            "episode_index": episode["episode_index"],
                            "synced_at": datetime.now(UTC).isoformat(),
                        },
                    )

                    # Ensure stable_id is set for GraphRAG linkage
                    # This is a fallback in case the automatic setting in add_episode_with_lore_relationships fails
                    try:
                        from src.db import get_neo4j_db

                        neo4j_db = await get_neo4j_db()

                        # Update any Episodic nodes that match our episode and don't have stable_id
                        await neo4j_db.execute_query(
                            """
                            MATCH (ep:Episodic)
                            WHERE ep.source_description = $source_description
                              AND ep.stable_id IS NULL
                            SET ep.stable_id = $stable_id
                            RETURN COUNT(ep) as updated_count
                        """,
                            {
                                "source_description": f"episode_{episode_id}",
                                "stable_id": str(episode_id),
                            },
                        )

                        # Close the Neo4j connection
                        if hasattr(neo4j_db, "close"):
                            await neo4j_db.close()
                        elif hasattr(neo4j_db, "driver") and hasattr(neo4j_db.driver, "close"):
                            await neo4j_db.driver.close()

                    except Exception as stable_id_error:
                        console.print(
                            "[yellow]Warning: Could not set stable_id for episode "
                            f"{episode_id} ({type(stable_id_error).__name__})[/yellow]"
                        )

                    # Mark as synced in PostgreSQL
                    await postgres.execute(
                        """
                        UPDATE episodes
                        SET graphiti_synced = TRUE,
                            graphiti_synced_at = NOW()
                        WHERE id = $1
                    """,
                        episode_id,
                    )

                    total_synced += 1
                    if debug:
                        console.print(
                            f"✅ [green]Synced episode {episode_id} (index {episode['episode_index']})[/green]"
                        )
                    else:
                        console.print(".", end="", style="green")

                    # Success - break out of retry loop
                    break

                except Exception as e:
                    error_msg = str(e).lower()

                    # Check if it's a rate limit error
                    if (
                        "rate limit" in error_msg
                        or "429" in error_msg
                        or "too many requests" in error_msg
                    ):
                        if attempt < max_retries - 1:  # Don't sleep on last attempt
                            wait_time = base_delay * (2**attempt)  # Exponential backoff
                            console.print(
                                f"\n⏳ [yellow]Rate limit hit on episode {episode['id']}, waiting {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})[/yellow]"
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            console.print(
                                f"\n❌ [red]Rate limit exceeded for episode {episode['id']} after {max_retries} attempts - skipping[/red]"
                            )
                            total_failed += 1
                            failed_episode_ids.append(episode["id"])
                            break
                    else:
                        # Non-rate-limit error - fail immediately
                        total_failed += 1
                        failed_episode_ids.append(episode["id"])
                        console.print(
                            f"\n❌ [red]Failed to sync episode {episode['id']} "
                            f"({type(e).__name__})[/red]"
                        )
                        break

            total_attempted += 1

            # Base throttling between episodes (reduced since we have retry logic)
            await asyncio.sleep(0.2)  # 200ms base delay

        if not debug:
            print()  # New line after dots

    return total_synced, total_failed


async def sync_episodes(
    batch_size: int = 5,
    debug: bool = False,
    max_episodes: int | None = None,
    bulk_mode: bool = False,
    force_bulk: bool = False,
):
    """Sync episodes from PostgreSQL to Neo4j via Graphiti"""

    print(f"🔄 Starting episode sync (batch_size={batch_size}, bulk_mode={bulk_mode})")
    total_synced = 0
    total_failed = 0

    # Get PostgreSQL connection
    try:
        postgres = await get_postgres_db()
        print("✅ Connected to PostgreSQL")
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL ({type(e).__name__})")
        return False

    # Initialize Graphiti (uses environment variables for credentials)
    try:
        graphiti = await initialize_graphiti()
        print("✅ Initialized Graphiti")
    except Exception as e:
        print(f"❌ Failed to initialize Graphiti ({type(e).__name__})")
        return False

    # Check if graph is empty for bulk mode optimization
    if bulk_mode:
        try:
            from src.db import get_neo4j_db

            neo4j = await get_neo4j_db()
            count_result = await neo4j.execute_query("MATCH (n) RETURN COUNT(n) as node_count")
            node_count = (
                count_result.records[0]["node_count"]
                if hasattr(count_result, "records") and count_result.records
                else count_result[0]["node_count"] if count_result else 0
            )

            if hasattr(neo4j, "close"):
                await neo4j.close()
            elif hasattr(neo4j, "driver") and hasattr(neo4j.driver, "close"):
                await neo4j.driver.close()

            if node_count > 0 and not force_bulk:
                print(
                    f"⚠️  Warning: Graph has {node_count} nodes. Bulk mode is recommended only for empty graphs."
                )
                print("   Use --force-bulk to override this check.")
                return False
            elif node_count > 0 and force_bulk:
                print(
                    f"⚠️  Warning: Graph has {node_count} nodes, but proceeding with bulk mode due to --force-bulk"
                )
            else:
                print("✅ Graph is empty - bulk mode is optimal")
        except Exception as e:
            print(f"⚠️  Could not check graph state ({type(e).__name__})")
            print("   Continuing with bulk mode anyway...")

    try:
        if bulk_mode:
            # Bulk sync mode - much faster for large datasets
            total_synced, total_failed = await sync_episodes_bulk(
                postgres, graphiti, batch_size, debug, max_episodes
            )
        else:
            # Standard incremental sync mode
            total_synced, total_failed = await sync_episodes_incremental(
                postgres, graphiti, batch_size, debug, max_episodes
            )

    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Sync failed ({type(e).__name__})")
    finally:
        # Cleanup
        try:
            await graphiti.close()
            await postgres.disconnect()
        except Exception as e:
            if debug:
                print(f"Warning: cleanup failed ({type(e).__name__})")

    print("\n📊 Sync Summary:")
    print(f"  ✅ Episodes synced: {total_synced}")
    print(f"  ❌ Episodes failed: {total_failed}")

    return total_failed == 0


async def check_sync_status():
    """Check current sync status"""
    try:
        postgres = await get_postgres_db()

        # Get sync statistics
        stats = await postgres.fetchrow("""
            SELECT
                COUNT(*) as total_episodes,
                COUNT(*) FILTER (WHERE graphiti_synced = TRUE) as synced_episodes,
                COUNT(*) FILTER (WHERE graphiti_synced = FALSE) as unsynced_episodes,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) as episodes_with_embeddings
            FROM episodes
        """)

        print("📊 Episode Sync Status:")
        print(f"  Total episodes: {stats['total_episodes']}")
        print(f"  Synced to Graphiti: {stats['synced_episodes']}")
        print(f"  Unsynced: {stats['unsynced_episodes']}")
        print(f"  With embeddings: {stats['episodes_with_embeddings']}")

        await postgres.close()

    except Exception as e:
        print(f"❌ Failed to check sync status ({type(e).__name__})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync episodes from PostgreSQL to Neo4j via Graphiti",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_episodes_to_graphiti.py --status
  python sync_episodes_to_graphiti.py --batch-size 5 --debug
  python sync_episodes_to_graphiti.py --max-episodes 100
  python sync_episodes_to_graphiti.py --bulk              # Fast bulk sync for empty graphs
  python sync_episodes_to_graphiti.py --force-bulk        # Force bulk sync (dangerous!)

Sync Modes:
  Incremental: Episodes synced one by one with resume capability (default)
  Bulk:        All episodes synced at once using Graphiti's bulk API (much faster)

Bulk mode is recommended for:
  - Initial sync when graph is empty
  - Large datasets (1000+ episodes)
  - When you don't need resume capability

Use incremental mode for:
  - Adding new episodes to existing graph
  - Resume capability after interruption
  - Smaller datasets or testing
        """,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of episodes to process per batch (default: 5)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--max-episodes", type=int, help="Maximum number of episodes to sync (default: unlimited)"
    )
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="Use bulk sync mode (much faster, recommended for empty graphs)",
    )
    parser.add_argument(
        "--force-bulk",
        action="store_true",
        help="Force bulk mode even if graph is not empty (dangerous!)",
    )
    parser.add_argument("--status", action="store_true", help="Check sync status and exit")

    args = parser.parse_args()

    if args.status:
        asyncio.run(check_sync_status())
    else:
        # Enable bulk mode if --bulk or --force-bulk is specified
        bulk_mode = args.bulk or args.force_bulk
        success = asyncio.run(
            sync_episodes(
                batch_size=args.batch_size,
                debug=args.debug,
                max_episodes=args.max_episodes,
                bulk_mode=bulk_mode,
                force_bulk=args.force_bulk,
            )
        )
        sys.exit(0 if success else 1)
