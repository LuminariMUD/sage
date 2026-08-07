#!/usr/bin/env python3
"""
Convert documents in PostgreSQL into episodes for hybrid Graph RAG pipeline.

This script processes documents in the lore_documents table and splits them
into episodes stored in the episodes table, ready for embedding generation
and Graphiti sync.

Environment variables used (from Docker container):
- POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, "/app")

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from src.db import get_postgres_db

# Import semantic chunker
try:
    from semantic_chunker import SemanticChunker
except ImportError:
    # Try to import from scripts directory
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from semantic_chunker import SemanticChunker
# Temporal metadata extraction removed - let Graphiti handle it with context

load_dotenv()

console = Console(force_terminal=True, force_interactive=True)


class EpisodeCreator:
    """Convert documents to episodes using semantic chunking"""

    def __init__(
        self,
        base_tokens: int = 200,
        min_tokens: int = 100,
        max_tokens: int = 500,
        overlap_percentage: float = 0.25,
        similarity_threshold: float = 0.7,
        complexity_factor: float = 1.5,
    ):
        self.semantic_chunker = SemanticChunker(
            base_tokens=base_tokens,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            overlap_percentage=overlap_percentage,
            similarity_threshold=similarity_threshold,
            complexity_factor=complexity_factor,
        )

    def split_text_into_episodes(self, text: str, title: str = "") -> list[str]:
        """Split text into semantically coherent episodes with intelligent overlap"""

        if not text.strip():
            return []

        # Use semantic chunker to create chunks
        chunks = self.semantic_chunker.create_semantic_chunks(text, title)

        # Extract just the text from each chunk
        episodes = [chunk["text"] for chunk in chunks]

        return episodes


async def create_episodes_from_documents(
    batch_size: int = 50,
    debug: bool = False,
    base_tokens: int = 200,
    min_tokens: int = 100,
    max_tokens: int = 500,
    overlap_percentage: float = 0.25,
    similarity_threshold: float = 0.7,
    complexity_factor: float = 1.5,
    max_documents: int | None = None,
    force_recreate: bool = False,
):
    """Create episodes from canon documents in PostgreSQL."""

    console.print(
        Panel.fit(
            f"[bold cyan]📄 Document → Episodes Conversion (Semantic Chunking)[/bold cyan]\n\n"
            f"[dim]Base tokens:[/dim] {base_tokens:,}\n"
            f"[dim]Token range:[/dim] {min_tokens}-{max_tokens}\n"
            f"[dim]Overlap percentage:[/dim] {overlap_percentage:.1%}\n"
            f"[dim]Similarity threshold:[/dim] {similarity_threshold}\n"
            f"[dim]Complexity factor:[/dim] {complexity_factor}x\n"
            f"[dim]Batch size:[/dim] {batch_size}\n"
            f"[dim]Force recreate:[/dim] {'Yes' if force_recreate else 'No'}",
            border_style="cyan",
        )
    )

    # Get PostgreSQL connection
    with console.status("[bold green]Connecting to PostgreSQL..."):
        try:
            postgres = await get_postgres_db()
            console.print("✅ [bold green]Connected to PostgreSQL[/bold green]")
        except Exception as e:
            console.print(
                f"❌ [bold red]Failed to connect to PostgreSQL[/bold red] ({type(e).__name__})"
            )
            return False

    episode_creator = EpisodeCreator(
        base_tokens=base_tokens,
        min_tokens=min_tokens,
        max_tokens=max_tokens,
        overlap_percentage=overlap_percentage,
        similarity_threshold=similarity_threshold,
        complexity_factor=complexity_factor,
    )
    total_processed = 0
    total_episodes_created = 0
    total_failed = 0

    # Handle force_recreate by resetting status once at the start
    if force_recreate:
        console.print(
            "[yellow]Force recreate enabled - resetting canon processing status...[/yellow]"
        )
        await postgres.execute("""
            UPDATE lore_documents
            SET processing_status = NULL,
                processed_at = NULL,
                updated_at = NOW()
            WHERE canonical IS TRUE
              AND source_file LIKE 'canon/%'
        """)
        console.print("✅ [green]Reset processing status for canon documents[/green]")

    try:
        while True:
            # Get documents that haven't been processed
            documents = await postgres.fetch(
                """
                SELECT id, title, body_md, document_type, source_file
                FROM lore_documents
                WHERE canonical IS TRUE
                  AND source_file LIKE 'canon/%'
                  AND (processing_status != 'completed' OR processing_status IS NULL)
                ORDER BY created_at
                LIMIT $1
            """,
                batch_size,
            )

            if not documents:
                console.print("✅ [bold green]No more documents to process[/bold green]")
                break

            if max_documents and total_processed >= max_documents:
                console.print(
                    f"🛑 [yellow]Reached maximum document limit ({max_documents})[/yellow]"
                )
                break

            # Create progress bar for this batch
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.fields[doc_title]}", justify="left"),
                BarColumn(bar_width=None),
                "[progress.percentage]{task.percentage:>3.1f}%",
                "•",
                TextColumn("[bold green]{task.fields[episodes]} episodes", justify="right"),
                TimeRemainingColumn(),
                console=console,
                expand=True,
            ) as progress:
                batch_task = progress.add_task(
                    f"Processing {len(documents)} documents...",
                    total=len(documents),
                    doc_title="Starting batch",
                    episodes="0",
                )

                for i, doc in enumerate(documents):
                    if max_documents and total_processed >= max_documents:
                        break

                    try:
                        document_id = doc["id"]
                        title = (
                            doc["title"][:50] + "..." if len(doc["title"]) > 50 else doc["title"]
                        )
                        body_md = doc["body_md"]

                        # Update progress bar
                        progress.update(
                            batch_task,
                            completed=i,
                            doc_title=f"📄 {title}",
                            episodes=str(total_episodes_created),
                        )

                        # Clear existing episodes if recreating
                        if force_recreate:
                            await postgres.execute(
                                """
                                DELETE FROM episodes WHERE document_id = $1
                            """,
                                document_id,
                            )

                        # Split document into regular episodes using semantic chunking
                        episode_texts = episode_creator.split_text_into_episodes(
                            body_md, doc["title"]
                        )

                        # Insert episodes
                        episodes_created = 0
                        for idx, episode_text in enumerate(episode_texts):
                            episode_index = idx
                            try:
                                await postgres.execute(
                                    """
                                    INSERT INTO episodes (document_id, episode_index, text, created_at)
                                    VALUES ($1, $2, $3, NOW())
                                    ON CONFLICT (document_id, episode_index)
                                    DO UPDATE SET text = EXCLUDED.text, updated_at = NOW()
                                """,
                                    document_id,
                                    episode_index,
                                    episode_text,
                                )
                                episodes_created += 1
                            except Exception as e:
                                if debug:
                                    console.print(
                                        f"   ❌ [red]Failed to insert episode {episode_index}[/red] "
                                        f"({type(e).__name__})"
                                    )

                        # Mark document as processed
                        await postgres.execute(
                            """
                            UPDATE lore_documents
                            SET processing_status = 'completed',
                                processed_at = NOW(),
                                updated_at = NOW()
                            WHERE id = $1
                        """,
                            document_id,
                        )

                        total_processed += 1
                        total_episodes_created += episodes_created

                        # Update final progress for this document
                        progress.update(
                            batch_task,
                            completed=i + 1,
                            doc_title=f"✅ {title}",
                            episodes=str(total_episodes_created),
                        )

                    except Exception as e:
                        total_failed += 1
                        doc_title = (doc["title"] or str(doc["id"]))[:50]
                        console.print(
                            f"❌ [red]Failed to process {doc_title}[/red] ({type(e).__name__})"
                        )

                        # Mark as failed
                        try:
                            await postgres.execute(
                                """
                                UPDATE lore_documents
                                SET processing_status = 'failed',
                                    updated_at = NOW()
                                WHERE id = $1
                            """,
                                doc["id"],
                            )
                        except Exception:
                            pass  # Don't fail on failed status update

                        # Update progress to show failed
                        progress.update(
                            batch_task,
                            completed=i + 1,
                            doc_title=f"❌ {doc_title}",
                            episodes=str(total_episodes_created),
                        )
                        continue

                if max_documents and total_processed >= max_documents:
                    break

    except KeyboardInterrupt:
        console.print("\n⚠️ [yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n❌ [red]Episode creation failed[/red] ({type(e).__name__})")
    finally:
        # Cleanup
        try:
            await postgres.disconnect()
        except Exception as e:
            if debug:
                console.print(f"[dim]Warning: cleanup failed ({type(e).__name__})[/dim]")

    # Create beautiful summary table
    table = Table(title="📊 Episode Creation Summary", border_style="cyan")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="bold")
    table.add_column("Status", justify="center")

    table.add_row(
        "Documents processed", f"{total_processed:,}", "✅" if total_processed > 0 else "⚠️"
    )
    table.add_row(
        "Episodes created",
        f"{total_episodes_created:,}",
        "✅" if total_episodes_created > 0 else "⚠️",
    )
    table.add_row("Documents failed", f"{total_failed:,}", "❌" if total_failed > 0 else "✅")

    console.print()
    console.print(table)

    if total_failed == 0:
        console.print(
            f"\n🎉 [bold green]Success![/bold green] Created {total_episodes_created:,} episodes from {total_processed:,} documents"
        )
    else:
        console.print(f"\n⚠️ [yellow]Completed with {total_failed} failures[/yellow]")

    return total_failed == 0


async def check_episode_status():
    """Check current episode creation status"""
    console.print(
        Panel.fit("[bold cyan]📊 Episode Creation Status Check[/bold cyan]", border_style="cyan")
    )

    try:
        with console.status("[bold green]Querying database..."):
            postgres = await get_postgres_db()

            # Get processing statistics
            stats = await postgres.fetchrow("""
                SELECT
                    COUNT(*) as total_documents,
                    COUNT(*) FILTER (WHERE processing_status = 'completed') as completed_documents,
                    COUNT(*) FILTER (WHERE processing_status = 'pending' OR processing_status IS NULL) as pending_documents,
                    COUNT(*) FILTER (WHERE processing_status = 'failed') as failed_documents
                FROM lore_documents
                WHERE canonical IS TRUE
                  AND source_file LIKE 'canon/%'
            """)

            episode_stats = await postgres.fetchrow("""
                SELECT
                    COUNT(*) as total_episodes,
                    COUNT(DISTINCT episode.document_id) as documents_with_episodes,
                    AVG(length(episode.text)) as avg_episode_length
                FROM episodes AS episode
                JOIN lore_documents AS document ON document.id = episode.document_id
                WHERE document.canonical IS TRUE
                  AND document.source_file LIKE 'canon/%'
            """)

            await postgres.disconnect()

        # Create beautiful status tables
        doc_table = Table(title="📄 Document Processing Status", border_style="blue")
        doc_table.add_column("Status", style="cyan", no_wrap=True)
        doc_table.add_column("Count", justify="right", style="bold")
        doc_table.add_column("Percentage", justify="right")

        total_docs = stats["total_documents"]
        if total_docs > 0:
            doc_table.add_row("Total", f"{total_docs:,}", "100%")
            doc_table.add_row(
                "Completed",
                f"{stats['completed_documents']:,}",
                f"{stats['completed_documents'] / total_docs * 100:.1f}%",
            )
            doc_table.add_row(
                "Pending",
                f"{stats['pending_documents']:,}",
                f"{stats['pending_documents'] / total_docs * 100:.1f}%",
            )
            if stats["failed_documents"] > 0:
                doc_table.add_row(
                    "Failed",
                    f"{stats['failed_documents']:,}",
                    f"{stats['failed_documents'] / total_docs * 100:.1f}%",
                )
        else:
            doc_table.add_row("No documents found", "0", "0%")

        episode_table = Table(title="📚 Episode Statistics", border_style="green")
        episode_table.add_column("Metric", style="cyan", no_wrap=True)
        episode_table.add_column("Value", justify="right", style="bold")

        episode_table.add_row("Total episodes", f"{episode_stats['total_episodes']:,}")
        episode_table.add_row(
            "Documents with episodes", f"{episode_stats['documents_with_episodes']:,}"
        )
        if episode_stats["avg_episode_length"]:
            episode_table.add_row(
                "Average episode length", f"{int(episode_stats['avg_episode_length']):,} chars"
            )
        else:
            episode_table.add_row("Average episode length", "N/A")

        # Show completion rate
        if total_docs > 0:
            completion_rate = stats["completed_documents"] / total_docs * 100
            if completion_rate == 100:
                status_msg = "🎉 [bold green]All documents processed![/bold green]"
            elif completion_rate > 0:
                status_msg = f"🔄 [yellow]{completion_rate:.1f}% complete[/yellow]"
            else:
                status_msg = "⏳ [red]No documents processed yet[/red]"
        else:
            status_msg = "⚠️ [yellow]No documents found[/yellow]"

        console.print()
        console.print(doc_table)
        console.print()
        console.print(episode_table)
        console.print()
        console.print(status_msg)

    except Exception as e:
        console.print(f"❌ [red]Failed to check episode status[/red] ({type(e).__name__})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create episodes from documents in PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_episodes_from_documents.py --status
  python create_episodes_from_documents.py --base-tokens 300 --max-tokens 600
  python create_episodes_from_documents.py --similarity-threshold 0.8 --overlap-percentage 0.3
  python create_episodes_from_documents.py --force-recreate --debug
  python create_episodes_from_documents.py --max-documents 10
        """,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of documents to process per batch (default: 50)",
    )
    parser.add_argument(
        "--base-tokens", type=int, default=200, help="Base target tokens per chunk (default: 200)"
    )
    parser.add_argument(
        "--min-tokens", type=int, default=100, help="Minimum tokens per chunk (default: 100)"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=500, help="Maximum tokens per chunk (default: 500)"
    )
    parser.add_argument(
        "--overlap-percentage",
        type=float,
        default=0.25,
        help="Overlap percentage between chunks (default: 0.25 = 25%)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.7,
        help="Semantic similarity threshold for grouping (default: 0.7)",
    )
    parser.add_argument(
        "--complexity-factor",
        type=float,
        default=1.5,
        help="Maximum complexity multiplier for chunk sizing (default: 1.5)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--max-documents",
        type=int,
        help="Maximum number of documents to process (default: unlimited)",
    )
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="Recreate all episodes, even from completed documents",
    )
    parser.add_argument(
        "--status", action="store_true", help="Check episode creation status and exit"
    )

    args = parser.parse_args()

    if args.status:
        asyncio.run(check_episode_status())
    else:
        success = asyncio.run(
            create_episodes_from_documents(
                batch_size=args.batch_size,
                debug=args.debug,
                base_tokens=args.base_tokens,
                min_tokens=args.min_tokens,
                max_tokens=args.max_tokens,
                overlap_percentage=args.overlap_percentage,
                similarity_threshold=args.similarity_threshold,
                complexity_factor=args.complexity_factor,
                max_documents=args.max_documents,
                force_recreate=args.force_recreate,
            )
        )
        sys.exit(0 if success else 1)
