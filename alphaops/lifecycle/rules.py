"""Lifecycle rules and review gates for Alpha Registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleState(StrEnum):
    REGISTRY_REVIEW = "registry_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RiskSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RiskFlag:
    severity: RiskSeverity
    code: str
    message: str


@dataclass(frozen=True)
class ReviewGateResult:
    allowed: bool
    reasons: tuple[str, ...]


ALLOWED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.REGISTRY_REVIEW: {LifecycleState.APPROVED, LifecycleState.REJECTED, LifecycleState.ARCHIVED},
    LifecycleState.APPROVED: {LifecycleState.ACTIVE, LifecycleState.ARCHIVED},
    LifecycleState.REJECTED: {LifecycleState.ARCHIVED},
    LifecycleState.ACTIVE: {LifecycleState.ARCHIVED},
    LifecycleState.ARCHIVED: set(),
}


def validate_transition(
    current: LifecycleState,
    target: LifecycleState,
    *,
    metrics: dict[str, float],
    risk_flags: list[RiskFlag],
) -> ReviewGateResult:
    reasons: list[str] = []
    if target not in ALLOWED_TRANSITIONS[current]:
        reasons.append(f"transition_not_allowed:{current.value}->{target.value}")
    if target in {LifecycleState.APPROVED, LifecycleState.ACTIVE}:
        if "rank_ic_mean" not in metrics and "ic_mean" not in metrics:
            reasons.append("missing_ic_metrics")
        if any(flag.severity == RiskSeverity.CRITICAL for flag in risk_flags):
            reasons.append("critical_risk_flag_present")
    if target == LifecycleState.ACTIVE and current != LifecycleState.APPROVED:
        reasons.append("active_requires_approved_state")
    return ReviewGateResult(allowed=not reasons, reasons=tuple(reasons))
