#!/usr/bin/env python3
"""
Reset database and reprocess documents with semantic chunking.

This script will:
1. Clear existing episodes and chunks
2. Reset document processing status
3. Reprocess canon documents with semantic chunking
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).parent))

from create_episodes_from_documents import create_episodes_from_documents
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from src.db import get_postgres_db

load_dotenv()

console = Console(force_terminal=True, force_interactive=True)


async def clear_database():
    """Clear existing episodes and chunks from database."""
    console.print(
        Panel.fit(
            "[bold red]⚠️  Database Reset[/bold red]\n\n"
            "[dim]This will clear all existing:[/dim]\n"
            "• Episodes table\n"
            "• Chunks table\n"
            "• Reset document processing status",
            border_style="red",
        )
    )

    # Connect to database
    with console.status("[bold yellow]Connecting to PostgreSQL..."):
        try:
            postgres = await get_postgres_db()
            console.print("✅ [bold green]Connected to PostgreSQL[/bold green]")
        except Exception as e:
            console.print(
                f"❌ [bold red]Failed to connect to PostgreSQL[/bold red] ({type(e).__name__})"
            )
            return False

    try:
        # Clear episodes table
        console.print("\n[yellow]Clearing episodes table...[/yellow]")
        await postgres.execute("DELETE FROM episodes")
        console.print("✅ [green]Cleared episodes table[/green]")

        # Clear chunks table
        console.print("[yellow]Clearing chunks table...[/yellow]")
        await postgres.execute("DELETE FROM chunks")
        console.print("✅ [green]Cleared chunks table[/green]")

        # Note: Document processing status will be reset by force_recreate in create_episodes_from_documents
        console.print("✅ [green]Document processing status will be reset automatically[/green]")

        await postgres.disconnect()
        return True

    except Exception as e:
        console.print(f"❌ [bold red]Failed to clear database[/bold red] ({type(e).__name__})")
        return False


async def reprocess_with_semantic_chunking():
    """Reprocess canon documents using semantic chunking."""

    console.print(
        Panel.fit(
            "[bold cyan]🧠 Semantic Chunking Reprocessing[/bold cyan]\n\n"
            "[dim]Using new semantic chunking parameters:[/dim]\n"
            "• Base tokens: 200\n"
            "• Token range: 100-500\n"
            "• Overlap: 25%\n"
            "• Similarity threshold: 0.7\n"
            "• Complexity factor: 1.5x",
            border_style="cyan",
        )
    )

    # Run episode creation with semantic chunking
    success = await create_episodes_from_documents(
        batch_size=25,  # Smaller batches for better progress tracking
        debug=True,
        base_tokens=200,
        min_tokens=100,
        max_tokens=500,
        overlap_percentage=0.25,
        similarity_threshold=0.7,
        complexity_factor=1.5,
        force_recreate=True,  # Recreate all canon documents
    )

    return success


async def main():
    """Main entry point for semantic chunking reset."""

    console.print("[bold cyan]Semantic Chunking Database Reset & Reprocessing[/bold cyan]")
    console.print("=" * 60)

    # Confirmation prompt
    if not Confirm.ask(
        "\n[bold yellow]This will clear all existing episodes and chunks. Continue?[/bold yellow]"
    ):
        console.print("[yellow]Operation cancelled.[/yellow]")
        return

    # Step 1: Clear database
    console.print("\n[bold blue]Step 1: Clearing Database[/bold blue]")
    if not await clear_database():
        console.print("[bold red]❌ Failed to clear database. Aborting.[/bold red]")
        sys.exit(1)

    console.print("\n✅ [bold green]Database cleared successfully![/bold green]")

    # Step 2: Reprocess with semantic chunking
    console.print("\n[bold blue]Step 2: Reprocessing with Semantic Chunking[/bold blue]")

    if await reprocess_with_semantic_chunking():
        console.print("\n🎉 [bold green]SUCCESS![/bold green]")
        console.print("Canon documents have been reprocessed with semantic chunking.")
        console.print("\n[dim]Next steps:[/dim]")
        console.print("1. Run embedding generation: [cyan]python generate_embeddings.py[/cyan]")
        console.print("2. Sync to Graphiti: [cyan]python sync_episodes_to_graphiti.py[/cyan]")
    else:
        console.print("\n❌ [bold red]FAILED![/bold red]")
        console.print("Some documents failed to process. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
