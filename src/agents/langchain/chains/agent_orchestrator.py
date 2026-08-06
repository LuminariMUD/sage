"""Compatibility planner for legacy multi-agent workflows.

The active chat service uses tool calling directly. This small deterministic
planner keeps the older orchestration API usable for integrations that still
request an explicit sequence of quest-building steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionStep:
    """One operation in a legacy orchestration plan."""

    step: int
    tool: str
    description: str
    input: dict[str, Any]
    output_key: str


@dataclass(frozen=True)
class ExecutionPlan:
    """A deterministic plan returned by :class:`AgentOrchestrator`."""

    user_intent: str
    needs_orchestration: bool
    execution_plan: list[ExecutionStep]


class AgentOrchestrator:
    """Build explicit plans for the retired keyword-routed agent interface."""

    _COUNT_PATTERNS = (
        re.compile(r"\b(\d+)\s*[- ]?quests?\b", re.IGNORECASE),
        re.compile(r"\bquestline\s+with\s+(\d+)\s+parts?\b", re.IGNORECASE),
        re.compile(r"\b(\d+)\s*[- ]?part\b", re.IGNORECASE),
    )

    async def _create_execution_plan(self, request: str) -> ExecutionPlan:
        """Create a connected quest plan without making an LLM request."""

        quest_count = 1
        for pattern in self._COUNT_PATTERNS:
            match = pattern.search(request)
            if match:
                quest_count = max(1, int(match.group(1)))
                break

        steps: list[ExecutionStep] = []
        for index in range(1, quest_count + 1):
            step_input: dict[str, Any] = {
                "premise": request,
                "quest_number": index,
                "total_quests": quest_count,
            }
            if index > 1:
                step_input["previous_context"] = f"{{{{step_{index - 1}}}}}"

            steps.append(
                ExecutionStep(
                    step=index,
                    tool="plan_quest",
                    description=f"Create connected quest {index} of {quest_count}",
                    input=step_input,
                    output_key=f"step_{index}",
                )
            )

        return ExecutionPlan(
            user_intent=request,
            needs_orchestration=quest_count > 1,
            execution_plan=steps,
        )


__all__ = ["AgentOrchestrator", "ExecutionPlan", "ExecutionStep"]
