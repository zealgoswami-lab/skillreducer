from __future__ import annotations

from dataclasses import dataclass

from skillrevise.core.models import ExecutionTrace, UtilityBreakdown


@dataclass
class UtilityWeights:
    alpha: float = 1.0
    beta: float = 0.35
    gamma: float = 0.35
    lam: float = 0.75


UTILITY_PRESETS = {
    "full": UtilityWeights(),
    "success-only": UtilityWeights(alpha=1.0, beta=0.0, gamma=0.0, lam=0.0),
    "efficiency-only": UtilityWeights(alpha=0.0, beta=1.0, gamma=0.0, lam=0.0),
    "transfer-only": UtilityWeights(alpha=0.0, beta=0.0, gamma=1.0, lam=0.0),
    "no-interference": UtilityWeights(alpha=1.0, beta=0.35, gamma=0.35, lam=0.0),
}


def utility_weights_for_preset(name: str) -> UtilityWeights:
    try:
        preset = UTILITY_PRESETS[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(UTILITY_PRESETS))
        raise ValueError(f"Unknown utility preset '{name}'. Allowed presets: {allowed}") from exc
    return UtilityWeights(alpha=preset.alpha, beta=preset.beta, gamma=preset.gamma, lam=preset.lam)


def _relative_reduction(baseline: int | float, current: int | float) -> float:
    if baseline <= 0:
        return 0.0
    return (baseline - current) / baseline


def trace_outcome_score(trace: ExecutionTrace) -> float | None:
    """Return the continuous benchmark reward when available, otherwise binary success."""
    if "reward" not in trace.metadata:
        return float(trace.success)

    reward = trace.metadata.get("reward")
    if reward is None:
        return None
    if isinstance(reward, (int, float)):
        return float(reward)
    if isinstance(reward, str):
        if not reward.strip():
            return None
        try:
            return float(reward)
        except ValueError:
            return None
    return None


def compute_utility(
    no_skill: ExecutionTrace,
    with_skill: ExecutionTrace,
    *,
    transfer_gain: float = 0.0,
    interference_cost: float | None = None,
    weights: UtilityWeights | None = None,
) -> UtilityBreakdown:
    weights = weights or UtilityWeights()
    no_skill_score = trace_outcome_score(no_skill)
    with_skill_score = trace_outcome_score(with_skill)
    if no_skill_score is None or with_skill_score is None:
        return UtilityBreakdown(
            success_gain=0.0,
            token_gain=0.0,
            tool_gain=0.0,
            step_gain=0.0,
            latency_gain=0.0,
            efficiency_gain=0.0,
            transfer_gain=0.0,
            interference_cost=0.0,
            overall_score=0.0,
            notes=["Utility skipped because at least one run has no valid benchmark reward."],
        )

    success_gain = with_skill_score - no_skill_score
    token_gain = _relative_reduction(no_skill.tokens, with_skill.tokens)
    tool_gain = _relative_reduction(no_skill.tool_calls, with_skill.tool_calls)
    step_gain = _relative_reduction(no_skill.steps, with_skill.steps)
    latency_gain = _relative_reduction(no_skill.latency_seconds, with_skill.latency_seconds)
    efficiency_gain = (token_gain + tool_gain + step_gain + latency_gain) / 4.0
    interference = interference_cost
    if interference is None:
        interference = 1.0 if no_skill.success and not with_skill.success else 0.0
    overall = (
        weights.alpha * success_gain
        + weights.beta * efficiency_gain
        + weights.gamma * transfer_gain
        - weights.lam * interference
    )

    notes: list[str] = []
    if success_gain > 0:
        notes.append("Skill improves same-task success.")
    elif success_gain < 0:
        notes.append("Skill introduces same-task regression.")
    if efficiency_gain > 0:
        notes.append("Skill reduces execution cost.")
    elif efficiency_gain < 0:
        notes.append("Skill increases execution cost.")
    if transfer_gain > 0:
        notes.append("Skill transfers to held-out sibling tasks.")
    if interference > 0:
        notes.append("Skill shows measurable interference.")

    return UtilityBreakdown(
        success_gain=success_gain,
        token_gain=token_gain,
        tool_gain=tool_gain,
        step_gain=step_gain,
        latency_gain=latency_gain,
        efficiency_gain=efficiency_gain,
        transfer_gain=transfer_gain,
        interference_cost=interference,
        overall_score=overall,
        notes=notes,
    )
