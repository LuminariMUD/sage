"""Adversarial contracts for entity dedupe and summary completeness."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.graphiti import policy_graphiti
from src.graphiti.entity_stage_quality import (
    EntityStageQualityAccumulator,
    EntityStageQualityError,
)
from src.graphiti.policy_graphiti import EntityStageQualityLLMProxy


def _prompt(*, summaries: bool = False):
    if summaries:
        content = '<ENTITIES>[{"name":"Lumia"},{"name":"Nagburim"}]</ENTITIES>'
    else:
        content = (
            '<ENTITIES>[{"id":0},{"id":1}]</ENTITIES>\n'
            '<EXISTING ENTITIES>[{"candidate_id":10}]</EXISTING ENTITIES>'
        )
    return [SimpleNamespace(content=content)]


def test_shifted_absolute_dedupe_ids_are_missing_and_out_of_range():
    accumulator = EntityStageQualityAccumulator("observe_v1")

    report = accumulator.record_dedupe(
        _prompt(),
        {
            "entity_resolutions": [
                {"id": 1, "duplicate_candidate_id": -1},
                {"id": 2, "duplicate_candidate_id": 10},
            ]
        },
    )

    assert report.dedupe_expected_count == 2
    assert report.dedupe_returned_count == 2
    assert report.dedupe_missing_count == 1
    assert report.dedupe_out_of_range_count == 1
    assert report.has_anomalies


def test_duplicate_ids_and_invalid_candidates_are_counted_independently():
    accumulator = EntityStageQualityAccumulator("observe_v1")

    report = accumulator.record_dedupe(
        _prompt(),
        {
            "entity_resolutions": [
                {"id": 0, "duplicate_candidate_id": 99},
                {"id": 0, "duplicate_candidate_id": -1},
            ]
        },
    )

    assert report.dedupe_missing_count == 1
    assert report.dedupe_duplicate_id_count == 1
    assert report.dedupe_invalid_candidate_count == 1


def test_summary_names_must_be_a_complete_subset_of_requested_nodes():
    accumulator = EntityStageQualityAccumulator("observe_v1")

    report = accumulator.record_summary(
        _prompt(summaries=True),
        {"summaries": [{"name": "Lumia"}, {"name": "Unknown Example"}]},
    )

    assert report.summary_expected_count == 2
    assert report.summary_returned_count == 2
    assert report.summary_missing_count == 1
    assert report.summary_unknown_count == 1
    assert report.has_anomalies


async def test_strict_policy_raises_bounded_quality_error_on_incomplete_summary():
    delegate = SimpleNamespace(
        generate_response=AsyncMock(return_value={"summaries": [{"name": "Lumia"}]})
    )
    proxy = EntityStageQualityLLMProxy(delegate, "strict_v1")
    accumulator = EntityStageQualityAccumulator("strict_v1")
    token = policy_graphiti._CURRENT_ENTITY_STAGE_QUALITY.set(accumulator)
    try:
        with pytest.raises(
            EntityStageQualityError,
            match="entity_summary_response_incomplete",
        ) as raised:
            await proxy.generate_response(
                _prompt(summaries=True),
                prompt_name="extract_nodes.extract_summaries_batch",
            )
    finally:
        policy_graphiti._CURRENT_ENTITY_STAGE_QUALITY.reset(token)

    assert raised.value.quality_report.summary_missing_count == 1
    delegate.generate_response.assert_awaited_once()
