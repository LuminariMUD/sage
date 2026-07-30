#!/usr/bin/env python3
"""Generate chunks from documents and create embeddings."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import tiktoken
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table
from sentence_transformers import SentenceTransformer

from src.db import get_postgres_db

# Import semantic chunker
try:
    from semantic_chunker import SemanticChunker
except ImportError:
    # Try to import from scripts directory
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from semantic_chunker import SemanticChunker

load_dotenv()

console = Console()


class ChunkGenerator:
    """Generate chunks from documents with embeddings using semantic chunking."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        base_tokens: int = 200,
        min_tokens: int = 100,
        max_tokens: int = 500,
        overlap_percentage: float = 0.25,
        similarity_threshold: float = 0.7,
        complexity_factor: float = 1.5,
        use_semantic_chunking: bool = True,
    ):
        self.model = SentenceTransformer(
            model_name,
            revision=os.getenv("SAGE_SENTENCE_TRANSFORMERS_REVISION"),
        )
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.use_semantic_chunking = use_semantic_chunking

        # Legacy parameters for backward compatibility
        self.target_tokens = base_tokens
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = int(base_tokens * overlap_percentage)

        # Semantic chunking parameters
        if use_semantic_chunking:
            self.semantic_chunker = SemanticChunker(
                embedding_model=model_name,
                base_tokens=base_tokens,
                min_tokens=min_tokens,
                max_tokens=max_tokens,
                overlap_percentage=overlap_percentage,
                similarity_threshold=similarity_threshold,
                complexity_factor=complexity_factor,
            )

        self.chunks_created = 0
        self.embeddings_created = 0

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))

    def split_by_headers(self, content: str) -> list[tuple[str, str]]:
        """Split content by markdown headers, preserving hierarchy."""
        sections = []
        current_section = []
        current_header = ""

        lines = content.split("\n")

        for line in lines:
            # Check if line is a header
            if re.match(r"^#{1,6}\s+", line):
                # Save previous section if exists
                if current_section:
                    sections.append((current_header, "\n".join(current_section)))

                # Start new section
                current_header = line
                current_section = [line]
            else:
                current_section.append(line)

        # Don't forget the last section
        if current_section:
            sections.append((current_header, "\n".join(current_section)))

        return sections

    def split_text_into_chunks(self, text: str, header: str = "") -> list[str]:
        """Split text into chunks using semantic chunking or legacy method."""

        if self.use_semantic_chunking and hasattr(self, "semantic_chunker"):
            # Use semantic chunking
            semantic_chunks = self.semantic_chunker.create_semantic_chunks(text, header)
            return [chunk["text"] for chunk in semantic_chunks]

        else:
            # Legacy method (kept for backward compatibility)
            chunks = []

            # If text is short enough, return as single chunk
            token_count = self.count_tokens(text)
            if token_count <= self.max_tokens:
                return [text]

            # Split by paragraphs first
            paragraphs = text.split("\n\n")
            current_chunk = header + "\n\n" if header else ""
            current_tokens = self.count_tokens(current_chunk)

            for para in paragraphs:
                para_tokens = self.count_tokens(para)

                # If paragraph itself is too large, split by sentences
                if para_tokens > self.max_tokens:
                    sentences = re.split(r"(?<=[.!?])\s+", para)

                    for sentence in sentences:
                        sentence_tokens = self.count_tokens(sentence)

                        if current_tokens + sentence_tokens <= self.max_tokens:
                            current_chunk += sentence + " "
                            current_tokens += sentence_tokens
                        else:
                            # Save current chunk if it meets minimum
                            if current_tokens >= self.min_tokens:
                                chunks.append(current_chunk.strip())

                            # Start new chunk with overlap
                            overlap_text = (
                                current_chunk[-self.overlap_tokens :]
                                if len(current_chunk) > self.overlap_tokens
                                else ""
                            )
                            current_chunk = overlap_text + sentence + " "
                            current_tokens = self.count_tokens(current_chunk)

                # Normal paragraph processing
                elif current_tokens + para_tokens <= self.max_tokens:
                    current_chunk += para + "\n\n"
                    current_tokens += para_tokens
                else:
                    # Save current chunk
                    if current_tokens >= self.min_tokens:
                        chunks.append(current_chunk.strip())

                    # Start new chunk with overlap
                    overlap_text = (
                        current_chunk[-self.overlap_tokens :]
                        if len(current_chunk) > self.overlap_tokens
                        else ""
                    )
                    current_chunk = overlap_text + para + "\n\n"
                    current_tokens = self.count_tokens(current_chunk)

            # Don't forget the last chunk
            if current_chunk.strip() and current_tokens >= self.min_tokens:
                chunks.append(current_chunk.strip())

            return chunks

    def extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text using simple heuristics."""
        keywords = []

        # Extract capitalized words (potential entities)
        capitalized = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        keywords.extend(list(set(capitalized))[:10])

        # Extract words in quotes
        quoted = re.findall(r'"([^"]+)"', text)
        keywords.extend(list(set(quoted))[:5])

        # Extract words after "the"
        the_phrases = re.findall(r"\bthe\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text)
        keywords.extend(list(set(the_phrases))[:5])

        return list(set(keywords))[:20]  # Limit to 20 keywords

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text using sentence-transformers."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    async def process_document(self, doc_row, db) -> int:
        """Process a single document into chunks with embeddings."""
        chunks_created = 0

        try:
            doc_id = doc_row["id"]
            content = doc_row["body_md"]
            canonical = doc_row["canonical"]

            # Split by headers first
            sections = self.split_by_headers(content)

            chunk_index = 0
            all_chunks = []

            for header, section_text in sections:
                # Split section into chunks
                chunks = self.split_text_into_chunks(section_text, header)

                for chunk_text in chunks:
                    # Extract keywords
                    keywords = self.extract_keywords(chunk_text)

                    # Generate embedding
                    embedding = self.generate_embedding(chunk_text)

                    # Prepare chunk data
                    chunk_data = {
                        "document_id": doc_id,
                        "chunk_index": chunk_index,
                        "text": chunk_text,
                        "token_count": self.count_tokens(chunk_text),
                        "embedding": embedding,
                        "keywords": keywords,
                        "canonical": canonical,
                        "metadata": {
                            "header": header,
                            "section_index": sections.index((header, section_text)),
                        },
                    }

                    all_chunks.append(chunk_data)
                    chunk_index += 1

            # Batch insert chunks
            if all_chunks:
                for chunk in all_chunks:
                    await db.execute(
                        """
                        INSERT INTO chunks
                        (document_id, chunk_index, text, token_count,
                         embedding, keywords, canonical, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (document_id, chunk_index)
                        DO UPDATE SET
                            text = EXCLUDED.text,
                            token_count = EXCLUDED.token_count,
                            embedding = EXCLUDED.embedding,
                            keywords = EXCLUDED.keywords,
                            metadata = EXCLUDED.metadata
                    """,
                        chunk["document_id"],
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["token_count"],
                        chunk["embedding"],
                        chunk["keywords"],
                        chunk["canonical"],
                        json.dumps(chunk["metadata"]),
                    )
                    chunks_created += 1

                self.chunks_created += chunks_created
                self.embeddings_created += chunks_created

                console.print(
                    f"  [green]✓[/green] Created {chunks_created} chunks for: {doc_row['title']}"
                )

        except Exception as e:
            console.print(
                f"  [red]✗[/red] Error processing {doc_row['title']} ({type(e).__name__})"
            )

        return chunks_created

    async def generate_all_chunks(self) -> dict[str, int]:
        """Generate chunks for all documents."""
        db = await get_postgres_db()

        # Get all documents, prioritizing canonical ones
        docs = await db.fetch("""
            SELECT id, title, body_md, canonical
            FROM lore_documents
            ORDER BY canonical DESC, title
        """)

        console.print(f"\n[cyan]Processing {len(docs)} documents[/cyan]")

        total_chunks = 0

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Generating chunks...", total=len(docs))

            for doc in docs:
                chunks = await self.process_document(doc, db)
                total_chunks += chunks
                progress.advance(task)

        # Print summary
        table = Table(title="Chunk Generation Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")

        table.add_row("Documents Processed", str(len(docs)))
        table.add_row("Chunks Created", str(self.chunks_created))
        table.add_row("Embeddings Generated", str(self.embeddings_created))

        console.print("\n")
        console.print(table)

        return {
            "documents": len(docs),
            "chunks": self.chunks_created,
            "embeddings": self.embeddings_created,
        }


async def main():
    """Main entry point for chunk generation."""
    console.print("[bold cyan]Luminari Sage Chunk Generator[/bold cyan]")
    console.print("=" * 50)

    # Load embedding model with semantic chunking
    console.print("\n[yellow]Loading embedding model and semantic chunker...[/yellow]")
    generator = ChunkGenerator(use_semantic_chunking=True)
    console.print("[green]✓ Models loaded successfully (using semantic chunking)[/green]")

    try:
        await generator.generate_all_chunks()
        console.print("\n[green]✓ Chunk generation completed successfully![/green]")

    except Exception as e:
        console.print(f"\n[red]Fatal error type: {type(e).__name__}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
