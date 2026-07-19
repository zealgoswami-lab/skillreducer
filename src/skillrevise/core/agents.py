from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

from skillrevise.core.models import ExecutionTrace, Skill, TaskSpec, TrajectoryEvent

ABSOLUTE_MARKERS = ("always", "must", "directly", "without checking", "never")
VALIDATION_MARKERS = ("verify", "check", "inspect", "confirm", "fallback")
WORKFLOW_MARKERS = ("first", "then", "before", "after", "workflow")
ENVIRONMENT_MARKERS = ("environment", "repository-native", "available", "entrypoint", "tool", "file")
FALLBACK_MARKERS = ("fallback", "if unavailable", "alternative", "otherwise")
STRICT_MARKERS = ("do not", "only after", "stop", "avoid", "must not")


class AgentAdapter(Protocol):
    def run(self, task: TaskSpec, skill: Skill | None) -> ExecutionTrace:
        """Execute one task, optionally with a skill injected."""


class MockAgentAdapter:
    """Deterministic stand-in for early harness development.

    The adapter simulates a realistic failure pattern:
    direct skills often fail because they hard-code a path/command or skip validation,
    while revised skills improve once they verify the environment and use fallback logic.
    """

    def run(self, task: TaskSpec, skill: Skill | None) -> ExecutionTrace:
        now = datetime.now(timezone.utc)
        base_tokens = int(task.metadata.get("base_tokens", 1_500))
        base_steps = int(task.metadata.get("base_steps", 10))
        base_tools = int(task.metadata.get("base_tool_calls", 6))
        base_latency = float(task.metadata.get("base_latency_seconds", 18.0))
        success_threshold = float(task.metadata.get("success_threshold", 0.6))

        score, events = self._score_task(task, skill)
        success = score >= success_threshold

        if skill is None:
            tokens = base_tokens
            steps = base_steps
            tool_calls = base_tools
            latency = base_latency
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="baseline",
                    summary="Agent explores the repo without external skill guidance.",
                )
            )
        else:
            word_count = len(skill.as_markdown().split())
            delta = score - float(task.metadata.get("base_success", 0.5))
            if delta >= 0:
                reduction = min(0.35, 0.28 * delta + 0.05)
                tokens = max(400, int(base_tokens * (1 - reduction) + 18 * len(skill.procedure)))
                steps = max(3, int(base_steps * (1 - min(0.3, 0.4 * delta))))
                tool_calls = max(2, int(base_tools * (1 - min(0.25, 0.3 * delta))))
                latency = round(max(4.0, base_latency * (1 - min(0.25, 0.35 * delta))), 2)
            else:
                inflation = min(0.9, abs(delta) * 0.7 + max(0, word_count - 180) / 300.0)
                tokens = int(base_tokens * (1.2 + inflation) + 22 * len(skill.procedure))
                steps = int(base_steps * (1.1 + min(0.35, abs(delta))))
                tool_calls = int(base_tools * (1.1 + min(0.3, abs(delta))))
                latency = round(base_latency * (1.15 + min(0.45, abs(delta))), 2)

        outcome = "Accepted by mock verifier." if success else "Rejected by mock verifier."
        end_time = now + timedelta(seconds=latency)
        return ExecutionTrace(
            run_id=uuid4().hex[:10],
            task_id=task.task_id,
            skill_version=None if skill is None else skill.version,
            success=success,
            status="success" if success else "failure",
            started_at=now.isoformat(),
            ended_at=end_time.isoformat(),
            tokens=tokens,
            tool_calls=tool_calls,
            steps=steps,
            latency_seconds=latency,
            outcome_summary=outcome,
            events=events,
            metadata={"mock_score": round(score, 4)},
        )

    def _score_task(self, task: TaskSpec, skill: Skill | None) -> tuple[float, list[TrajectoryEvent]]:
        score = float(task.metadata.get("base_success", 0.5))
        events: list[TrajectoryEvent] = []
        if skill is None:
            return score, events

        text = skill.as_markdown().lower()
        keywords = [item.lower() for item in task.metadata.get("skill_keywords", [])]
        anti_patterns = [item.lower() for item in task.metadata.get("anti_patterns", [])]
        requires_validation = bool(task.metadata.get("requires_validation", False))
        family_bonus = task.family.lower() in skill.when_to_use.lower() or task.family.lower() in skill.purpose.lower()

        if keywords:
            matched = [keyword for keyword in keywords if keyword in text]
            coverage = len(matched) / len(keywords)
            score += 0.45 * coverage
            if coverage < 0.4:
                events.append(
                    TrajectoryEvent(
                        step_index=len(events) + 1,
                        kind="plan_gap",
                        summary="Skill does not cover enough family-level workflow cues.",
                        evidence=", ".join(keywords[:3]),
                    )
                )

        if family_bonus:
            score += 0.08

        has_validation = any(marker in text for marker in VALIDATION_MARKERS)
        if requires_validation and has_validation:
            score += 0.18
        elif requires_validation:
            score -= 0.15
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="assumption_error",
                    summary="Skill skips environment validation before acting.",
                )
            )

        if any(marker in text for marker in WORKFLOW_MARKERS):
            score += 0.06

        if any(marker in text for marker in ENVIRONMENT_MARKERS):
            score += 0.08

        if any(marker in text for marker in FALLBACK_MARKERS):
            score += 0.08

        if any(marker in text for marker in STRICT_MARKERS):
            score += 0.06

        matched_anti = [item for item in anti_patterns if item in text]
        if matched_anti:
            score -= 0.14 * len(matched_anti)
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="env_error",
                    summary="Skill assumes repo details that do not hold in this environment.",
                    evidence=matched_anti[0],
                )
            )

        if any(marker in text for marker in ABSOLUTE_MARKERS):
            score -= 0.08
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="false_certainty",
                    summary="Skill presents unconditional directives without fallback.",
                )
            )

        word_count = len(text.split())
        max_words = int(task.metadata.get("max_skill_words", 220))
        if word_count > max_words:
            score -= min(0.25, (word_count - max_words) / max_words * 0.3)
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="context_noise",
                    summary="Skill is verbose enough to compete with task context.",
                )
            )

        path_like = len(re.findall(r"`[^`]+/[^`]+`|\b[a-zA-Z0-9_.-]+\.[a-z]{1,4}\b", text))
        if path_like >= 2:
            score -= 0.06 * min(3, path_like)
            events.append(
                TrajectoryEvent(
                    step_index=len(events) + 1,
                    kind="overfit",
                    summary="Skill overfits to file-level or command-level literals.",
                )
            )

        return max(0.0, min(1.0, score)), events
