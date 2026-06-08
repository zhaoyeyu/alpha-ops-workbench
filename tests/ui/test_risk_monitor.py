from datetime import datetime, timedelta

import duckdb

from alphaops.lifecycle.registry import AlphaRegistry
from alphaops.lifecycle.rules import LifecycleState
from alphaops.risk.critic import RiskThresholds, run_risk_review_from_storage
from alphaops.storage.duckdb import initialize_duckdb


def _seed_risk_context(db_path):
    now = datetime(2026, 1, 10)
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO backtest_runs VALUES (?, ?, ?, ?, ?, ?)",
            ["risk_run", "bt_contract", "alpha_risk_ui", 100_000.0, 100_500.0, now],
        )
        conn.executemany(
            "INSERT INTO metric_results VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("risk_run", "bt_contract", "max_drawdown", -0.25, "1d", now),
                ("risk_run", "bt_contract", "average_turnover", 1.8, "1d", now),
                ("risk_run", "bt_contract", "total_cost", 3000.0, "1d", now),
            ],
        )
        conn.executemany(
            "INSERT INTO backtest_weights VALUES (?, ?, ?, ?, ?)",
            [
                ("risk_run", now, "equity:a", "equity", 0.6),
                ("risk_run", now, "equity:b", "equity", 0.4),
            ],
        )
        conn.executemany(
            "INSERT INTO market_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("equity:a", "A", "equity", now - timedelta(days=10), "1d", 100, 100, 100, 100, 100, 1000, "USD", "NASDAQ", "risk_fixture", "fixture", now, None),
                ("equity:b", "B", "equity", now - timedelta(days=10), "1d", 100, 100, 100, 100, 100, 1000, "USD", "NASDAQ", "risk_fixture", "fixture", now, None),
            ],
        )
        conn.execute(
            "INSERT INTO quality_reports VALUES (?, ?, ?, ?, ?, ?)",
            ["qr_risk", "risk_fixture", "equity", 2, 0.4, now],
        )
    registry = AlphaRegistry(db_path)
    registry.register_for_review(
        {
            "alpha_id": "alpha_risk_ui",
            "formula": "rank(close)",
            "ast_version": "0.1",
            "metrics": {"rank_ic_mean": 0.1},
        }
    )


def test_risk_monitor_runs_review_from_persisted_backtest_context(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    _seed_risk_context(db_path)

    payload = run_risk_review_from_storage(
        db_path,
        run_id="risk_run",
        thresholds=RiskThresholds(max_drawdown=0.1, max_average_turnover=1.0, max_weight=0.4, min_quality_score=0.8, max_cost_ratio=0.01, max_stale_days=5),
        target_state=LifecycleState.ACTIVE,
        as_of=datetime(2026, 1, 20),
    )
    review = payload["review"]
    flags = AlphaRegistry(db_path).risk_flags_frame("alpha_risk_ui")

    assert review.blocks_promotion is True
    assert payload["persisted_flags"] == len(review.findings)
    assert {"drawdown_limit", "quality_score_low", "lifecycle_gate"}.issubset({finding.code for finding in review.findings})
    assert len(flags) == len(review.findings)
