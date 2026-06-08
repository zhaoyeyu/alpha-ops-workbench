from alphaops.lifecycle.rules import LifecycleState, RiskFlag, RiskSeverity, validate_transition


def test_lifecycle_rules_allow_review_to_approved_with_metrics() -> None:
    result = validate_transition(
        LifecycleState.REGISTRY_REVIEW,
        LifecycleState.APPROVED,
        metrics={"rank_ic_mean": 0.05},
        risk_flags=[],
    )

    assert result.allowed is True
    assert result.reasons == ()


def test_lifecycle_rules_block_critical_risk_and_invalid_transition() -> None:
    result = validate_transition(
        LifecycleState.REGISTRY_REVIEW,
        LifecycleState.ACTIVE,
        metrics={"rank_ic_mean": 0.05},
        risk_flags=[RiskFlag(RiskSeverity.CRITICAL, "leakage", "Potential lookahead leakage")],
    )

    assert result.allowed is False
    assert "transition_not_allowed:registry_review->active" in result.reasons
    assert "critical_risk_flag_present" in result.reasons
    assert "active_requires_approved_state" in result.reasons


def test_lifecycle_rules_require_ic_metrics_for_approval() -> None:
    result = validate_transition(
        LifecycleState.REGISTRY_REVIEW,
        LifecycleState.APPROVED,
        metrics={},
        risk_flags=[],
    )

    assert result.allowed is False
    assert result.reasons == ("missing_ic_metrics",)

