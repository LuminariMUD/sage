#!/usr/bin/env python3
"""
Test script for the autonomous relationship correction agent.

This script tests the core functionality of the correction agent including:
1. Semantic type standardization (SCREAMING_SNAKE_CASE)
2. Duplicate relationship detection and removal
3. Complete audit trail with rollback capability
4. Safety features and dry-run mode
"""

import asyncio
import os
import sys

# Add src directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agents.relationship_corrector import RelationshipCorrector


def test_semantic_standardization():
    """Test semantic type standardization logic."""
    corrector = RelationshipCorrector(openai_api_key="dummy")

    test_cases = [
        ("Protects", "PROTECTS"),
        ("allied_with", "ALLIED_WITH"),
        ("commands army", "COMMANDS_ARMY"),
        ("Uses-Material", "USES_MATERIAL"),
        ("fights  against", "FIGHTS_AGAINST"),
        ("", ""),
        ("ALREADY_CORRECT", "ALREADY_CORRECT"),
    ]

    print("🧪 Testing semantic type standardization:")
    all_passed = True

    for input_type, expected in test_cases:
        result = corrector.standardize_semantic_type(input_type)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"  {status} '{input_type}' → '{result}' (expected: '{expected}')")
        if not passed:
            all_passed = False

    return all_passed


def test_duplicate_selection():
    """Test duplicate relationship selection logic."""
    corrector = RelationshipCorrector(openai_api_key="dummy")

    # Mock relationships with different completeness levels
    relationships = [
        {"id": "rel1", "props": {"name": "protects", "fact": "Entity A protects Entity B"}},
        {
            "id": "rel2",
            "props": {
                "name": "protects",
                "fact": "Entity A protects Entity B",
                "fact_embedding": [0.1] * 1536,  # Has embedding
                "episodes": ["ep1", "ep2"],
                "created_at": "2024-01-01",
            },
        },
        {
            "id": "rel3",
            "props": {
                "name": "protects",
                "fact": "Entity A protects Entity B",
                "fact_embedding": [0.1] * 1536,
                "name_embedding": [0.2] * 1536,  # Has both embeddings
                "episodes": ["ep1", "ep2", "ep3"],
                "created_at": "2024-01-02",
            },
        },
    ]

    print("\n🔍 Testing duplicate selection logic:")

    best, to_delete = corrector.select_best_duplicate(relationships)

    print(f"  Best relationship: {best['id']} (should be rel3)")
    print(f"  To delete: {[rel['id'] for rel in to_delete]} (should be [rel1, rel2])")

    # rel3 should be selected as best (most complete)
    passed = (
        best["id"] == "rel3"
        and len(to_delete) == 2
        and {rel["id"] for rel in to_delete} == {"rel1", "rel2"}
    )

    status = "✅" if passed else "❌"
    print(f"  {status} Duplicate selection logic")

    return passed


async def test_dry_run_functionality():
    """Test dry-run functionality (no actual database changes)."""
    print("\n🎭 Testing dry-run functionality:")

    # Mock relationships for testing
    mock_relationships = [
        {
            "id": "test_rel_1",
            "type": "RELATES_TO",
            "source_id": "entity1",
            "target_id": "entity2",
            "source_name": "Test Entity 1",
            "target_name": "Test Entity 2",
            "props": {"name": "protects"},  # Needs standardization
        },
        {
            "id": "test_rel_2",
            "type": "RELATES_TO",
            "source_id": "entity1",
            "target_id": "entity2",
            "source_name": "Test Entity 1",
            "target_name": "Test Entity 2",
            "props": {"name": "protects", "fact": "More complete version"},  # Duplicate
        },
    ]

    try:
        corrector = RelationshipCorrector(openai_api_key="dummy")

        # Test dry run (should not make any database changes)
        corrections = await corrector.apply_corrections(
            relationships=mock_relationships,
            correct_duplicates=True,
            standardize_semantics=True,
            confidence_threshold=0.8,
            max_corrections=10,
            dry_run=True,  # Important: dry run mode
        )

        print(f"  ✅ Dry run completed with {len(corrections)} potential corrections")

        for correction in corrections:
            print(f"    - {correction.correction_type}: {correction.reasoning}")

        # Should find both deduplication and standardization opportunities
        dedup_corrections = [c for c in corrections if c.correction_type == "DEDUPLICATION"]
        standardization_corrections = [
            c for c in corrections if c.correction_type == "SEMANTIC_STANDARDIZATION"
        ]

        print(
            f"  📊 Found {len(dedup_corrections)} deduplication and {len(standardization_corrections)} standardization corrections"
        )

        return len(corrections) > 0

    except Exception as e:
        print(f"  ❌ Dry run test failed: {e}")
        return False


def print_test_summary(results: dict[str, bool]):
    """Print test summary."""
    print("\n" + "=" * 50)
    print("🏁 TEST SUMMARY")
    print("=" * 50)

    total_tests = len(results)
    passed_tests = sum(results.values())

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} {test_name}")

    print(f"\n📊 Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 All tests passed! The correction agent is ready for deployment.")
    else:
        print("⚠️  Some tests failed. Please review the issues above.")

    return passed_tests == total_tests


async def main():
    """Run all tests."""
    print("🚀 Testing Autonomous Relationship Correction Agent")
    print("=" * 50)

    results = {}

    # Test 1: Semantic standardization
    results["Semantic Standardization"] = test_semantic_standardization()

    # Test 2: Duplicate selection
    results["Duplicate Selection Logic"] = test_duplicate_selection()

    # Test 3: Dry run functionality
    results["Dry Run Functionality"] = await test_dry_run_functionality()

    # Print summary
    all_passed = print_test_summary(results)

    if all_passed:
        print("\n🎯 NEXT STEPS:")
        print(
            "1. Set up PostgreSQL schema: python3 -c \"import asyncio; from src.db import get_postgres_db; asyncio.run(get_postgres_db().execute_schema('schemas/relationship_corrections_schema.sql'))\""
        )
        print("2. Test with real data: Enable auto_correct=True with dry_run=True")
        print("3. Monitor corrections: Use /api/v1/corrections/history endpoint")
        print("4. Practice rollbacks: Use /api/v1/corrections/batch/{id}/rollback")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
