#!/usr/bin/env python3
"""Report Neo4j statistics and reject the retired untracked clear path."""

import argparse
import asyncio
import sys

# Add src to path for imports
sys.path.insert(0, "/app")

from src.db import get_neo4j_db


async def get_graph_stats() -> dict | None:
    """Get current graph statistics"""
    try:
        neo4j = await get_neo4j_db()

        # Get node counts by label
        node_stats = await neo4j.execute_query("""
            MATCH (n)
            RETURN labels(n) as labels, count(*) as count
            ORDER BY count DESC
        """)

        # Get relationship counts by type
        rel_stats = await neo4j.execute_query("""
            MATCH ()-[r]->()
            RETURN type(r) as relationship_type, count(*) as count
            ORDER BY count DESC
        """)

        node_records = node_stats.records if hasattr(node_stats, "records") else node_stats
        relationship_records = rel_stats.records if hasattr(rel_stats, "records") else rel_stats

        if hasattr(neo4j, "close"):
            await neo4j.close()
        elif hasattr(neo4j, "driver") and hasattr(neo4j.driver, "close"):
            await neo4j.driver.close()

        return {
            "nodes": node_records,
            "relationships": relationship_records,
            "totals": {
                "total_nodes": sum(record["count"] for record in node_records),
                "total_relationships": sum(record["count"] for record in relationship_records),
            },
        }

    except Exception as e:
        print(f"❌ Failed to get graph statistics ({type(e).__name__})")
        return None


def format_graph_stats(stats: dict):
    """Format graph statistics for display"""
    totals = stats["totals"]

    print("📊 Current Graph Contents:")
    print(f"  Total nodes: {totals['total_nodes']}")
    print(f"  Total relationships: {totals['total_relationships']}")

    if stats["nodes"]:
        print("\n  Nodes by type:")
        for record in stats["nodes"][:10]:  # Show top 10
            labels = record["labels"]
            label_str = ":".join(labels) if labels else "No Label"
            print(f"    {label_str}: {record['count']}")

        if len(stats["nodes"]) > 10:
            print(f"    ... and {len(stats['nodes']) - 10} more node types")

    if stats["relationships"]:
        print("\n  Relationships by type:")
        for record in stats["relationships"][:10]:  # Show top 10
            rel_type = record["relationship_type"]
            print(f"    {rel_type}: {record['count']}")

        if len(stats["relationships"]) > 10:
            print(f"    ... and {len(stats['relationships']) - 10} more relationship types")


async def clear_graph(confirm: bool = False, debug: bool = False) -> bool:
    """Reject untracked deletion; the status-only path remains supported."""
    del confirm, debug
    print(
        "Direct graph deletion is retired. Use graph_rebuild.py prepare with "
        "a verified backup and the exact confirmation token.",
        file=sys.stderr,
    )
    return False


async def main():
    parser = argparse.ArgumentParser(
        description="Report Neo4j graph statistics; direct deletion is retired",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clear_graph.py --status           # Show graph statistics without changing data

Deletion moved to the backup-gated durable graph rebuild workflow.
        """,
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Compatibility option; direct deletion is still refused",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument(
        "--status", action="store_true", help="Show graph statistics and exit without deleting data"
    )

    args = parser.parse_args()

    try:
        if args.status:
            stats = await get_graph_stats()
            if not stats:
                sys.exit(1)
            format_graph_stats(stats)
            return

        success = await clear_graph(confirm=args.yes, debug=args.debug)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error type: {type(e).__name__}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
