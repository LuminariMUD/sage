#!/usr/bin/env python3
"""Load markdown documents from the lore directory into PostgreSQL."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import ulid
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.db import get_postgres_db

load_dotenv()

console = Console()

# Document type mapping based on new directory structure
DOCUMENT_TYPE_MAP = {
    "world": "worldbuilding",
    "cultures": "culture",
    "factions": "faction",
    "characters": "character",
    "timeline": "chronicle",
    "locations": "location",
    "uncategorized": "misc",
}

# Default document type for unmapped directories
DEFAULT_DOCUMENT_TYPE = "lore"


class DocumentLoader:
    """Load and process markdown documents for the lore database."""

    def __init__(
        self, lore_dir: str, source: str = "canon", verbose: bool = False, resume: bool = False
    ):
        self.lore_dir = Path(lore_dir)
        self.source = source  # "canon", "draft", or "all"
        self.verbose = verbose
        self.resume = resume
        self.loaded_count = 0
        self.skipped_count = 0
        self.error_count = 0
        self.updated_count = 0

    def generate_stable_id(self, content: str) -> str:
        """Generate a stable ID for a document based on content hash."""
        # Use first 8 chars of content hash + ULID for uniqueness
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"{content_hash}_{ulid.new().str}"

    def calculate_content_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content for change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def extract_summary(self, content: str, max_length: int = 500) -> str:
        """Extract a summary from the document content."""
        lines = content.split("\n")
        summary_lines = []
        char_count = 0

        for line in lines:
            # Skip headers and empty lines
            if line.startswith("#") or not line.strip():
                continue

            # Add line to summary
            summary_lines.append(line.strip())
            char_count += len(line)

            if char_count >= max_length:
                break

        summary = " ".join(summary_lines)[:max_length]
        if len(summary) == max_length:
            summary = summary.rsplit(" ", 1)[0] + "..."

        return summary

    def get_document_type(self, file_path: Path) -> str:
        """Determine document type based on file path."""
        # Get relative path from lore_dir
        try:
            rel_path = file_path.relative_to(self.lore_dir)
            parts = rel_path.parts

            # Skip 'canon' or 'drafts' prefix and check category directory
            if len(parts) > 1 and parts[0] in ["canon", "drafts"]:
                category_dir = parts[1]
                if category_dir in DOCUMENT_TYPE_MAP:
                    return DOCUMENT_TYPE_MAP[category_dir]

            # Fallback: check immediate parent directory
            parent_dir = file_path.parent.name
            if parent_dir in DOCUMENT_TYPE_MAP:
                return DOCUMENT_TYPE_MAP[parent_dir]

        except ValueError:
            pass

        return DEFAULT_DOCUMENT_TYPE

    def find_markdown_files(self) -> list[Path]:
        """Find all markdown files - no filtering needed since canon/ and drafts/ contain only lore."""
        md_files = []

        # Determine which directories to scan
        if self.source == "canon":
            scan_dirs = [self.lore_dir / "canon"]
        elif self.source == "draft":
            scan_dirs = [self.lore_dir / "drafts"]
        elif self.source == "all":
            scan_dirs = [self.lore_dir / "canon", self.lore_dir / "drafts"]
        else:
            raise ValueError(f"Invalid source: {self.source}. Must be 'canon', 'draft', or 'all'")

        # Get ALL .md files - they're all valid lore content
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                if self.verbose:
                    console.print(f"[yellow]Warning: Directory {scan_dir} does not exist[/yellow]")
                continue

            # No filtering needed - trust the directory structure
            md_files.extend(scan_dir.rglob("*.md"))

        # Sort by modification time (most recently modified first) for better progress visibility
        md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        if self.verbose:
            console.print(
                f"[dim]Found {len(md_files)} markdown files in {[str(d) for d in scan_dirs]}[/dim]"
            )

        return md_files

    async def load_document(self, file_path: Path, db) -> bool:
        """Load a single document into the database."""
        try:
            # Read file content
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Get relative path for source_file
            rel_path = file_path.relative_to(self.lore_dir)

            # Extract title from first header or filename
            title = file_path.stem.replace("_", " ").title()
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            # Generate stable ID
            stable_id = self.generate_stable_id(content)

            # Extract summary
            summary = self.extract_summary(content)

            # Calculate content hash for change detection
            content_hash = self.calculate_content_hash(content)

            # Determine document type
            doc_type = self.get_document_type(file_path)

            # Check if document is canonical (in canon directory)
            canonical = str(rel_path).startswith("canon/")

            # Add source information to metadata
            if str(rel_path).startswith("canon/"):
                doc_source = "canon"
            elif str(rel_path).startswith("drafts/"):
                doc_source = "draft"
            else:
                doc_source = "unknown"

            # Prepare metadata
            file_stat = file_path.stat()
            metadata = {
                "file_size": file_stat.st_size,
                "file_modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                "line_count": content.count("\n"),
                "word_count": len(content.split()),
                "has_headers": "# " in content,
                "loaded_at": datetime.utcnow().isoformat(),
                "source": doc_source,
            }

            # Check if document already exists and if content has changed
            existing = await db.fetchrow(
                "SELECT id, graphiti_content_hash FROM lore_documents WHERE source_file = $1",
                str(rel_path),
            )

            if existing:
                # Check if content has changed
                existing_hash = existing["graphiti_content_hash"]
                content_changed = existing_hash != content_hash

                if content_changed:
                    # Content changed - update and reset Graphiti status
                    await db.execute(
                        """
                        UPDATE lore_documents
                        SET body_md = $1, summary = $2, canonical = $3,
                            metadata = $4, updated_at = NOW(),
                            graphiti_content_hash = $5, graphiti_status = 'pending',
                            graphiti_processed_at = NULL
                        WHERE source_file = $6
                    """,
                        content,
                        summary,
                        canonical,
                        json.dumps(metadata),
                        content_hash,
                        str(rel_path),
                    )

                    console.print(f"  [yellow]↻ Content changed[/yellow] Updated: {rel_path}")
                    self.updated_count += 1
                else:
                    # Content unchanged - just update metadata
                    await db.execute(
                        """
                        UPDATE lore_documents
                        SET canonical = $1, metadata = $2, updated_at = NOW()
                        WHERE source_file = $3
                    """,
                        canonical,
                        json.dumps(metadata),
                        str(rel_path),
                    )

                    if self.verbose:
                        console.print(f"  [dim]↻ No changes[/dim] Refreshed: {rel_path}")
                    self.skipped_count += 1
            else:
                # Insert new document
                await db.execute(
                    """
                    INSERT INTO lore_documents
                    (stable_id, title, document_type, source_file, body_md,
                     summary, canonical, metadata, graphiti_content_hash, graphiti_status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
                """,
                    stable_id,
                    title,
                    doc_type,
                    str(rel_path),
                    content,
                    summary,
                    canonical,
                    json.dumps(metadata),
                    content_hash,
                )

                console.print(f"  [green]✓[/green] Loaded: {rel_path}")
                self.loaded_count += 1

            return True

        except Exception as e:
            console.print(f"  [red]✗[/red] Error loading {file_path} ({type(e).__name__})")
            self.error_count += 1
            return False

    async def load_all_documents(self) -> dict[str, int]:
        """Load all markdown documents into the database."""
        db = await get_postgres_db()

        # Find all markdown files
        md_files = self.find_markdown_files()
        console.print(f"\n[cyan]Found {len(md_files)} markdown files to process[/cyan]")

        # Process files with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading documents...", total=len(md_files))

            for md_file in md_files:
                await self.load_document(md_file, db)
                progress.advance(task)

        # Print summary table
        table = Table(title="Document Loading Summary")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")

        table.add_row("Loaded (New)", str(self.loaded_count))
        table.add_row("Updated (Changed)", str(self.updated_count))
        table.add_row("Skipped (Unchanged)", str(self.skipped_count))
        table.add_row("Errors", str(self.error_count))
        table.add_row("Total Processed", str(len(md_files)))

        console.print("\n")
        console.print(table)

        return {
            "loaded": self.loaded_count,
            "updated": self.updated_count,
            "skipped": self.skipped_count,
            "errors": self.error_count,
            "total": len(md_files),
        }


async def main():
    """Main entry point for document loading."""
    parser = argparse.ArgumentParser(description="Load markdown documents into PostgreSQL")
    parser.add_argument(
        "--source",
        choices=["canon", "draft", "all"],
        default=os.getenv("LORE_SOURCE", "canon"),
        help="Source to load from: canon (default), draft, or all",
    )
    parser.add_argument(
        "--lore-dir",
        default=os.getenv("LORE_DIR", "/home/luminari/lore"),
        help="Lore directory path",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output including unchanged files",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume mode - only process new or changed documents"
    )

    args = parser.parse_args()

    console.print("[bold cyan]Luminari Sage Document Loader[/bold cyan]")
    console.print("=" * 50)
    console.print(f"[cyan]Source: {args.source}[/cyan]")
    console.print(f"[cyan]Lore Dir: {args.lore_dir}[/cyan]")
    console.print()

    if not Path(args.lore_dir).exists():
        console.print(f"[red]Error: Lore directory not found: {args.lore_dir}[/red]")
        sys.exit(1)

    # Create loader and process documents
    loader = DocumentLoader(args.lore_dir, args.source, verbose=args.verbose, resume=args.resume)

    try:
        results = await loader.load_all_documents()

        if results["errors"] > 0:
            console.print(
                f"\n[yellow]Warning: {results['errors']} documents failed to load[/yellow]"
            )
            sys.exit(1)
        else:
            console.print("\n[green]✓ All documents loaded successfully![/green]")

    except Exception as e:
        console.print(f"\n[red]Fatal error type: {type(e).__name__}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
