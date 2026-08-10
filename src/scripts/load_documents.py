#!/usr/bin/env python3
"""Load markdown documents from the lore directory into PostgreSQL."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
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
    # Keep these values aligned with the PostgreSQL ``document_type`` enum.
    "world": "world",
    "cultures": "culture",
    "factions": "faction",
    "characters": "character",
    "timeline": "chronicle",
    "locations": "location",
    "uncategorized": "misc",
}

# Default document type for unmapped directories
DEFAULT_DOCUMENT_TYPE = "lore"

REQUIRED_LORE_DOCUMENT_COLUMNS = frozenset(
    {
        "id",
        "stable_id",
        "title",
        "document_type",
        "source_file",
        "body_md",
        "summary",
        "canonical",
        "metadata",
        "graphiti_content_hash",
        "graphiti_status",
        "processing_status",
        "processed_at",
        "updated_at",
    }
)
REQUIRED_LORE_DOCUMENT_COLUMN_TYPES = {
    "id": frozenset({"uuid"}),
    "stable_id": frozenset({"text", "varchar"}),
    "title": frozenset({"text", "varchar"}),
    "document_type": frozenset({"document_type"}),
    "source_file": frozenset({"text", "varchar"}),
    "body_md": frozenset({"text", "varchar"}),
    "summary": frozenset({"text", "varchar"}),
    "canonical": frozenset({"bool"}),
    "metadata": frozenset({"jsonb"}),
    "graphiti_content_hash": frozenset({"text", "varchar"}),
    "graphiti_status": frozenset({"text", "varchar"}),
    "processing_status": frozenset({"text", "varchar"}),
    "processed_at": frozenset({"timestamptz"}),
    "updated_at": frozenset({"timestamptz"}),
}


class DocumentLoader:
    """Load canon Markdown documents into the lore database."""

    def __init__(
        self, lore_dir: str, source: str = "canon", verbose: bool = False, resume: bool = False
    ):
        self.lore_dir = Path(lore_dir)
        if source != "canon":
            raise ValueError("The production lore corpus is restricted to lore_docs/canon")
        self.source = "canon"
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

            # Skip the canon prefix and check the category directory.
            if len(parts) > 1 and parts[0] == "canon":
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
        """Find Markdown files whose resolved paths remain inside ``canon``."""
        canon_dir = self.lore_dir / "canon"
        if not canon_dir.is_dir():
            raise FileNotFoundError(f"Canon lore directory does not exist: {canon_dir}")

        md_files = list(canon_dir.rglob("*.md"))
        for file_path in md_files:
            self.canon_relative_path(file_path)

        # Sort by modification time (most recently modified first) for better progress visibility
        md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        if self.verbose:
            console.print(f"[dim]Found {len(md_files)} markdown files in {canon_dir}[/dim]")

        return md_files

    async def preflight(self, db, markdown_files: list[Path]) -> dict[str, object]:
        """Validate inferred types and the complete write shape before mutation."""
        inferred_types = {self.get_document_type(path) for path in markdown_files}
        enum_rows = await db.fetch(
            """
            SELECT enum_value.enumlabel
            FROM pg_attribute AS attribute
            JOIN pg_class AS relation
              ON relation.oid = attribute.attrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            JOIN pg_type AS enum_type
              ON enum_type.oid = attribute.atttypid
            JOIN pg_enum AS enum_value
              ON enum_value.enumtypid = enum_type.oid
            WHERE relation.relname = 'lore_documents'
              AND namespace.nspname = current_schema()
              AND attribute.attname = 'document_type'
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            ORDER BY enum_value.enumsortorder
            """
        )
        deployed_types = {str(row["enumlabel"]) for row in enum_rows}
        if not deployed_types:
            raise RuntimeError("Document loader preflight could not inspect document_type")
        unsupported_types = sorted(inferred_types - deployed_types)
        if unsupported_types:
            raise RuntimeError("Document loader inferred a type absent from the deployed enum")

        column_rows = await db.fetch(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'lore_documents'
            ORDER BY ordinal_position
            """
        )
        deployed_columns = {str(row["column_name"]) for row in column_rows}
        missing_columns = sorted(REQUIRED_LORE_DOCUMENT_COLUMNS - deployed_columns)
        if missing_columns:
            raise RuntimeError("Document loader write columns are absent from the deployed schema")
        incompatible_columns = sorted(
            str(row["column_name"])
            for row in column_rows
            if str(row["column_name"]) in REQUIRED_LORE_DOCUMENT_COLUMN_TYPES
            and str(row["udt_name"])
            not in REQUIRED_LORE_DOCUMENT_COLUMN_TYPES[str(row["column_name"])]
        )
        if incompatible_columns:
            raise RuntimeError("Document loader write columns have incompatible deployed types")
        return {
            "files": len(markdown_files),
            "inferred_types": sorted(inferred_types),
            "deployed_types": sorted(deployed_types),
            "required_columns": len(REQUIRED_LORE_DOCUMENT_COLUMNS),
        }

    def canon_relative_path(self, file_path: Path) -> Path:
        """Return a canonical source path or reject path/symlink escape attempts."""
        canon_dir = (self.lore_dir / "canon").resolve(strict=True)
        resolved_file = file_path.resolve(strict=True)
        if resolved_file.suffix.lower() != ".md":
            raise ValueError("Only Markdown files from lore_docs/canon may be loaded")
        try:
            relative_to_canon = resolved_file.relative_to(canon_dir)
        except ValueError as error:
            raise ValueError("Lore document resolved outside lore_docs/canon") from error
        return Path("canon") / relative_to_canon

    async def load_document(self, file_path: Path, db) -> bool:
        """Load a single document into the database."""
        try:
            # Read file content
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Resolve first so a symlink inside canon cannot import outside content.
            rel_path = self.canon_relative_path(file_path)

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

            canonical = True
            doc_source = "canon"

            # Prepare metadata
            file_stat = file_path.stat()
            metadata = {
                "file_size": file_stat.st_size,
                "file_modified_at": datetime.fromtimestamp(file_stat.st_mtime, UTC).isoformat(),
                "line_count": content.count("\n"),
                "word_count": len(content.split()),
                "has_headers": "# " in content,
                "loaded_at": datetime.now(UTC).isoformat(),
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
                    # Content changed - refresh all derived document metadata and
                    # make the document eligible for episode regeneration. Graph
                    # synchronization is driven by the episode lifecycle, so the
                    # document-level status is only a compatibility projection.
                    await db.execute(
                        """
                        UPDATE lore_documents
                        SET title = $1, document_type = $2, body_md = $3,
                            summary = $4, canonical = $5, metadata = $6,
                            updated_at = NOW(), graphiti_content_hash = $7,
                            graphiti_status = 'pending',
                            processing_status = 'pending', processed_at = NULL
                        WHERE source_file = $8
                    """,
                        title,
                        doc_type,
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
        preflight = await self.preflight(db, md_files)
        console.print(f"\n[cyan]Found {len(md_files)} markdown files to process[/cyan]")
        if self.verbose:
            console.print(
                "[dim]Preflight passed: "
                f"types={','.join(preflight['inferred_types'])}, "
                f"columns={preflight['required_columns']}[/dim]"
            )

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
        choices=["canon"],
        default="canon",
        help="Corpus source (fixed to canon)",
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
