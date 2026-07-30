#!/usr/bin/env python3
"""
Migration script to add stable_id to existing Episodic nodes in Neo4j.

This script fixes the broken linkage between PostgreSQL episodes and Neo4j Episodic nodes
by extracting episode UUIDs from the source_description field and setting them as stable_id.

Environment variables used (from Docker container):
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

Usage:
    python migrate_episodic_stable_ids.py --dry-run    # Preview what will be updated
    python migrate_episodic_stable_ids.py             # Actually perform the migration
"""

import argparse
import asyncio
import re
import sys

# Add src to path for imports
sys.path.insert(0, "/app")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.db import get_neo4j_db

console = Console(force_terminal=True, force_interactive=True)


async def analyze_episodic_nodes(dry_run: bool = True):
    """Analyze existing Episodic nodes and plan migration."""

    console.print(
        Panel.fit(
            f"[bold cyan]🔍 Episodic Node Analysis[/bold cyan]\n\n"
            f"[dim]Mode:[/dim] {'Dry Run (Preview Only)' if dry_run else 'Live Migration'}\n"
            f"[dim]Purpose:[/dim] Add stable_id to link with PostgreSQL episodes",
            border_style="cyan",
        )
    )

    try:
        neo4j_db = await get_neo4j_db()

        # Get all Episodic nodes with their current properties
        result = await neo4j_db.execute_query("""
            MATCH (ep:Episodic)
            RETURN
                ep.uuid as neo4j_uuid,
                ep.name as name,
                ep.source_description as source_description,
                ep.stable_id as stable_id,
                ep.created_at as created_at
            ORDER BY ep.created_at
        """)

        # Extract results based on Neo4j driver version
        records = result.records if hasattr(result, "records") else result

        console.print(f"\n📊 Found {len(records)} Episodic nodes")

        # Analyze the nodes and plan updates
        nodes_to_update = []
        nodes_with_stable_id = []
        nodes_unparseable = []

        for record in records:
            neo4j_uuid = record["neo4j_uuid"]
            name = record["name"]
            source_description = record["source_description"]
            stable_id = record["stable_id"]
            created_at = record["created_at"]

            if stable_id:
                # Already has stable_id
                nodes_with_stable_id.append(
                    {
                        "neo4j_uuid": neo4j_uuid,
                        "name": name,
                        "stable_id": stable_id,
                        "source_description": source_description,
                    }
                )
            else:
                # Try to extract episode UUID from source_description
                extracted_uuid = None

                if source_description:
                    # Pattern 1: episode_<uuid>
                    match = re.match(
                        r"episode_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                        source_description,
                    )
                    if match:
                        extracted_uuid = match.group(1)
                    else:
                        # Pattern 2: doc_<uuid> (from bulk mode)
                        match = re.match(
                            r"doc_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                            source_description,
                        )
                        if match:
                            # This is a document UUID, we need to look it up in PostgreSQL
                            # For now, we'll try to extract from the name field
                            if name:
                                name_match = re.search(
                                    r"episode_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                                    name,
                                )
                                if name_match:
                                    extracted_uuid = name_match.group(1)

                if extracted_uuid:
                    nodes_to_update.append(
                        {
                            "neo4j_uuid": neo4j_uuid,
                            "name": name,
                            "source_description": source_description,
                            "extracted_uuid": extracted_uuid,
                            "created_at": created_at,
                        }
                    )
                else:
                    nodes_unparseable.append(
                        {
                            "neo4j_uuid": neo4j_uuid,
                            "name": name,
                            "source_description": source_description,
                        }
                    )

        # Display analysis results
        table = Table(title="Migration Analysis")
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_column("Description", style="white")

        table.add_row(
            "Already have stable_id", str(len(nodes_with_stable_id)), "✅ No action needed"
        )
        table.add_row("Can extract UUID", str(len(nodes_to_update)), "🔄 Will set stable_id")
        table.add_row("Cannot parse UUID", str(len(nodes_unparseable)), "❌ Manual review needed")
        table.add_row("Total", str(len(records)), "📊 All Episodic nodes")

        console.print(table)

        # Show sample nodes to update
        if nodes_to_update:
            console.print("\n[bold green]Sample nodes that will be updated:[/bold green]")
            sample_table = Table()
            sample_table.add_column("Neo4j UUID", style="dim")
            sample_table.add_column("Source Description", style="cyan")
            sample_table.add_column("→ stable_id", style="green")

            for node in nodes_to_update[:5]:  # Show first 5
                sample_table.add_row(
                    node["neo4j_uuid"][:8] + "...",
                    node["source_description"],
                    node["extracted_uuid"],
                )

            if len(nodes_to_update) > 5:
                sample_table.add_row("...", f"+ {len(nodes_to_update) - 5} more", "...")

            console.print(sample_table)

        # Show unparseable nodes if any
        if nodes_unparseable:
            console.print(
                "\n[bold yellow]Nodes that cannot be automatically updated:[/bold yellow]"
            )
            problem_table = Table()
            problem_table.add_column("Neo4j UUID", style="dim")
            problem_table.add_column("Name", style="yellow")
            problem_table.add_column("Source Description", style="yellow")

            for node in nodes_unparseable:
                problem_table.add_row(
                    node["neo4j_uuid"][:8] + "...",
                    (
                        node["name"][:50] + "..."
                        if node["name"] and len(node["name"]) > 50
                        else node["name"] or "None"
                    ),
                    node["source_description"] or "None",
                )

            console.print(problem_table)

        # Perform migration if not dry run
        if not dry_run and nodes_to_update:
            console.print(
                f"\n[bold red]🚀 Performing migration of {len(nodes_to_update)} nodes...[/bold red]"
            )

            updated_count = 0
            for node in nodes_to_update:
                try:
                    await neo4j_db.execute_query(
                        """
                        MATCH (ep:Episodic)
                        WHERE ep.uuid = $neo4j_uuid
                        SET ep.stable_id = $stable_id
                        RETURN ep
                    """,
                        {"neo4j_uuid": node["neo4j_uuid"], "stable_id": node["extracted_uuid"]},
                    )

                    updated_count += 1
                    console.print(
                        f"✅ Updated {node['neo4j_uuid'][:8]}... → {node['extracted_uuid']}"
                    )

                except Exception as e:
                    console.print(
                        f"❌ Failed to update {node['neo4j_uuid'][:8]}... ({type(e).__name__})"
                    )

            console.print(
                f"\n[bold green]🎉 Migration completed: {updated_count}/{len(nodes_to_update)} nodes updated[/bold green]"
            )

        # Close connection
        if hasattr(neo4j_db, "close"):
            await neo4j_db.close()
        elif hasattr(neo4j_db, "driver") and hasattr(neo4j_db.driver, "close"):
            await neo4j_db.driver.close()

        return len(nodes_to_update), len(nodes_unparseable)

    except Exception as e:
        console.print(f"[red]❌ Migration failed ({type(e).__name__})[/red]")
        return 0, 0


async def verify_migration():
    """Verify that migration was successful by checking stable_id coverage."""

    console.print("\n[bold cyan]🔍 Verifying migration results...[/bold cyan]")

    try:
        neo4j_db = await get_neo4j_db()

        # Get statistics on stable_id coverage
        result = await neo4j_db.execute_query("""
            MATCH (ep:Episodic)
            RETURN
                COUNT(ep) as total_episodic,
                COUNT(ep.stable_id) as with_stable_id,
                COUNT(ep) - COUNT(ep.stable_id) as without_stable_id
        """)

        # Extract results
        record = result.records[0] if hasattr(result, "records") else result[0]

        total = record["total_episodic"]
        with_stable_id = record["with_stable_id"]
        without_stable_id = record["without_stable_id"]

        console.print("📊 Migration Verification:")
        console.print(f"  Total Episodic nodes: {total}")
        console.print(f"  With stable_id: {with_stable_id} ({with_stable_id / total * 100:.1f}%)")
        console.print(
            f"  Without stable_id: {without_stable_id} ({without_stable_id / total * 100:.1f}%)"
        )

        if without_stable_id == 0:
            console.print("✅ [bold green]Perfect! All Episodic nodes have stable_id[/bold green]")
        elif without_stable_id < total * 0.1:  # Less than 10% missing
            console.print(
                "🟡 [bold yellow]Good! Most nodes have stable_id, manual review needed for remainder[/bold yellow]"
            )
        else:
            console.print("❌ [bold red]Issue! Many nodes still missing stable_id[/bold red]")

        # Close connection
        if hasattr(neo4j_db, "close"):
            await neo4j_db.close()
        elif hasattr(neo4j_db, "driver") and hasattr(neo4j_db.driver, "close"):
            await neo4j_db.driver.close()

        return with_stable_id == total

    except Exception as e:
        console.print(f"[red]❌ Verification failed ({type(e).__name__})[/red]")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate Episodic nodes to have stable_id for GraphRAG linkage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python migrate_episodic_stable_ids.py --dry-run     # Preview changes
  python migrate_episodic_stable_ids.py              # Perform migration
  python migrate_episodic_stable_ids.py --verify     # Just verify current state

Purpose:
This script fixes the broken linkage between PostgreSQL episodes and Neo4j Episodic nodes
by extracting episode UUIDs from existing source_description and name fields and setting
them as stable_id properties. This enables the GraphRAG system to properly expand from
vector search results to graph entities and relationships.
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying data (default: false)",
    )
    parser.add_argument(
        "--verify", action="store_true", help="Just verify current stable_id coverage"
    )

    args = parser.parse_args()

    if args.verify:
        success = asyncio.run(verify_migration())
        sys.exit(0 if success else 1)
    else:
        nodes_updated, nodes_failed = asyncio.run(analyze_episodic_nodes(dry_run=args.dry_run))

        if not args.dry_run:
            # Also run verification after migration
            asyncio.run(verify_migration())

        sys.exit(0 if nodes_failed == 0 else 1)
