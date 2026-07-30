"""Pytest configuration and fixtures for Luminari Sage tests."""

import asyncio
from collections.abc import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config():
    """Test configuration settings."""
    return {
        "api_base_url": "http://localhost:8003",
        "mcp_base_url": "http://localhost:8004",
        "test_entity_id": "40dd54d0-e6f0-43a1-a8ad-2e5c9dc17c14",  # Void's Wake
        "test_relationship_id": 894,
        "timeout": 10,
    }


@pytest.fixture
def skip_if_no_data():
    """Skip tests if test data is not available."""

    def _skip_if_no_data(response):
        if not response or (hasattr(response, "status_code") and response.status_code == 404):
            pytest.skip("Test data not available - run data ingestion first")
        return response

    return _skip_if_no_data


@pytest.fixture
def skip_if_service_down():
    """Skip tests if services are not running."""

    def _skip_if_service_down(error_type=Exception):
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except error_type:
                    pytest.skip(f"Service not available: {error_type.__name__}")

            return wrapper

        return decorator

    return _skip_if_service_down


# Test data constants
TEST_QUERIES = {
    "simple": "Void's Wake",
    "complex": "Tell me about the relationship between Void's Wake and the Forgotten Tide",
    "entity_search": "void",
    "validation": "Paladine is the god of good dragons in Luminari.",
}


TEST_ENTITY_IDS = {
    "voids_wake": "40dd54d0-e6f0-43a1-a8ad-2e5c9dc17c14",
    "forgotten_tide": "b32e2a43-91a1-444a-a1bf-0a6c4b916aa4",
    "void_witch": "f220f0c6-f930-4d87-90e9-39430b69f554",
}


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring services"
    )
    config.addinivalue_line(
        "markers", "data_dependent: mark test as requiring test data to be loaded"
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")
