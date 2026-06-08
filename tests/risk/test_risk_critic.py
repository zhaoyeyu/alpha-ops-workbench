from datetime import datetime

import pandas as pd

from alphaops.lifecycle.rules import LifecycleState
from alphaops.risk.critic import RiskCritic, RiskThresholds


def test_risk_critic_blocks_failed_thresholds_from_real_artifacts() -> None:
    critic = RiskCritic(
        RiskThresholds(
            max_drawdown=0.1,
            max_average_turnover=1.0,
            max_weight=0.4,
            min_quality_score=0.8,
            max_cost_ratio=0.01,
            max_stale_days=2,
        )
    )
    weights = pd.DataFrame(
        [
            {"timestamp": datetime(2026, 1, 1), "instrument_id": "eq:a", "target_weight": 0.55},
            {"timestamp": datetime(2026, 1, 1), "instrument_id": "eq:b", "target_weight": 0.45},
        ]
    )
    bars = pd.DataFrame(
        [{"timestamp": datetime(2026, 1, 1), "instrument_id": "eq:a", "close": 100.0}]
    )

    review = critic.review(
        alpha_id="alpha_risk_fixture",
        metrics={
            "max_drawdown": -0.2,
            "average_turnover": 1.2,
            "total_cost": 2_000,
            "initial_capital": 100_000,
        },
        weights=weights,
        market_bars=bars,
        quality_score=0.5,
        lifecycle_state=LifecycleState.REGISTRY_REVIEW,
        target_state=LifecycleState.ACTIVE,
        as_of=datetime(2026, 1, 10),
    )
    codes = {finding.code for finding in review.findings}

    assert review.blocks_promotion is True
    assert codes >= {
        "drawdown_limit",
        "turnover_high",
        "cost_sensitivity",
        "concentration_limit",
        "stale_data",
        "quality_score_low",
        "lifecycle_gate",
    }
    assert review.summary()["critical_count"] == 4


def test_risk_critic_allows_clean_approved_alpha() -> None:
    critic = RiskCritic()
    review = critic.review(
        alpha_id="alpha_clean",
        metrics={
            "max_drawdown": -0.05,
            "average_turnover": 0.2,
            "total_cost": 100,
            "initial_capital": 100_000,
        },
        weights=pd.DataFrame([{"target_weight": 0.2}]),
        market_bars=pd.DataFrame([{"timestamp": datetime(2026, 1, 5)}]),
        quality_score=0.95,
        lifecycle_state=LifecycleState.APPROVED,
        target_state=LifecycleState.ACTIVE,
        as_of=datetime(2026, 1, 6),
    )

    assert review.findings == []
    assert review.blocks_promotion is False
