"""Test streaming functionality with provider abstraction.

This module tests that LangChain streaming works correctly with both
OpenAI and Ollama providers via the provider abstraction layer.
"""

import pytest

from src.llm.langchain_helpers import get_chat_model


@pytest.mark.integration
@pytest.mark.asyncio
async def test_langchain_streaming_async():
    """Test LangChain async streaming with configured provider."""
    llm = get_chat_model(task="chat", temperature=0.7, streaming=True)

    chunks = []
    async for chunk in llm.astream("Write a haiku about crystal dwarves."):
        chunks.append(chunk.content)
        # Print each chunk for visibility
        print(chunk.content, end="", flush=True)

    full_response = "".join(chunks)
    assert len(full_response) > 0, "Streaming should produce content"
    assert len(chunks) > 1, "Streaming should produce multiple chunks"

    print(f"\n\nFull response ({len(chunks)} chunks): {full_response}")


@pytest.mark.integration
async def test_langchain_invoke():
    """Test LangChain synchronous invocation."""
    llm = get_chat_model(task="chat", temperature=0.7, streaming=False)

    response = llm.invoke("What are crystal dwarves?")
    assert len(response.content) > 0, "Invoke should produce content"
    print(f"Response: {response.content}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_langchain_ainvoke():
    """Test LangChain async invocation (non-streaming)."""
    llm = get_chat_model(task="chat", temperature=0.7, streaming=False)

    response = await llm.ainvoke("Describe a crystal cavern in one sentence.")
    assert len(response.content) > 0, "Async invoke should produce content"
    print(f"Response: {response.content}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_creative_task_streaming():
    """Test streaming with creative task (higher temperature)."""
    llm = get_chat_model(task="creative", temperature=0.9, streaming=True)

    chunks = []
    async for chunk in llm.astream("Create a short quest hook about dwarves."):
        chunks.append(chunk.content)

    full_response = "".join(chunks)
    assert len(full_response) > 0, "Creative streaming should produce content"
    print(f"\n\nCreative response: {full_response}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reasoning_task_streaming():
    """Test streaming with reasoning task (lower temperature)."""
    llm = get_chat_model(task="reasoning", temperature=0.5, streaming=True)

    chunks = []
    query = "Analyze the relationship between Crystal Dwarves and their environment."
    async for chunk in llm.astream(query):
        chunks.append(chunk.content)

    full_response = "".join(chunks)
    assert len(full_response) > 0, "Reasoning streaming should produce content"
    print(f"\n\nReasoning response: {full_response}")


@pytest.mark.integration
def test_streaming_with_max_tokens():
    """Test streaming with max_tokens parameter."""
    llm = get_chat_model(task="chat", temperature=0.7, streaming=True, max_tokens=50)

    response = llm.invoke("Tell me about crystal dwarves.")
    # With max_tokens=50, response should be truncated
    assert len(response.content) > 0, "Should produce content"
    print(f"Limited response (max 50 tokens): {response.content}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_streaming():
    """Test streaming multiple queries in sequence."""
    llm = get_chat_model(task="chat", temperature=0.7, streaming=True)

    queries = [
        "Name one race in LuminariMUD.",
        "Name one location in LuminariMUD.",
        "Name one type of magic.",
    ]

    responses = []
    for query in queries:
        chunks = []
        async for chunk in llm.astream(query):
            chunks.append(chunk.content)
        full_response = "".join(chunks)
        responses.append(full_response)
        print(f"\nQuery: {query}")
        print(f"Response: {full_response}")

    assert len(responses) == 3, "Should get responses for all queries"
    assert all(len(r) > 0 for r in responses), "All responses should have content"


if __name__ == "__main__":
    # Allow running tests directly for quick verification
    import asyncio

    print("Testing LangChain streaming with provider abstraction...")
    print("=" * 60)

    async def run_tests():
        print("\n1. Testing async streaming...")
        await test_langchain_streaming_async()

        print("\n\n2. Testing sync invoke...")
        await test_langchain_invoke()

        print("\n\n3. Testing async invoke...")
        await test_langchain_ainvoke()

        print("\n\n4. Testing creative task...")
        await test_creative_task_streaming()

        print("\n\n5. Testing reasoning task...")
        await test_reasoning_task_streaming()

    asyncio.run(run_tests())
    print("\n\nAll manual tests completed!")
