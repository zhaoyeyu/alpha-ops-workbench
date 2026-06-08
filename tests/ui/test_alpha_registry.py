import pytest

from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState, RiskFlag, RiskSeverity
from alphaops.storage.duckdb import initialize_duckdb


def _payload() -> dict[str, object]:
    return {
        "alpha_id": "alpha_ui_registry",
        "formula": "rank(close)",
        "ast_version": "0.1",
        "lifecycle_state": "registry_review",
        "metrics": {"rank_ic_mean": 0.09, "ic_mean": 0.08},
    }


def test_alpha_registry_page_services_list_detail_and_transition(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    registry = AlphaRegistry(db_path)
    card = registry.register_for_review(_payload())
    registry.add_risk_flag(card.alpha_id, RiskFlag(RiskSeverity.WARNING, "turnover", "High turnover"))

    cards = registry.cards_frame(query="rank")
    metrics = registry.metric_history(card.alpha_id)
    flags = registry.risk_flags_frame(card.alpha_id)
    events_before = registry.events_frame(card.alpha_id)
    approved = registry.transition(card.alpha_id, LifecycleState.APPROVED, actor="tester", reason="reviewed")
    active = registry.transition(
        card.alpha_id,
        LifecycleState.ACTIVE,
        actor="tester",
        reason="activate",
        report_link="reports/alpha_ui_registry.md",
    )
    events_after = registry.events_frame(card.alpha_id)
    reports = registry.reports_frame(card.alpha_id)

    assert cards.iloc[0]["alpha_id"] == card.alpha_id
    assert set(metrics["metric_name"]) == {"rank_ic_mean", "ic_mean"}
    assert flags.iloc[0]["code"] == "turnover"
    assert events_before.iloc[0]["to_state"] == "registry_review"
    assert approved.lifecycle_state == LifecycleState.APPROVED
    assert active.lifecycle_state == LifecycleState.ACTIVE
    assert list(events_after["to_state"]) == ["registry_review", "approved", "active"]
    assert reports.iloc[0]["path"] == "reports/alpha_ui_registry.md"


def test_alpha_registry_page_services_preserve_transition_guards(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    registry = AlphaRegistry(db_path)
    card = registry.register_for_review(_payload())
    registry.add_risk_flag(card.alpha_id, RiskFlag(RiskSeverity.CRITICAL, "leakage", "Potential leakage"))

    with pytest.raises(ValueError):
        registry.transition(card.alpha_id, LifecycleState.APPROVED, actor="tester", reason="blocked")
