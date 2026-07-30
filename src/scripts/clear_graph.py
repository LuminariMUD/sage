#!/usr/bin/env python3
"""
Clear all nodes and relationships from Neo4j graph database.

This utility script provides a way to completely reset the Neo4j knowledge graph,
which is useful during development and testing of the Graph RAG system.

Environment variables used (from Docker container):
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

Safety features:
- Interactive confirmation by default
- --yes flag to skip confirmation for automation
- Detailed progress reporting
- Graceful error handling
"""

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

        # Get total counts
        totals = await neo4j.execute_query("""
            MATCH (n)
            OPTIONAL MATCH ()-[r]->()
            RETURN count(DISTINCT n) as total_nodes, count(r) as total_relationships
        """)

        if hasattr(neo4j, "close"):
            await neo4j.close()
        elif hasattr(neo4j, "driver") and hasattr(neo4j.driver, "close"):
            await neo4j.driver.close()

        return {
            "nodes": node_stats.records if hasattr(node_stats, "records") else node_stats,
            "relationships": rel_stats.records if hasattr(rel_stats, "records") else rel_stats,
            "totals": (
                totals.records[0]
                if (hasattr(totals, "records") and totals.records)
                else totals[0] if totals else {"total_nodes": 0, "total_relationships": 0}
            ),
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
    """Clear all nodes and relationships from Neo4j"""

    print("🗑️  Neo4j Graph Clearing Utility")
    print("=" * 40)

    # Get current graph stats
    if debug:
        print("🔍 Checking current graph state...")

    stats = await get_graph_stats()
    if stats:
        format_graph_stats(stats)

        total_nodes = stats["totals"]["total_nodes"]
        total_relationships = stats["totals"]["total_relationships"]

        if total_nodes == 0 and total_relationships == 0:
            print("\n✅ Graph is already empty!")
            return True
    else:
        print("⚠️  Could not retrieve graph statistics")
        total_nodes = "unknown"
        total_relationships = "unknown"

    # Confirmation
    if not confirm:
        print("\n⚠️  WARNING: This will permanently DELETE ALL graph data!")
        print(f"   Nodes to delete: {total_nodes}")
        print(f"   Relationships to delete: {total_relationships}")
        print("\n   This action cannot be undone!")

        response = input("\nType 'yes' to proceed with deletion: ").strip().lower()
        if response != "yes":
            print("❌ Operation cancelled")
            return False

    print("\n🗑️  Starting graph deletion...")

    try:
        neo4j = await get_neo4j_db()

        # Delete all relationships first (required by Neo4j)
        if debug:
            print("🔄 Deleting all relationships...")

        rel_result = await neo4j.execute_query("MATCH ()-[r]->() DELETE r")

        if debug and hasattr(rel_result, "summary") and hasattr(rel_result.summary, "counters"):
            deleted_rels = rel_result.summary.counters.relationships_deleted
            print(f"   ✅ Deleted {deleted_rels} relationships")
        else:
            print("   ✅ Deleted all relationships")

        # Delete all nodes
        if debug:
            print("🔄 Deleting all nodes...")

        node_result = await neo4j.execute_query("MATCH (n) DELETE n")

        if debug and hasattr(node_result, "summary") and hasattr(node_result.summary, "counters"):
            deleted_nodes = node_result.summary.counters.nodes_deleted
            print(f"   ✅ Deleted {deleted_nodes} nodes")
        else:
            print("   ✅ Deleted all nodes")

        if hasattr(neo4j, "close"):
            await neo4j.close()
        elif hasattr(neo4j, "driver") and hasattr(neo4j.driver, "close"):
            await neo4j.driver.close()

        print("\n🎉 Graph cleared successfully!")

        # Verify the graph is empty
        if debug:
            print("\n🔍 Verifying graph is empty...")
            final_stats = await get_graph_stats()
            if final_stats:
                totals = final_stats["totals"]
                if totals["total_nodes"] == 0 and totals["total_relationships"] == 0:
                    print("   ✅ Verification passed - graph is empty")
                else:
                    print(
                        f"   ⚠️  Warning: Still found {totals['total_nodes']} nodes and {totals['total_relationships']} relationships"
                    )

        return True

    except Exception as e:
        print(f"\n❌ Failed to clear graph ({type(e).__name__})")
        return False


async def main():
    parser = argparse.ArgumentParser(
        description="Clear all nodes and relationships from Neo4j graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clear_graph.py                    # Interactive confirmation
  python clear_graph.py --yes             # Skip confirmation
  python clear_graph.py --yes --debug     # Skip confirmation with debug output

Warning: This operation permanently deletes all graph data and cannot be undone!
        """,
    )

    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt (dangerous!)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    try:
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
