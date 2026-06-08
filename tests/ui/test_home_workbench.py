from datetime import datetime

import duckdb
import pytest

from alphaops.storage.duckdb import initialize_duckdb
from apps.dashboard_streamlit.ui.state import REQUIRED_PAGES, HomeStateError, collect_home_state


def _seed_home_db(db_path) -> None:
    with duckdb.connect(str(db_path)) as conn:
        for asset_class, instrument_id, symbol in [
            ("equity", "eq:a", "A"),
            ("etf", "etf:qqq", "QQQ"),
            ("futures", "fut:mnq", "MNQ.C"),
        ]:
            conn.execute(
                """
                INSERT INTO market_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    instrument_id,
                    symbol,
                    asset_class,
                    datetime(2026, 1, 1),
                    "1d",
                    100.0,
                    101.0,
                    99.0,
                    100.5,
                    100.5,
                    1000.0,
                    "USD",
                    "TEST",
                    "fixture",
                    "test",
                    datetime(2026, 1, 1),
                    "mnq_202603" if asset_class == "futures" else None,
                ],
            )
        conn.execute(
            "INSERT INTO quality_reports VALUES (?, ?, ?, ?, ?, ?)",
            ["qr_home", "home_dataset", "equity", 3, 0.95, datetime(2026, 1, 1)],
        )
        conn.execute(
            "INSERT INTO alpha_registry VALUES (?, ?, ?, ?, ?)",
            ["alpha_home", "rank(close)", "0.1", "active", datetime(2026, 1, 1)],
        )
        conn.execute(
            "INSERT INTO alpha_risk_flags VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["risk_home", "alpha_home", "warning", "turnover_high", "High turnover", datetime(2026, 1, 1), None],
        )
        conn.execute(
            "INSERT INTO agent_runs VALUES (?, ?, ?, ?)",
            ["agent_home", "workflow", '{"status":"completed"}', datetime(2026, 1, 1)],
        )
        conn.execute(
            "INSERT INTO reports VALUES (?, ?, ?, ?, ?)",
            ["report_home", "alpha", "alpha_home", "reports/alpha_home.md", datetime(2026, 1, 1)],
        )
        conn.execute(
            "INSERT INTO evaluation_cases VALUES (?, ?, ?, ?)",
            ["eval_home", "schema_validity", "passed", datetime(2026, 1, 1)],
        )


def test_home_state_reads_real_service_summaries(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    _seed_home_db(db_path)

    state = collect_home_state(db_path)

    assert state["data_coverage"] == {"equity": 1, "etf": 1, "futures": 1}
    assert state["quality"]["average_score"] == pytest.approx(0.95)
    assert state["alpha_states"] == {"active": 1}
    assert state["risk_flags"] == {"warning": 1}
    assert state["agent_runs"] == {"completed": 1}
    assert state["report_count"] == 1
    assert state["evaluation_cases"] == {"passed": 1}
    assert "评估仪表盘" in REQUIRED_PAGES


def test_home_state_reports_missing_readiness_without_blocking_empty_services(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    state = collect_home_state(db_path)

    assert state["readiness"]["missing_market_coverage"] == ["equity", "etf", "futures"]
    assert state["readiness"]["alpha_registry_ready"] is False
    assert state["readiness"]["evaluation_ready"] is False
