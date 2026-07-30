"""Performance benchmark tests."""

import asyncio
import statistics
import time

import pytest

from src.llm.embeddings.factory import get_embedder
from src.llm.providers.factory import get_llm_provider


@pytest.mark.performance
@pytest.mark.integration
class TestPerformanceBenchmarks:
    """Performance benchmark suite."""

    @pytest.mark.asyncio
    async def test_generation_latency(self):
        """Benchmark text generation latency."""
        provider = get_llm_provider()
        prompts = [f"Test prompt {i}: Write one sentence." for i in range(10)]

        times = []
        print("\n\n⏱️  Benchmarking Generation Latency...")

        for i, prompt in enumerate(prompts, 1):
            start = time.time()
            await provider.generate(prompt, temperature=0.7)
            elapsed = time.time() - start
            times.append(elapsed)

            if i % 5 == 0:
                print(f"   Completed {i}/10 requests...")

        avg_time = statistics.mean(times)
        median_time = statistics.median(times)
        p95_time = sorted(times)[int(len(times) * 0.95)]
        min_time = min(times)
        max_time = max(times)

        print("\n📊 Generation Latency Results:")
        print(f"   Average: {avg_time:.2f}s")
        print(f"   Median: {median_time:.2f}s")
        print(f"   P95: {p95_time:.2f}s")
        print(f"   Min: {min_time:.2f}s")
        print(f"   Max: {max_time:.2f}s")

        # Performance targets (lenient for CI)
        assert avg_time < 10.0, f"Average latency too high: {avg_time:.2f}s"
        assert p95_time < 15.0, f"P95 latency too high: {p95_time:.2f}s"

        if avg_time < 3.0:
            print("   ✅ Excellent performance (<3s avg)")
        elif avg_time < 5.0:
            print("   ✅ Good performance (3-5s avg)")
        elif avg_time < 8.0:
            print("   ⚠️  Acceptable performance (5-8s avg)")
        else:
            print("   ⚠️  Slow performance (>8s avg)")

    @pytest.mark.asyncio
    async def test_embedding_throughput(self):
        """Benchmark embedding generation throughput."""
        embedder = get_embedder()
        texts = [f"Test text number {i} for embedding." for i in range(50)]

        print("\n\n📊 Benchmarking Embedding Throughput...")

        start = time.time()

        # Check if embedder has embed_batch method
        if hasattr(embedder, "embed_batch"):
            embeddings = await embedder.embed_batch(texts)
        else:
            # Fall back to individual embeds
            embeddings = []
            for text in texts:
                emb = await embedder.embed(text)
                embeddings.append(emb)

        elapsed = time.time() - start
        throughput = len(texts) / elapsed

        print("\n📈 Embedding Throughput Results:")
        print(f"   Total embeddings: {len(texts)}")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Throughput: {throughput:.1f} embeddings/sec")
        print(f"   Avg per embedding: {elapsed/len(texts):.3f}s")

        # Should achieve reasonable throughput
        assert throughput >= 5.0, f"Throughput too low: {throughput:.1f} embeddings/sec"

        if throughput >= 20.0:
            print("   ✅ Excellent throughput (≥20/sec)")
        elif throughput >= 10.0:
            print("   ✅ Good throughput (10-20/sec)")
        else:
            print("   ⚠️  Moderate throughput (<10/sec)")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling concurrent requests."""
        provider = get_llm_provider()

        print("\n\n🔀 Benchmarking Concurrent Requests...")

        async def make_request(i):
            start = time.time()
            await provider.generate(f"Request {i}", temperature=0.7)
            return time.time() - start

        # Make 5 concurrent requests
        num_concurrent = 5
        start = time.time()
        times = await asyncio.gather(*[make_request(i) for i in range(num_concurrent)])
        total_time = time.time() - start

        avg_request_time = statistics.mean(times)

        print("\n🔄 Concurrent Request Results:")
        print(f"   Concurrent requests: {num_concurrent}")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Average per request: {avg_request_time:.2f}s")
        print(f"   Individual times: {[f'{t:.2f}s' for t in times]}")

        # With queue, requests may be sequential
        # Total time ≈ sum of individual times (with some overhead)
        sum_individual = sum(times)
        print(f"   Sum of individual: {sum_individual:.2f}s")
        print(f"   Overhead: {(total_time - sum_individual):.2f}s")

        # Verify all requests completed
        assert len(times) == num_concurrent, "All requests should complete"

    @pytest.mark.asyncio
    async def test_streaming_performance(self):
        """Test streaming generation performance."""
        provider = get_llm_provider()

        print("\n\n📡 Benchmarking Streaming Performance...")

        prompt = "Count from 1 to 5 and explain each number briefly."

        start = time.time()
        chunks = []
        first_chunk_time = None

        async for chunk in provider.stream(prompt, temperature=0.7):
            chunks.append(chunk)
            if first_chunk_time is None:
                first_chunk_time = time.time() - start

        total_time = time.time() - start

        print("\n⚡ Streaming Results:")
        print(f"   Total chunks: {len(chunks)}")
        print(f"   Time to first chunk: {first_chunk_time:.2f}s")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Avg per chunk: {total_time/len(chunks):.3f}s")

        # First chunk should arrive reasonably fast
        assert first_chunk_time < 5.0, f"First chunk too slow: {first_chunk_time:.2f}s"

        if first_chunk_time < 2.0:
            print("   ✅ Fast first token (<2s)")
        else:
            print("   ⚠️  Slow first token (>2s)")

    @pytest.mark.asyncio
    async def test_small_vs_large_prompts(self):
        """Compare performance of small vs large prompts."""
        provider = get_llm_provider()

        print("\n\n📏 Benchmarking Small vs Large Prompts...")

        small_prompt = "Say hello."
        large_prompt = "Given the following detailed context about Crystal Dwarves: They live in Nagburim, mine crystals, have translucent skin, speak Tal language, are master gemcutters, and maintain the Crystalline Network. Please provide a comprehensive summary of their culture, traditions, and way of life."

        # Test small prompt
        start = time.time()
        await provider.generate(small_prompt, temperature=0.7)
        small_time = time.time() - start

        # Test large prompt
        start = time.time()
        await provider.generate(large_prompt, temperature=0.7)
        large_time = time.time() - start

        print("\n⚖️  Prompt Size Comparison:")
        print(f"   Small prompt ({len(small_prompt)} chars): {small_time:.2f}s")
        print(f"   Large prompt ({len(large_prompt)} chars): {large_time:.2f}s")
        print(f"   Ratio (large/small): {large_time/small_time:.2f}x")

        # Both should complete
        assert small_time > 0 and large_time > 0

    @pytest.mark.asyncio
    async def test_temperature_impact_on_speed(self):
        """Test if temperature affects generation speed."""
        provider = get_llm_provider()

        print("\n\n🌡️  Testing Temperature Impact on Speed...")

        prompt = "Write three sentences about mining."

        # Low temperature
        start = time.time()
        await provider.generate(prompt, temperature=0.1)
        low_temp_time = time.time() - start

        # High temperature
        start = time.time()
        await provider.generate(prompt, temperature=0.9)
        high_temp_time = time.time() - start

        print("\n🔥 Temperature Speed Results:")
        print(f"   Low temp (0.1): {low_temp_time:.2f}s")
        print(f"   High temp (0.9): {high_temp_time:.2f}s")
        print(f"   Difference: {abs(high_temp_time - low_temp_time):.2f}s")

        # Both should complete in reasonable time
        assert low_temp_time < 15.0 and high_temp_time < 15.0

    @pytest.mark.asyncio
    async def test_embedding_batch_efficiency(self):
        """Test batch embedding efficiency vs individual."""
        embedder = get_embedder()

        print("\n\n📦 Testing Batch Embedding Efficiency...")

        texts = [f"Test text {i}" for i in range(10)]

        # Individual embeddings
        start = time.time()
        individual_embeddings = []
        for text in texts:
            emb = await embedder.embed(text)
            individual_embeddings.append(emb)
        individual_time = time.time() - start

        # Batch embeddings (if supported)
        if hasattr(embedder, "embed_batch"):
            start = time.time()
            await embedder.embed_batch(texts)
            batch_time = time.time() - start

            print("\n⚡ Batch vs Individual:")
            print(f"   Individual: {individual_time:.2f}s ({individual_time/len(texts):.3f}s each)")
            print(f"   Batch: {batch_time:.2f}s ({batch_time/len(texts):.3f}s each)")
            print(f"   Speedup: {individual_time/batch_time:.2f}x")

            # Batch should be faster or similar
            assert batch_time <= individual_time * 1.2, "Batch should not be significantly slower"

            if batch_time < individual_time * 0.5:
                print("   ✅ Excellent batch speedup (>2x)")
            elif batch_time < individual_time:
                print("   ✅ Good batch speedup")
            else:
                print("   ⚠️  No significant batch speedup")
        else:
            print("\n   ⚠️  Batch embeddings not supported")
            print(f"   Individual time: {individual_time:.2f}s")


@pytest.mark.performance
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cold_start_vs_warm():
    """Test cold start vs warm performance."""
    from src.llm.providers.factory import reset_provider_cache

    print("\n\n🔄 Testing Cold Start vs Warm Performance...")

    # Cold start (fresh provider)
    reset_provider_cache()
    provider = get_llm_provider()

    start = time.time()
    await provider.generate("Test", temperature=0.7)
    cold_start_time = time.time() - start

    # Warm start (cached provider)
    start = time.time()
    await provider.generate("Test", temperature=0.7)
    warm_time = time.time() - start

    print("\n🌡️  Cold vs Warm Start:")
    print(f"   Cold start: {cold_start_time:.2f}s")
    print(f"   Warm: {warm_time:.2f}s")
    print(f"   Difference: {cold_start_time - warm_time:.2f}s")

    # Warm should be similar or faster
    # (May not be dramatically different with Ollama)


if __name__ == "__main__":
    # Allow running tests directly
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
