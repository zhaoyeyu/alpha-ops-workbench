import duckdb
import pytest

from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState, RiskFlag, RiskSeverity
from alphaops.storage.duckdb import initialize_duckdb


def _payload() -> dict[str, object]:
    return {
        "alpha_id": "alpha_registry_fixture",
        "formula": "rank(close)",
        "ast_version": "0.1",
        "lifecycle_state": "registry_review",
        "dependencies": ["close"],
        "operator_names": ["rank"],
        "score": 0.08,
        "metrics": {"rank_ic_mean": 0.08, "ic_mean": 0.07},
        "duplicate_of": None,
    }


def test_registry_registers_review_card_metrics_and_event(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    registry = AlphaRegistry(db_path)

    card = registry.register_for_review(_payload())
    events = registry.events(card.alpha_id)

    assert card.lifecycle_state == LifecycleState.REGISTRY_REVIEW
    assert card.metrics["rank_ic_mean"] == pytest.approx(0.08)
    assert events[0]["to_state"] == "registry_review"
    with duckdb.connect(str(db_path)) as conn:
        metric_count = conn.execute("SELECT COUNT(*) FROM alpha_metric_snapshots").fetchone()[0]
    assert metric_count == 2


def test_registry_blocks_approval_when_critical_risk_exists(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    registry = AlphaRegistry(db_path)
    card = registry.register_for_review(_payload())

    registry.add_risk_flag(
        card.alpha_id,
        RiskFlag(RiskSeverity.CRITICAL, "leakage", "Potential lookahead leakage"),
    )

    with pytest.raises(ValueError) as error:
        registry.transition(card.alpha_id, LifecycleState.APPROVED, actor="reviewer", reason="manual_review")

    assert "critical_risk_flag_present" in str(error.value)


def test_registry_approval_activation_and_report_link_are_auditable(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    registry = AlphaRegistry(db_path)
    card = registry.register_for_review(_payload())

    approved = registry.transition(card.alpha_id, LifecycleState.APPROVED, actor="reviewer", reason="passed_review")
    active = registry.transition(
        card.alpha_id,
        LifecycleState.ACTIVE,
        actor="reviewer",
        reason="activate_for_monitoring",
        report_link="reports/alpha_registry_fixture.md",
    )
    events = registry.events(card.alpha_id)

    assert approved.lifecycle_state == LifecycleState.APPROVED
    assert active.lifecycle_state == LifecycleState.ACTIVE
    assert active.report_links == ["reports/alpha_registry_fixture.md"]
    assert [event["to_state"] for event in events] == ["registry_review", "approved", "active"]
