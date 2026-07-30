"""Comprehensive performance benchmark suite."""

import asyncio
import os
import statistics
import sys
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm.embeddings.factory import get_embedder
from src.llm.providers.factory import get_llm_provider


async def benchmark_generation_speed():
    """Benchmark text generation speed."""
    print("\n" + "=" * 60)
    print("📊 TEXT GENERATION BENCHMARK")
    print("=" * 60)

    try:
        provider = get_llm_provider()
        print(f"Provider: {provider.get_model_info()['provider']}")

        prompts = [
            "Write one sentence about crystal dwarves.",
            "Describe a magical crystal in 20 words.",
            "What is the capital of Nagburim?",
            "Tell me about the lore of LuminariMUD.",
            "Explain the significance of crystals in fantasy lore.",
        ]

        times = []
        tokens_per_sec = []
        total_tokens = 0

        for i, prompt in enumerate(prompts, 1):
            print(f"\n  Test {i}/{len(prompts)}: {prompt[:50]}...")
            start = time.time()

            try:
                response = await provider.generate(prompt, temperature=0.7)
                elapsed = time.time() - start

                # Rough token estimate (words * 1.3)
                tokens = len(response.split()) * 1.3
                tps = tokens / elapsed if elapsed > 0 else 0

                times.append(elapsed)
                tokens_per_sec.append(tps)
                total_tokens += tokens

                print(f"    ✓ Completed in {elapsed:.2f}s ({tps:.1f} tokens/sec)")
                print(f"    Response length: {len(response)} chars (~{int(tokens)} tokens)")

            except Exception as e:
                print(f"    ✗ Failed ({type(e).__name__})")

        if times:
            print("\n  📈 Results:")
            print(f"    Average time: {statistics.mean(times):.2f}s")
            print(f"    Min time: {min(times):.2f}s")
            print(f"    Max time: {max(times):.2f}s")
            print(f"    Average tokens/sec: {statistics.mean(tokens_per_sec):.1f}")
            print(f"    Total tokens generated: ~{int(total_tokens)}")
        else:
            print("\n  ⚠️ No successful generations")

    except Exception as e:
        print(f"\n  ❌ Benchmark failed ({type(e).__name__})")


async def benchmark_embedding_speed():
    """Benchmark embedding generation."""
    print("\n" + "=" * 60)
    print("📊 EMBEDDING BENCHMARK")
    print("=" * 60)

    try:
        embedder = get_embedder()
        print(f"Embedder type: {type(embedder).__name__}")

        # Test single embedding
        print("\n  Single embedding test:")
        test_text = "The crystal dwarves of Nagburim mine magical crystals."
        start = time.time()
        embedding = await embedder.embed_text(test_text)
        elapsed = time.time() - start
        print(f"    ✓ Generated in {elapsed:.3f}s")
        print(f"    Dimension: {len(embedding)}")

        # Test batch embeddings
        batch_sizes = [10, 32, 50]
        for batch_size in batch_sizes:
            print(f"\n  Batch embedding test (n={batch_size}):")
            texts = [f"Test text number {i} about fantasy lore." for i in range(batch_size)]

            start = time.time()
            await embedder.embed_batch(texts)
            elapsed = time.time() - start

            embeddings_per_sec = batch_size / elapsed if elapsed > 0 else 0
            print(f"    ✓ Generated {batch_size} embeddings in {elapsed:.2f}s")
            print(f"    Speed: {embeddings_per_sec:.1f} embeddings/sec")

        # Project larger batch performance
        print("\n  📈 Projected performance:")
        print(f"    100 embeddings: ~{100 / embeddings_per_sec:.1f}s")
        print(f"    1000 embeddings: ~{1000 / embeddings_per_sec / 60:.1f} minutes")

    except Exception as e:
        print(f"\n  ❌ Benchmark failed ({type(e).__name__})")


async def benchmark_concurrent_requests():
    """Benchmark concurrent request handling."""
    print("\n" + "=" * 60)
    print("📊 CONCURRENT REQUEST BENCHMARK")
    print("=" * 60)

    try:
        provider = get_llm_provider()

        # Test sequential execution
        print("\n  Sequential execution (5 requests):")
        prompts = [f"Request {i}: Tell me about fantasy lore." for i in range(5)]

        start = time.time()
        for prompt in prompts:
            await provider.generate(prompt[:50], temperature=0.7)
        sequential_time = time.time() - start

        print(f"    ✓ Completed in {sequential_time:.2f}s")
        print(f"    Average per request: {sequential_time / 5:.2f}s")

        # Test concurrent execution (will be queued for Ollama)
        print("\n  Concurrent execution (5 requests):")
        start = time.time()
        tasks = [provider.generate(prompt[:50], temperature=0.7) for prompt in prompts]
        await asyncio.gather(*tasks)
        concurrent_time = time.time() - start

        print(f"    ✓ Completed in {concurrent_time:.2f}s")
        print(f"    Average per request: {concurrent_time / 5:.2f}s")

        if concurrent_time < sequential_time * 0.9:
            print(f"    📈 Speedup: {sequential_time / concurrent_time:.2f}x")
        else:
            print("    ℹ️ Sequential execution (request queuing active)")

    except Exception as e:
        print(f"\n  ❌ Benchmark failed ({type(e).__name__})")


async def benchmark_rag_query():
    """Benchmark RAG query performance (simulated)."""
    print("\n" + "=" * 60)
    print("📊 RAG QUERY BENCHMARK (Simulated)")
    print("=" * 60)

    print("\n  Note: This would require running API server")
    print("  Use the following command to test RAG performance:")
    print("    curl -X POST http://localhost:8003/api/v1/rag/query \\")
    print("      -H 'Content-Type: application/json' \\")
    print('      -d \'{"query": "Who are the crystal dwarves?", "limit": 5}\'')


async def main():
    """Run all benchmarks."""
    print("\n" + "=" * 60)
    print("🚀 LUMINARI SAGE PERFORMANCE BENCHMARKS")
    print("=" * 60)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Check environment
    provider = os.getenv("LLM_PROVIDER", "ollama")
    print(f"LLM Provider: {provider}")

    # Run benchmarks
    await benchmark_generation_speed()
    await benchmark_embedding_speed()
    await benchmark_concurrent_requests()
    await benchmark_rag_query()

    print("\n" + "=" * 60)
    print("✅ BENCHMARKS COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Benchmarks interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error type: {type(e).__name__}")
        sys.exit(1)
