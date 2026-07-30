"""Stress tests for stability."""

import asyncio
import time

import pytest

from src.llm.providers.factory import get_llm_provider


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_sustained_load():
    """Test system under sustained load."""
    provider = get_llm_provider()
    num_requests = 50  # Reduced from 100 for reasonable test time

    print(f"\n\n🔥 Stress Test: {num_requests} Sequential Requests")
    print(f"{'='*60}")

    successful = 0
    failed = 0
    errors = []
    times = []

    start_time = time.time()

    for i in range(num_requests):
        try:
            request_start = time.time()
            await provider.generate(f"Request {i}: Write one word.", temperature=0.7)
            request_time = time.time() - request_start

            successful += 1
            times.append(request_time)

            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(
                    f"   Progress: {i+1}/{num_requests} ({successful} success, {failed} failed) - {rate:.1f} req/s"
                )

        except Exception as e:
            failed += 1
            errors.append(str(e))
            print(f"   ❌ Request {i} failed: {type(e).__name__}")

    total_time = time.time() - start_time

    print("\n📊 Stress Test Results:")
    print(f"   Total time: {total_time:.1f}s")
    print(f"   Successful: {successful}/{num_requests} ({successful/num_requests*100:.1f}%)")
    print(f"   Failed: {failed}/{num_requests}")
    print(
        f"   Average request time: {sum(times)/len(times):.2f}s"
        if times
        else "   No successful requests"
    )
    print(f"   Throughput: {num_requests/total_time:.2f} req/s")

    if errors:
        print("\n⚠️  Errors encountered:")
        unique_errors = list(set(errors))[:5]  # Show up to 5 unique errors
        for error in unique_errors:
            print(f"   - {error[:100]}")

    # Should have >90% success rate
    success_rate = successful / num_requests
    assert success_rate >= 0.90, f"Success rate too low: {success_rate*100:.1f}%"

    print(f"\n✅ Stress test passed with {success_rate*100:.1f}% success rate")


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_rapid_fire_requests():
    """Test handling of rapid consecutive requests."""
    provider = get_llm_provider()

    print("\n\n⚡ Rapid Fire Test: 20 Quick Requests")
    print(f"{'='*60}")

    num_requests = 20
    successful = 0
    failed = 0

    start_time = time.time()

    # Fire requests as fast as possible
    for i in range(num_requests):
        try:
            # Very short prompt for speed
            await provider.generate(f"Say {i}", temperature=0.5)
            successful += 1
        except Exception as e:
            failed += 1
            print(f"   ❌ Request {i} failed: {type(e).__name__}")

    elapsed = time.time() - start_time

    print("\n📊 Rapid Fire Results:")
    print(f"   Total time: {elapsed:.2f}s")
    print(f"   Successful: {successful}/{num_requests}")
    print(f"   Failed: {failed}/{num_requests}")
    print(f"   Average: {elapsed/num_requests:.2f}s per request")

    # Should handle rapid requests
    success_rate = successful / num_requests
    assert success_rate >= 0.85, f"Too many failures under rapid fire: {success_rate*100:.1f}%"

    print("✅ Rapid fire test passed")


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_stability():
    """Test for memory leaks."""
    try:
        import os

        import psutil
    except ImportError:
        pytest.skip("psutil not installed")

    process = psutil.Process(os.getpid())
    provider = get_llm_provider()

    print("\n\n💾 Memory Stability Test")
    print(f"{'='*60}")

    # Initial memory
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    print(f"   Initial memory: {initial_memory:.1f} MB")

    # Run many requests
    num_requests = 30
    for i in range(num_requests):
        await provider.generate("Test request", temperature=0.7)

        if (i + 1) % 10 == 0:
            current_memory = process.memory_info().rss / 1024 / 1024
            print(f"   After {i+1} requests: {current_memory:.1f} MB")

    # Final memory
    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory

    print("\n📈 Memory Usage:")
    print(f"   Initial: {initial_memory:.1f} MB")
    print(f"   Final: {final_memory:.1f} MB")
    print(f"   Increase: {memory_increase:.1f} MB")
    print(f"   Per request: {memory_increase/num_requests:.2f} MB")

    # Memory increase should be reasonable
    # Allow up to 200MB increase for 30 requests (very lenient)
    assert memory_increase < 200, f"Potential memory leak: {memory_increase:.1f} MB increase"

    if memory_increase < 50:
        print("   ✅ Excellent memory management (<50MB)")
    elif memory_increase < 100:
        print("   ✅ Good memory management (50-100MB)")
    else:
        print("   ⚠️  Moderate memory increase (>100MB)")


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_recovery():
    """Test recovery from errors."""
    provider = get_llm_provider()

    print("\n\n🔄 Error Recovery Test")
    print(f"{'='*60}")

    # Make a normal request
    response1 = await provider.generate("Test 1", temperature=0.7)
    assert len(response1) > 0
    print("   ✅ Normal request 1 succeeded")

    # Try a potentially problematic request
    try:
        await provider.generate("", temperature=0.7)  # Empty prompt
        print("   ⚠️  Empty prompt handled")
    except Exception as e:
        print(f"   ⚠️  Empty prompt raised: {type(e).__name__}")

    # Make another normal request to verify recovery
    response2 = await provider.generate("Test 2", temperature=0.7)
    assert len(response2) > 0
    print("   ✅ Normal request 2 succeeded (after potential error)")

    # Try very long prompt
    try:
        long_prompt = "test " * 1000
        await provider.generate(long_prompt, temperature=0.7)
        print("   ✅ Long prompt handled")
    except Exception as e:
        print(f"   ⚠️  Long prompt raised: {type(e).__name__}")

    # Verify still working
    response3 = await provider.generate("Test 3", temperature=0.7)
    assert len(response3) > 0
    print("   ✅ Normal request 3 succeeded (after long prompt)")

    print("\n✅ Error recovery test passed")


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_stress():
    """Test concurrent request handling under stress."""
    provider = get_llm_provider()

    print("\n\n🔀 Concurrent Stress Test")
    print(f"{'='*60}")

    async def make_request(i):
        """Make a single request."""
        try:
            await provider.generate(f"Concurrent {i}", temperature=0.7)
            return True
        except Exception as e:
            print(f"   ❌ Concurrent request {i} failed: {type(e).__name__}")
            return False

    # Make multiple waves of concurrent requests
    num_waves = 3
    requests_per_wave = 5

    total_successful = 0
    total_requests = num_waves * requests_per_wave

    for wave in range(num_waves):
        print(f"\n   Wave {wave + 1}/{num_waves}...")
        start = time.time()

        results = await asyncio.gather(*[make_request(i) for i in range(requests_per_wave)])
        wave_successful = sum(results)
        total_successful += wave_successful

        elapsed = time.time() - start
        print(
            f"   Wave completed in {elapsed:.2f}s ({wave_successful}/{requests_per_wave} succeeded)"
        )

    success_rate = total_successful / total_requests

    print("\n📊 Concurrent Stress Results:")
    print(f"   Total requests: {total_requests}")
    print(f"   Successful: {total_successful}")
    print(f"   Success rate: {success_rate*100:.1f}%")

    # Should handle concurrent stress
    assert (
        success_rate >= 0.80
    ), f"Success rate too low under concurrent stress: {success_rate*100:.1f}%"

    print("✅ Concurrent stress test passed")


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_extended_runtime():
    """Test stability over extended runtime."""
    provider = get_llm_provider()

    print("\n\n⏰ Extended Runtime Test (2 minutes)")
    print(f"{'='*60}")

    duration = 120  # 2 minutes
    start_time = time.time()
    request_count = 0
    error_count = 0

    while time.time() - start_time < duration:
        try:
            await provider.generate(f"Extended test {request_count}", temperature=0.7)
            request_count += 1

            if request_count % 10 == 0:
                elapsed = time.time() - start_time
                remaining = duration - elapsed
                rate = request_count / elapsed
                print(
                    f"   {elapsed:.0f}s: {request_count} requests ({rate:.1f} req/s) - {remaining:.0f}s remaining"
                )

        except Exception as e:
            error_count += 1
            print(f"   ❌ Error at {time.time() - start_time:.0f}s: {type(e).__name__}")

        # Small delay to prevent overwhelming the system
        await asyncio.sleep(0.5)

    total_time = time.time() - start_time
    success_rate = (request_count - error_count) / request_count if request_count > 0 else 0

    print("\n📊 Extended Runtime Results:")
    print(f"   Duration: {total_time:.1f}s")
    print(f"   Total requests: {request_count}")
    print(f"   Errors: {error_count}")
    print(f"   Success rate: {success_rate*100:.1f}%")
    print(f"   Average rate: {request_count/total_time:.2f} req/s")

    # Should maintain stability
    assert request_count > 0, "Should complete at least one request"
    assert (
        success_rate >= 0.85
    ), f"Success rate too low over extended runtime: {success_rate*100:.1f}%"

    print("✅ Extended runtime test passed")


@pytest.mark.stress
@pytest.mark.integration
@pytest.mark.asyncio
async def test_embedding_stress():
    """Test embedding generation under stress."""
    from src.llm.embeddings.factory import get_embedder

    embedder = get_embedder()

    print("\n\n🔢 Embedding Stress Test")
    print(f"{'='*60}")

    num_batches = 10
    batch_size = 20
    total_embeddings = num_batches * batch_size

    successful = 0
    failed = 0

    start_time = time.time()

    for batch_num in range(num_batches):
        texts = [f"Embedding test {batch_num}_{i}" for i in range(batch_size)]

        try:
            if hasattr(embedder, "embed_batch"):
                embeddings = await embedder.embed_batch(texts)
            else:
                embeddings = [await embedder.embed(text) for text in texts]

            successful += len(embeddings)

            if (batch_num + 1) % 3 == 0:
                elapsed = time.time() - start_time
                rate = successful / elapsed
                print(
                    f"   Batch {batch_num + 1}/{num_batches}: {successful} embeddings - {rate:.1f} emb/s"
                )

        except Exception as e:
            failed += batch_size
            print(f"   ❌ Batch {batch_num} failed: {type(e).__name__}")

    total_time = time.time() - start_time

    print("\n📊 Embedding Stress Results:")
    print(f"   Total time: {total_time:.1f}s")
    print(f"   Total embeddings: {total_embeddings}")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"   Throughput: {successful/total_time:.1f} embeddings/s")

    success_rate = successful / total_embeddings
    assert success_rate >= 0.90, f"Embedding success rate too low: {success_rate*100:.1f}%"

    print("✅ Embedding stress test passed")


if __name__ == "__main__":
    # Allow running tests directly
    import sys

    sys.exit(pytest.main([__file__, "-v", "-s"]))
