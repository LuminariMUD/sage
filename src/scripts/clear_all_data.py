#!/usr/bin/env python3
"""
Clear all data from PostgreSQL and Neo4j for fresh pipeline run.

This script safely removes all processed data while preserving:
- Original document files in PostgreSQL
- Database schemas and indexes
- Configuration and credentials

Environment variables used:
- POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
"""

import asyncio
import sys

# Add src to path for imports
sys.path.insert(0, "/app")

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from src.db import get_neo4j_db, get_postgres_db

console = Console(force_terminal=True, force_interactive=True)


async def clear_postgresql_processed_data():
    """Clear all processed data from PostgreSQL, keeping documents."""

    console.print("[bold yellow]🗑️  Clearing PostgreSQL processed data...[/bold yellow]")

    try:
        postgres = await get_postgres_db()

        # Check what we have before clearing
        doc_count = await postgres.fetchval("SELECT COUNT(*) FROM documents")
        episode_count = await postgres.fetchval("SELECT COUNT(*) FROM episodes")

        console.print(f"  📊 Current state: {doc_count} documents, {episode_count} episodes")

        # Clear episodes table (keep documents - they're the source material)
        await postgres.execute("TRUNCATE TABLE episodes CASCADE")
        console.print("  ✅ Cleared episodes table")

        # Reset document processing flags
        await postgres.execute("""
            UPDATE documents
            SET processed = FALSE,
                processing_error = NULL,
                last_processed_at = NULL
        """)
        console.print("  ✅ Reset document processing flags")

        # Check final state
        remaining_episodes = await postgres.fetchval("SELECT COUNT(*) FROM episodes")
        await postgres.fetchval("SELECT COUNT(*) FROM documents WHERE processed = FALSE")

        console.print(
            f"  📊 After clearing: {doc_count} documents (reset for processing), {remaining_episodes} episodes"
        )

        await postgres.disconnect()
        return True

    except Exception as e:
        console.print(f"[red]❌ Failed to clear PostgreSQL data ({type(e).__name__})[/red]")
        return False


async def clear_neo4j_all_data():
    """Clear ALL data from Neo4j."""

    console.print("[bold red]🗑️  Clearing ALL Neo4j data...[/bold red]")

    try:
        neo4j_db = await get_neo4j_db()

        # Check what we have before clearing
        node_count = await neo4j_db.execute_query("MATCH (n) RETURN COUNT(n) as count")
        rel_count = await neo4j_db.execute_query("MATCH ()-[r]->() RETURN COUNT(r) as count")

        node_total = node_count[0]["count"] if node_count else 0
        rel_total = rel_count[0]["count"] if rel_count else 0

        console.print(f"  📊 Current state: {node_total} nodes, {rel_total} relationships")

        if node_total > 0 or rel_total > 0:
            # Clear all data - this is the most efficient way for large datasets
            await neo4j_db.execute_query("MATCH (n) DETACH DELETE n")
            console.print("  ✅ Cleared all nodes and relationships")

            # Verify clearing worked
            final_nodes = await neo4j_db.execute_query("MATCH (n) RETURN COUNT(n) as count")
            final_rels = await neo4j_db.execute_query("MATCH ()-[r]->() RETURN COUNT(r) as count")

            final_node_count = final_nodes[0]["count"] if final_nodes else 0
            final_rel_count = final_rels[0]["count"] if final_rels else 0

            console.print(
                f"  📊 After clearing: {final_node_count} nodes, {final_rel_count} relationships"
            )

            if final_node_count > 0 or final_rel_count > 0:
                console.print("[yellow]⚠️  Warning: Some data remains after clearing[/yellow]")
        else:
            console.print("  ✅ Neo4j already empty")

        # Close connection
        if hasattr(neo4j_db, "close"):
            await neo4j_db.close()
        elif hasattr(neo4j_db, "driver") and hasattr(neo4j_db.driver, "close"):
            await neo4j_db.driver.close()

        return True

    except Exception as e:
        console.print(f"[red]❌ Failed to clear Neo4j data ({type(e).__name__})[/red]")
        return False


async def verify_clearing():
    """Verify that data was successfully cleared."""

    console.print("\n[bold cyan]🔍 Verifying data clearing...[/bold cyan]")

    success = True

    try:
        # Check PostgreSQL
        postgres = await get_postgres_db()

        doc_count = await postgres.fetchval("SELECT COUNT(*) FROM documents")
        episode_count = await postgres.fetchval("SELECT COUNT(*) FROM episodes")
        unprocessed_docs = await postgres.fetchval(
            "SELECT COUNT(*) FROM documents WHERE processed = FALSE"
        )

        console.print("PostgreSQL verification:")
        console.print(f"  📄 Documents: {doc_count} (preserved)")
        console.print(f"  📑 Episodes: {episode_count} (should be 0)")
        console.print(f"  🔄 Unprocessed docs: {unprocessed_docs} (should equal total docs)")

        if episode_count > 0:
            console.print(f"[yellow]⚠️  Warning: {episode_count} episodes remain[/yellow]")
            success = False

        if unprocessed_docs != doc_count:
            console.print("[yellow]⚠️  Warning: Not all documents reset for reprocessing[/yellow]")
            success = False

        await postgres.disconnect()

        # Check Neo4j
        neo4j_db = await get_neo4j_db()

        node_result = await neo4j_db.execute_query("MATCH (n) RETURN COUNT(n) as count")
        rel_result = await neo4j_db.execute_query("MATCH ()-[r]->() RETURN COUNT(r) as count")

        node_count = node_result[0]["count"] if node_result else 0
        rel_count = rel_result[0]["count"] if rel_result else 0

        console.print("Neo4j verification:")
        console.print(f"  🔵 Nodes: {node_count} (should be 0)")
        console.print(f"  🔗 Relationships: {rel_count} (should be 0)")

        if node_count > 0 or rel_count > 0:
            console.print("[yellow]⚠️  Warning: Neo4j not completely cleared[/yellow]")
            success = False

        # Close connection
        if hasattr(neo4j_db, "close"):
            await neo4j_db.close()
        elif hasattr(neo4j_db, "driver") and hasattr(neo4j_db.driver, "close"):
            await neo4j_db.driver.close()

        if success:
            console.print(
                "\n[bold green]✅ Data clearing successful! Ready for fresh pipeline run.[/bold green]"
            )
        else:
            console.print(
                "\n[bold yellow]⚠️  Data clearing had issues. Please review above.[/bold yellow]"
            )

        return success

    except Exception as e:
        console.print(f"[red]❌ Verification failed ({type(e).__name__})[/red]")
        return False


async def main():
    """Main clearing function."""

    console.print(
        Panel.fit(
            "[bold red]🗑️  Database Data Clearing[/bold red]\n\n"
            "[dim]This will clear:[/dim]\n"
            "  • All episodes from PostgreSQL\n"
            "  • All nodes and relationships from Neo4j\n"
            "  • Reset document processing flags\n\n"
            "[dim]This will preserve:[/dim]\n"
            "  • Original documents in PostgreSQL\n"
            "  • Database schemas and indexes\n"
            "  • Configuration and credentials",
            border_style="red",
        )
    )

    # Interactive confirmation for safety
    if not Confirm.ask("\n[bold red]Are you sure you want to clear all processed data?[/bold red]"):
        console.print("[yellow]❌ Cancelled by user[/yellow]")
        return False

    console.print("\n[bold cyan]🚀 Starting data clearing process...[/bold cyan]")

    # Clear PostgreSQL processed data
    pg_success = await clear_postgresql_processed_data()

    # Clear Neo4j data
    neo4j_success = await clear_neo4j_all_data()

    # Verify clearing
    verify_success = await verify_clearing()

    overall_success = pg_success and neo4j_success and verify_success

    if overall_success:
        console.print("\n[bold green]🎉 All data successfully cleared![/bold green]")
        console.print("\n[bold cyan]Next steps:[/bold cyan]")
        console.print("  1. Run: make semantic-pipeline")
        console.print("  2. Or run individual steps:")
        console.print("     - make create-episodes")
        console.print("     - make generate-embeddings")
        console.print("     - make sync-to-graphiti")
    else:
        console.print(
            "\n[bold red]❌ Data clearing encountered issues. Please review above.[/bold red]"
        )

    return overall_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
