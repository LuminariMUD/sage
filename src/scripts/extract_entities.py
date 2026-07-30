#!/usr/bin/env python3
"""Extract entities from lore documents and store them in Neo4j using Graphiti."""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import tiktoken
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from src.db import get_postgres_db
from src.graphiti import LuminariGraphiti, initialize_graphiti

load_dotenv()

console = Console()


class GraphitiEntityProcessor:
    """Process entities using Graphiti for knowledge graph construction."""

    def __init__(self, verbose: bool = False):
        self.graphiti: LuminariGraphiti | None = None
        self.verbose = verbose
        self.processed_docs = 0
        self.total_episodes = 0
        self.failed_docs = 0
        # Initialize token encoder for proper chunking
        self.encoder = tiktoken.get_encoding("cl100k_base")

    async def initialize(self):
        """Initialize Graphiti connection."""
        console.print("[cyan]🚀 Initializing Graphiti knowledge graph...[/cyan]")
        self.graphiti = await initialize_graphiti(verbose=self.verbose)
        console.print("[green]✓ Graphiti initialized[/green]")

    async def update_document_status(self, doc_id: str, status: str, episodes_count: int = 0):
        """Update document processing status in PostgreSQL."""
        from src.db import get_postgres_db

        postgres_db = await get_postgres_db()

        if status == "completed":
            await postgres_db.execute(
                """
                UPDATE lore_documents
                SET graphiti_status = $1, graphiti_processed_at = NOW()
                WHERE id = $2
            """,
                status,
                doc_id,
            )
        elif status == "failed":
            await postgres_db.execute(
                """
                UPDATE lore_documents
                SET graphiti_status = $1
                WHERE id = $2
            """,
                status,
                doc_id,
            )

    def chunk_with_overlap(self, text: str, chunk_size: int = 450, overlap: int = 80) -> list[str]:
        """Create overlapping chunks of specified token size with semantic boundaries."""
        if not text or not text.strip():
            return []

        # Simple sliding window approach - more reliable
        tokens = self.encoder.encode(text)

        if len(tokens) <= chunk_size:
            return [text]  # Return original text if small enough

        chunks = []
        start = 0

        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]

            try:
                chunk_text = self.encoder.decode(chunk_tokens)
                chunks.append(chunk_text)
            except Exception as e:
                # If decode fails, skip this chunk
                console.print(
                    f"  [yellow]Warning: Failed to decode chunk at position {start} "
                    f"({type(e).__name__})[/yellow]"
                )

            # Move window forward, accounting for overlap
            if end == len(tokens):
                break  # We've processed everything
            start += chunk_size - overlap

        return chunks

    async def process_document(self, doc_row: dict) -> dict[str, int]:
        """Process a document by adding it as an episode to Graphiti."""
        doc_id = doc_row["id"]
        source_file = doc_row["source_file"]
        content = doc_row["body_md"]
        title = doc_row["title"]

        # Get token count for better processing decisions
        token_count = len(self.encoder.encode(content))
        if self.verbose:
            console.print(f"  [dim]Processing {len(content)} chars ({token_count} tokens)...[/dim]")

        # Use semantic chunking for documents > 400 tokens to ensure optimal LLM processing
        chunk_threshold = 400
        if token_count > chunk_threshold:
            # Use semantic chunking with overlap for better entity extraction
            chunk_size = min(450, token_count // 2 + 100)  # Adapt chunk size to document
            overlap = max(60, int(chunk_size * 0.15))  # 15% overlap minimum

            chunks = self.chunk_with_overlap(content, chunk_size=chunk_size, overlap=overlap)

            if self.verbose:
                console.print(
                    f"  [dim]Document split into {len(chunks)} overlapping chunks "
                    f"(~{chunk_size} tokens each, {overlap} token overlap)[/dim]"
                )

            # Process each chunk as separate episode
            episodes_created = 0
            for i, chunk in enumerate(chunks):
                try:
                    import asyncio

                    chunk_tokens = len(self.encoder.encode(chunk))

                    await asyncio.wait_for(
                        self.graphiti.add_episode_with_lore_relationships(
                            content=chunk,
                            source_file=f"{source_file}_chunk_{i + 1}",
                            metadata={
                                "title": f"{title} (Part {i + 1}/{len(chunks)})",
                                "document_type": (doc_row["document_type"] or "lore"),
                                "chunk_index": i,
                                "total_chunks": len(chunks),
                                "chunk_tokens": chunk_tokens,
                                "has_overlap_previous": i > 0,
                                "has_overlap_next": i < len(chunks) - 1,
                                "semantic_chunking": True,
                            },
                        ),
                        timeout=120.0,  # Longer timeout for rich relationship extraction
                    )
                    episodes_created += 1
                except Exception as e:
                    if self.verbose:
                        console.print(
                            f"  [yellow]Warning: Failed chunk {i + 1} ({type(e).__name__})[/yellow]"
                        )
                    else:
                        console.print(f"  [yellow]⚠[/yellow] Chunk {i + 1} failed: {title}")

            if episodes_created > 0:
                if self.verbose:
                    avg_tokens = sum(len(self.encoder.encode(chunk)) for chunk in chunks) // len(
                        chunks
                    )
                    console.print(
                        f"  [green]✓[/green] Added {episodes_created}/{len(chunks)} semantic chunks "
                        f"(avg {avg_tokens} tokens with overlap): {title}"
                    )
                else:
                    console.print(
                        f"  [green]✓[/green] Processed {title} ({episodes_created} episodes)"
                    )

                # Update status to completed
                await self.update_document_status(doc_id, "completed", episodes_created)

                self.processed_docs += 1
                return {"episodes": episodes_created}
            else:
                console.print(f"  [red]✗[/red] All chunks failed for: {title}")

                # Update status to failed
                await self.update_document_status(doc_id, "failed")

                return {"failed": 1}
        else:
            # Process smaller documents normally
            try:
                import asyncio

                await asyncio.wait_for(
                    self.graphiti.add_episode_with_lore_relationships(
                        content=content,
                        source_file=source_file,
                        metadata={
                            "title": title,
                            "document_type": (doc_row["document_type"] or "lore"),
                        },
                    ),
                    timeout=150.0,  # Longer timeout for rich relationship extraction
                )
                if self.verbose:
                    console.print(
                        f"  [green]✓[/green] Added single episode ({token_count} tokens): {title}"
                    )
                else:
                    console.print(f"  [green]✓[/green] Processed {title}")

                # Update status to completed
                await self.update_document_status(doc_id, "completed", 1)

                self.processed_docs += 1
                return {"episodes": 1}

            except TimeoutError:
                console.print(f"  [red]✗[/red] Timeout processing: {title}")

                # Update status to failed
                await self.update_document_status(doc_id, "failed")

                return {"failed": 1}

            except Exception as e:
                console.print(f"  [red]✗[/red] Failed to add episode ({type(e).__name__})")

                # Update status to failed
                await self.update_document_status(doc_id, "failed")

                return {"failed": 1}

    async def extract_episode_with_retry(self, episode_row: dict, max_retries: int = 3) -> bool:
        """Extract entities from episode with retry logic.

        Args:
            episode_row: Episode data dictionary
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            True on success, False on failure after all retries
        """
        source_file = episode_row["source_file"]
        episode_index = episode_row["episode_index"]

        for attempt in range(max_retries):
            try:
                # Process the episode
                await self._process_episode_internal(episode_row)
                return True  # Success

            except TimeoutError:
                console.print(
                    f"  ⚠️  Attempt {attempt + 1}/{max_retries} timed out: {source_file} ep{episode_index}"
                )
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    console.print(f"  ⏳ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    console.print(f"  ❌ Failed after {max_retries} attempts (timeout)")
                    return False

            except Exception as e:
                console.print(
                    f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed ({type(e).__name__})"
                )
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    console.print(f"  ⏳ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    console.print(f"  ❌ Failed after {max_retries} attempts")
                    return False

        return False  # Should not reach here, but return False as fallback

    async def _process_episode_internal(self, episode_row: dict):
        """Internal episode processing logic (called by retry wrapper).

        Args:
            episode_row: Episode data dictionary

        Raises:
            Exception: On processing failure
        """
        episode_id = episode_row["episode_id"]
        episode_text = episode_row["episode_text"]
        source_file = episode_row["source_file"]
        episode_index = episode_row["episode_index"]

        # Create episode name with source context

        # Check if this is a temporal metadata episode
        episode_db_metadata = episode_row["metadata"] or {}
        is_temporal = (
            episode_db_metadata.get("is_temporal_metadata", False)
            if isinstance(episode_db_metadata, dict)
            else False
        )

        # Create metadata including the PostgreSQL episode UUID for linkage
        episode_metadata = {
            "episode_id": str(episode_id),  # PostgreSQL UUID for hybrid RAG linkage
            "source_file": source_file,
            "episode_index": episode_index,
            "title": episode_row["title"] or "",
            "document_type": (episode_row["document_type"] or "lore"),
            "canonical": episode_row["canonical"] or False,
        }

        # Add temporal metadata if present
        if is_temporal:
            episode_metadata.update(
                {
                    "is_temporal_metadata": True,
                    "temporal_order": episode_db_metadata.get("temporal_order"),
                    "temporal_type": episode_db_metadata.get("temporal_type"),
                    "eras": episode_db_metadata.get("eras", []),
                    "no_split": True,  # Tell Graphiti not to split this further
                }
            )
            console.print(
                f"  [cyan]🕐 Processing temporal metadata episode from {source_file}[/cyan]"
            )

        if self.verbose:
            console.print(
                f"  [dim]Processing episode {episode_index} from {source_file} ({len(episode_text)} chars)[/dim]"
            )

        # Add episode to Graphiti with UUID metadata for linkage
        # Temporal episodes should be processed as single units
        if is_temporal:
            # Process temporal episode without splitting - use base Graphiti add_episode
            from graphiti_core.nodes import EpisodeType

            await self.graphiti.graphiti.add_episode(
                name=f"episode_{episode_id}",
                episode_body=episode_text,
                source_description=f"temporal_metadata_{episode_id}",
                reference_time=datetime.now(UTC),
                source=EpisodeType.message,  # Use standard type
            )
        else:
            # Regular episode processing with relationship extraction
            await self.graphiti.add_episode_with_lore_relationships(
                content=episode_text,
                source_file=f"episode_{episode_id}",  # Unique identifier
                timestamp=datetime.now(UTC),
                metadata=episode_metadata,  # Include episode UUID for hybrid RAG
            )

        # Mark episode as synced in PostgreSQL
        await self.update_episode_status(episode_id, True)

        console.print(f"  [green]✓[/green] Processed episode {episode_index}: {source_file}")

    async def process_episode(self, episode_row: dict) -> dict[str, int]:
        """Process a single episode for entity extraction with retry logic.

        Args:
            episode_row: Episode data dictionary

        Returns:
            Dictionary with processing statistics
        """
        success = await self.extract_episode_with_retry(episode_row, max_retries=3)

        if success:
            return {"processed": 1}
        else:
            # Mark episode as failed (keep graphiti_synced = false)
            episode_id = episode_row["episode_id"]
            await self.update_episode_status(episode_id, False)
            return {"failed": 1}

    async def update_episode_status(self, episode_id: str, synced: bool):
        """Update episode sync status in PostgreSQL."""
        from src.db import get_postgres_db

        postgres_db = await get_postgres_db()

        if synced:
            await postgres_db.execute(
                """
                UPDATE episodes
                SET graphiti_synced = true, graphiti_synced_at = NOW()
                WHERE id = $1
            """,
                episode_id,
            )
        # If failed, we don't update - leaves graphiti_synced = false for retry

    async def process_all_episodes(self) -> dict[str, int]:
        """Process all episodes from PostgreSQL (not documents directly)."""
        postgres_db = await get_postgres_db()

        # Get episodes that need processing - this ensures hybrid RAG linkage
        episodes = await postgres_db.fetch("""
            SELECT
                e.id as episode_id,
                e.text as episode_text,
                e.episode_index,
                e.metadata,
                d.source_file,
                d.title,
                d.document_type,
                d.canonical
            FROM episodes e
            JOIN lore_documents d ON e.document_id = d.id
            WHERE e.graphiti_synced = false
              AND length(e.text) > 50
            ORDER BY d.source_file, e.episode_index
        """)

        if len(episodes) == 0:
            console.print(
                "\n[green]✓ All episodes are up-to-date! No pending processing needed.[/green]"
            )
            return {"documents": 0, "episodes": 0, "failed": 0}

        console.print(
            f"\n[cyan]Found {len(episodes)} episodes to process for entity extraction[/cyan]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Processing episodes...", total=len(episodes))

            for episode in episodes:
                # Update task description
                file_name = Path(episode["source_file"]).name
                progress.update(
                    task, description=f"Processing {file_name} ({episode['episode_index']})..."
                )

                # Process episode for entity extraction
                stats = await self.process_episode(episode)

                # Track results
                if "processed" in stats:
                    self.processed_docs += stats["processed"]
                if "failed" in stats:
                    self.failed_docs += stats["failed"]

                progress.advance(task)

        return {
            "episodes_processed": self.processed_docs,
            "failed": self.failed_docs,
            "total": len(episodes),
        }

    async def create_special_relationships(self):
        """Create special relationships based on domain knowledge."""
        console.print("\n[cyan]Creating special relationships...[/cyan]")

        # Knight Orders to Deities relationships
        knight_deity_mappings = [
            ("Knights of Solamnia", "Paladine", "PATRON_DEITY"),
            ("Knights of Takhisis", "Takhisis", "PATRON_DEITY"),
            ("Knights of the Sword", "Kiri-Jolith", "PATRON_DEITY"),
            ("Knights of the Crown", "Habbakuk", "PATRON_DEITY"),
            ("Knights of the Rose", "Paladine", "PATRON_DEITY"),
        ]

        for knight_order, deity, rel_type in knight_deity_mappings:
            try:
                await self.graphiti.add_relationship(
                    source_name=knight_order,
                    target_name=deity,
                    relationship_type=rel_type,
                    properties={"canonical": True},
                )
                if self.verbose:
                    console.print(f"  [green]✓[/green] {knight_order} -> {deity}")
            except Exception as e:
                if self.verbose:
                    console.print(
                        f"  [yellow]⚠[/yellow] Failed: {knight_order} -> {deity} "
                        f"({type(e).__name__})"
                    )

    async def cleanup(self):
        """Clean up connections."""
        if self.graphiti:
            await self.graphiti.close()


async def main():
    """Main entry point for entity extraction."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract entities from lore documents using Graphiti"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output including debug information",
    )

    args = parser.parse_args()

    console.print("[bold cyan]Luminari Sage Entity Extraction with Graphiti[/bold cyan]")
    console.print("=" * 60)

    processor = GraphitiEntityProcessor(verbose=args.verbose)

    try:
        # Initialize
        await processor.initialize()

        # Process all episodes (not documents directly - this ensures hybrid RAG linkage)
        stats = await processor.process_all_episodes()

        # Create special relationships
        await processor.create_special_relationships()

        # Print summary
        table = Table(title="Episode Processing Summary", show_header=True)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Count", justify="right", style="green")

        table.add_row("Episodes Processed", str(stats.get("episodes_processed", 0)))
        table.add_row("Failed Episodes", str(stats.get("failed", 0)))
        table.add_row("Total Episodes", str(stats.get("total", 0)))

        console.print("\n")
        console.print(table)
        console.print("\n[green]✓ Episode processing completed successfully![/green]")

    except Exception as e:
        console.print(f"\n[red]Fatal error type: {type(e).__name__}[/red]")
        sys.exit(1)

    finally:
        await processor.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
