from datetime import datetime

import duckdb
import pandas as pd
import pytest

from alphaops.quant.evaluation import evaluate_alpha_ic
from alphaops.quant.ic import align_forward_returns, compute_ic_by_date, persist_ic_summary, summarize_ic
from alphaops.storage.duckdb import initialize_duckdb


def _market_bars() -> pd.DataFrame:
    rows = []
    prices = {
        "eq:a": [100.0, 110.0, 99.0],
        "eq:b": [100.0, 120.0, 96.0],
        "fut:c": [100.0, 130.0, 91.0],
    }
    for instrument_id, series in prices.items():
        for day, price in enumerate(series, start=1):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "asset_class": "futures" if instrument_id.startswith("fut") else "equity",
                    "timestamp": datetime(2026, 1, day),
                    "close": price,
                    "adj_close": price,
                }
            )
    return pd.DataFrame(rows)


def _factor_values() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "alpha_id": "alpha_ic_fixture",
                "instrument_id": "eq:a",
                "timestamp": datetime(2026, 1, 1),
                "factor_value": 1.0,
            },
            {
                "alpha_id": "alpha_ic_fixture",
                "instrument_id": "eq:b",
                "timestamp": datetime(2026, 1, 1),
                "factor_value": 2.0,
            },
            {
                "alpha_id": "alpha_ic_fixture",
                "instrument_id": "fut:c",
                "timestamp": datetime(2026, 1, 1),
                "factor_value": 3.0,
            },
            {
                "alpha_id": "alpha_ic_fixture",
                "instrument_id": "eq:a",
                "timestamp": datetime(2026, 1, 2),
                "factor_value": 1.0,
            },
            {
                "alpha_id": "alpha_ic_fixture",
                "instrument_id": "eq:b",
                "timestamp": datetime(2026, 1, 2),
                "factor_value": 2.0,
            },
            {
                "alpha_id": "alpha_ic_fixture",
                "instrument_id": "fut:c",
                "timestamp": datetime(2026, 1, 2),
                "factor_value": 3.0,
            },
        ]
    )


def test_forward_return_alignment_uses_future_prices() -> None:
    aligned = align_forward_returns(_factor_values(), _market_bars(), horizon=1)
    first_day = aligned[aligned["timestamp"] == pd.Timestamp("2026-01-01")]
    returns = dict(zip(first_day["instrument_id"], first_day["forward_return"], strict=True))

    assert len(aligned) == 6
    assert returns == pytest.approx({"eq:a": 0.10, "eq:b": 0.20, "fut:c": 0.30})


def test_ic_and_rankic_match_fixture_expectations() -> None:
    aligned = align_forward_returns(_factor_values(), _market_bars(), horizon=1)
    by_date = compute_ic_by_date(aligned)
    by_timestamp = {row.timestamp.date().isoformat(): row for row in by_date.itertuples(index=False)}

    assert by_timestamp["2026-01-01"].ic == pytest.approx(1.0)
    assert by_timestamp["2026-01-01"].rank_ic == pytest.approx(1.0)
    assert by_timestamp["2026-01-02"].ic == pytest.approx(-1.0)
    assert by_timestamp["2026-01-02"].rank_ic == pytest.approx(-1.0)
    assert by_timestamp["2026-01-01"].observation_count == 3


def test_grouped_ic_returns_by_asset_class_rows() -> None:
    aligned = align_forward_returns(_factor_values(), _market_bars(), horizon=1)
    by_group = compute_ic_by_date(aligned, group_column="asset_class")

    assert set(by_group["group"]) == {"equity", "futures"}
    futures_rows = by_group[by_group["group"] == "futures"]
    assert futures_rows["ic"].isna().all()
    assert futures_rows["observation_count"].tolist() == [1, 1]


def test_ic_summary_and_evaluation_payloads_are_structured() -> None:
    result = evaluate_alpha_ic(
        _factor_values(),
        _market_bars(),
        alpha_id="alpha_ic_fixture",
        horizon=1,
    )
    metric_map = dict(zip(result.summary["metric_name"], result.summary["metric_value"], strict=True))
    registry_payload = result.for_alpha_registry()
    report_payload = result.for_report()

    assert metric_map["ic_mean"] == pytest.approx(0.0)
    assert metric_map["rank_ic_mean"] == pytest.approx(0.0)
    assert metric_map["period_count"] == 2.0
    assert registry_payload["periods"] == 2
    assert report_payload["by_date_rows"] == 2


def test_ic_summary_persists_to_metric_results(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    aligned = align_forward_returns(_factor_values(), _market_bars(), horizon=1)
    by_date = compute_ic_by_date(aligned)
    summary = summarize_ic(by_date, alpha_id="alpha_ic_fixture")

    inserted = persist_ic_summary(db_path, summary, run_id="run_ic_fixture")

    with duckdb.connect(str(db_path)) as conn:
        metric_count = conn.execute(
            "SELECT COUNT(*) FROM metric_results WHERE run_id = ?",
            ["run_ic_fixture"],
        ).fetchone()[0]
        rank_metric = conn.execute(
            "SELECT metric_value FROM metric_results WHERE metric_name = ?",
            ["rank_ic_mean"],
        ).fetchone()[0]

    assert inserted == 7
    assert metric_count == 7
    assert rank_metric == pytest.approx(0.0)
