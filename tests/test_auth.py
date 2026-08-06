#!/usr/bin/env python3
"""
Test script for Sage authentication system.

This script tests the multi-key authentication system to ensure
it works correctly before deployment.
"""

import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.auth.api_key import KeyType, MultiKeyAuth
from src.auth.exceptions import InvalidAPIKeyError, MissingAPIKeyError


def test_multikey_auth(monkeypatch):
    """Test the MultiKeyAuth class with different scenarios."""

    for name in ("SAGE_API_KEY", "SAGE_MCP_KEY", "SAGE_MCP_BACKEND_KEY"):
        monkeypatch.delenv(name, raising=False)

    print("🧪 Testing MultiKeyAuth System")
    print("=" * 50)

    # Test 1: Empty keys (no environment variables set)
    print("\n1. Testing with no keys configured:")
    auth = MultiKeyAuth()

    # Should have empty key sets
    for key_type in KeyType:
        count = auth.get_key_count(key_type)
        print(f"   {key_type.value}: {count} keys")
        assert count == 0, f"Expected 0 keys for {key_type.value}, got {count}"

    print("   ✅ Empty key test passed")

    # Test 2: Add keys manually
    print("\n2. Testing manual key addition:")
    test_api_key = "unit-test-sage-api-key"
    test_mcp_key = "unit-test-sage-mcp-key"
    test_backend_key = "unit-test-sage-backend-key"

    auth.add_key(test_api_key, KeyType.BACKEND_API)
    auth.add_key(test_mcp_key, KeyType.MCP_OPERATIONS)
    auth.add_key(test_backend_key, KeyType.MCP_BACKEND_ACCESS)

    # Verify keys were added
    assert auth.is_valid_key(test_api_key, KeyType.BACKEND_API)
    assert auth.is_valid_key(test_mcp_key, KeyType.MCP_OPERATIONS)
    assert auth.is_valid_key(test_backend_key, KeyType.MCP_BACKEND_ACCESS)

    print("   ✅ Manual key addition test passed")

    # Test 3: Key validation
    print("\n3. Testing key validation:")

    # Valid key should pass
    try:
        result = auth.verify_key(test_api_key, KeyType.BACKEND_API)
        assert result
        print("   ✅ Valid key verification passed")
    except Exception as e:
        print(f"   ❌ Valid key verification failed: {e}")
        return False

    # Invalid key should fail
    try:
        auth.verify_key("invalid_key", KeyType.BACKEND_API)
        print("   ❌ Invalid key should have failed")
        return False
    except InvalidAPIKeyError:
        print("   ✅ Invalid key properly rejected")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False

    # Missing key should fail
    try:
        auth.verify_key(None, KeyType.BACKEND_API)
        print("   ❌ Missing key should have failed")
        return False
    except MissingAPIKeyError:
        print("   ✅ Missing key properly rejected")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False

    # Test 4: Wrong key type should fail
    print("\n4. Testing key type isolation:")
    try:
        auth.verify_key(test_api_key, KeyType.MCP_OPERATIONS)  # Wrong type
        print("   ❌ Wrong key type should have failed")
        return False
    except InvalidAPIKeyError:
        print("   ✅ Key type isolation working")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False

    print("\n🎉 All authentication tests passed!")
    return True


def test_environment_keys(monkeypatch):
    """Test authentication with environment variables."""

    print("\n🧪 Testing Environment Variable Integration")
    print("=" * 50)

    # Set test environment variables
    monkeypatch.setenv("SAGE_API_KEY", "unit-test-env-api-key")
    monkeypatch.setenv("SAGE_MCP_KEY", "unit-test-env-mcp-key")
    monkeypatch.setenv("SAGE_MCP_BACKEND_KEY", "unit-test-env-backend-key")

    # Create new auth instance to pick up env vars
    auth = MultiKeyAuth()

    # Test that environment keys are loaded
    assert auth.is_valid_key("unit-test-env-api-key", KeyType.BACKEND_API)
    assert auth.is_valid_key("unit-test-env-mcp-key", KeyType.MCP_OPERATIONS)
    assert auth.is_valid_key("unit-test-env-backend-key", KeyType.MCP_BACKEND_ACCESS)

    print("✅ Environment variable integration working")

    # Test DISABLE_AUTH functionality
    print("\nTesting DISABLE_AUTH functionality:")
    monkeypatch.setenv("DISABLE_AUTH", "true")
    auth_disabled = MultiKeyAuth()

    if auth_disabled.is_auth_disabled():
        print("✅ DISABLE_AUTH=true properly detected")
    else:
        print("❌ DISABLE_AUTH=true not working")
        return False

    return True


def main():
    """Run all authentication tests."""

    print("🚀 Starting Sage Authentication System Tests")
    print("=" * 60)

    success = True

    try:
        # Test core functionality
        if not test_multikey_auth():
            success = False

        # Test environment integration
        if not test_environment_keys():
            success = False

    except Exception as e:
        print(f"\n❌ Unexpected test failure: {e}")
        import traceback

        traceback.print_exc()
        success = False

    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED! Authentication system is ready.")
        return 0
    else:
        print("❌ TESTS FAILED! Please fix issues before deployment.")
        return 1


if __name__ == "__main__":
    exit(main())
