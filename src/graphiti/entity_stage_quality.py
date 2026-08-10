"""Fail-closed quality checks for Graphiti entity maintenance responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

ENTITY_RESPONSE_POLICY_OFF = "off"
ENTITY_RESPONSE_POLICY_OBSERVE_V1 = "observe_v1"
ENTITY_RESPONSE_POLICY_STRICT_V1 = "strict_v1"
ENTITY_RESPONSE_POLICIES = frozenset(
    {
        ENTITY_RESPONSE_POLICY_OFF,
        ENTITY_RESPONSE_POLICY_OBSERVE_V1,
        ENTITY_RESPONSE_POLICY_STRICT_V1,
    }
)

_ENTITIES_BLOCK = re.compile(r"<ENTITIES>\s*(\[.*?\])\s*</ENTITIES>", re.DOTALL)
_EXISTING_ENTITIES_BLOCK = re.compile(
    r"<EXISTING ENTITIES>\s*(\[.*?\])\s*</EXISTING ENTITIES>",
    re.DOTALL,
)


class EntityStageQualityError(RuntimeError):
    """A dedupe or summary response violated its bounded stage contract."""

    def __init__(self, code: str, report: EntityStageQualityReport):
        super().__init__(code)
        self.code = code
        self.quality_report = report


def resolve_entity_response_policy(value: str | None) -> str:
    parsed = (value or ENTITY_RESPONSE_POLICY_OFF).strip().lower()
    if parsed not in ENTITY_RESPONSE_POLICIES:
        raise ValueError("Entity response policy is unsupported")
    return parsed


def _content(prompt: object) -> str:
    messages = prompt if isinstance(prompt, list) else []
    return "\n".join(
        str(getattr(message, "content", ""))
        for message in messages
        if getattr(message, "content", None) is not None
    )


def _json_block(pattern: re.Pattern[str], prompt: object) -> list[dict[str, Any]]:
    match = pattern.search(_content(prompt))
    if match is None:
        raise ValueError("Entity-stage prompt context is incomplete")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError("Entity-stage prompt context is malformed") from error
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("Entity-stage prompt entities are malformed")
    return payload


def _response_items(response: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise ValueError("Entity-stage response must be an object")
    payload = response.get(key)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("Entity-stage response list is malformed")
    return payload


@dataclass(frozen=True)
class EntityStageQualityReport:
    policy: str
    dedupe_expected_count: int = 0
    dedupe_returned_count: int = 0
    dedupe_missing_count: int = 0
    dedupe_duplicate_id_count: int = 0
    dedupe_out_of_range_count: int = 0
    dedupe_invalid_candidate_count: int = 0
    summary_expected_count: int = 0
    summary_returned_count: int = 0
    summary_missing_count: int = 0
    summary_unknown_count: int = 0

    @property
    def has_anomalies(self) -> bool:
        return any(
            (
                self.dedupe_missing_count,
                self.dedupe_duplicate_id_count,
                self.dedupe_out_of_range_count,
                self.dedupe_invalid_candidate_count,
                self.summary_missing_count,
                self.summary_unknown_count,
            )
        )

    def as_dict(self) -> dict[str, str | int | bool]:
        return {
            "policy": self.policy,
            "dedupe_expected_count": self.dedupe_expected_count,
            "dedupe_returned_count": self.dedupe_returned_count,
            "dedupe_missing_count": self.dedupe_missing_count,
            "dedupe_duplicate_id_count": self.dedupe_duplicate_id_count,
            "dedupe_out_of_range_count": self.dedupe_out_of_range_count,
            "dedupe_invalid_candidate_count": self.dedupe_invalid_candidate_count,
            "summary_expected_count": self.summary_expected_count,
            "summary_returned_count": self.summary_returned_count,
            "summary_missing_count": self.summary_missing_count,
            "summary_unknown_count": self.summary_unknown_count,
            "has_anomalies": self.has_anomalies,
        }


class EntityStageQualityAccumulator:
    """Aggregate content-free stage counts across one episode call."""

    def __init__(self, policy: str):
        self.policy = resolve_entity_response_policy(policy)
        self._counts = dict.fromkeys(
            (
                "dedupe_expected_count",
                "dedupe_returned_count",
                "dedupe_missing_count",
                "dedupe_duplicate_id_count",
                "dedupe_out_of_range_count",
                "dedupe_invalid_candidate_count",
                "summary_expected_count",
                "summary_returned_count",
                "summary_missing_count",
                "summary_unknown_count",
            ),
            0,
        )

    def report(self) -> EntityStageQualityReport:
        return EntityStageQualityReport(policy=self.policy, **self._counts)

    def record_dedupe(self, prompt: object, response: object) -> EntityStageQualityReport:
        extracted = _json_block(_ENTITIES_BLOCK, prompt)
        candidates = _json_block(_EXISTING_ENTITIES_BLOCK, prompt)
        resolutions = _response_items(response, "entity_resolutions")
        expected_ids = {int(item["id"]) for item in extracted if isinstance(item.get("id"), int)}
        candidate_ids = {
            int(item["candidate_id"])
            for item in candidates
            if isinstance(item.get("candidate_id"), int)
        }
        returned_ids = [item.get("id") for item in resolutions]
        valid_returned = [value for value in returned_ids if isinstance(value, int)]
        returned_set = set(valid_returned)
        duplicate_count = len(valid_returned) - len(returned_set)
        out_of_range = sum(value not in expected_ids for value in valid_returned)
        out_of_range += sum(not isinstance(value, int) for value in returned_ids)
        invalid_candidates = sum(
            not isinstance(item.get("duplicate_candidate_id"), int)
            or (
                int(item["duplicate_candidate_id"]) != -1
                and int(item["duplicate_candidate_id"]) not in candidate_ids
            )
            for item in resolutions
        )
        self._counts["dedupe_expected_count"] += len(expected_ids)
        self._counts["dedupe_returned_count"] += len(resolutions)
        self._counts["dedupe_missing_count"] += len(expected_ids - returned_set)
        self._counts["dedupe_duplicate_id_count"] += duplicate_count
        self._counts["dedupe_out_of_range_count"] += out_of_range
        self._counts["dedupe_invalid_candidate_count"] += invalid_candidates
        return self.report()

    def record_summary(self, prompt: object, response: object) -> EntityStageQualityReport:
        expected_entities = _json_block(_ENTITIES_BLOCK, prompt)
        summaries = _response_items(response, "summaries")
        expected_names = {
            str(item.get("name") or "").strip().casefold()
            for item in expected_entities
            if str(item.get("name") or "").strip()
        }
        returned_names = [str(item.get("name") or "").strip().casefold() for item in summaries]
        returned_set = {name for name in returned_names if name}
        self._counts["summary_expected_count"] += len(expected_names)
        self._counts["summary_returned_count"] += len(summaries)
        self._counts["summary_missing_count"] += len(expected_names - returned_set)
        self._counts["summary_unknown_count"] += sum(
            not name or name not in expected_names for name in returned_names
        )
        return self.report()
