from datetime import datetime, timedelta

import duckdb
import pandas as pd

from alphaops.data.contracts import AssetClass
from alphaops.data.quality import (
    profile_stored_market_bars,
    quality_issue_table,
    quality_overview,
    quality_score_history,
    symbol_quality_drilldown,
)
from alphaops.storage.duckdb import initialize_duckdb


def _insert_bars(db_path):
    base = datetime(2026, 1, 5, 9, 30)
    rows = []
    for index, close in enumerate([100.0, 100.0, 100.0, 450.0]):
        rows.append(
            (
                "equity:nvda",
                "NVDA",
                "equity",
                base + timedelta(minutes=index),
                "1m",
                100 + index,
                101 + index,
                99 + index,
                close,
                close,
                1000 + index,
                "USD",
                "NASDAQ",
                "private_equity_quality",
                "fixture",
                base,
                None,
            )
        )
    with duckdb.connect(str(db_path)) as conn:
        conn.executemany(
            "INSERT INTO market_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "INSERT INTO data_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "lineage_quality_1",
                "equity",
                "private_file",
                "private_equity_quality",
                "private_csv_parquet",
                "CanonicalMarketBar",
                "schema_hash",
                "input_hash",
                "output_hash",
                "run_quality",
                base,
                "local_private_file",
            ],
        )


def test_data_quality_page_services_profile_persisted_market_bars(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    _insert_bars(db_path)

    report = profile_stored_market_bars(
        db_path,
        asset_class=AssetClass.EQUITY,
        symbol="NVDA",
        source_id="private_equity_quality",
    )
    overview = quality_overview(db_path)
    issues = quality_issue_table(db_path)
    history = quality_score_history(db_path, asset_class=AssetClass.EQUITY)
    drilldown = symbol_quality_drilldown(db_path, "equity:nvda")

    assert report.row_count == 4
    assert report.quality_score < 1.0
    assert {"LARGE_RETURN_JUMP", "STALE_CLOSE"}.issubset({issue.code for issue in report.issues})
    assert overview["report_count"] == 1
    assert overview["issue_count"] >= 2
    assert overview["recent_reports"].iloc[0]["lineage_id"] == "lineage_quality_1"
    assert set(issues["code"]).issuperset({"LARGE_RETURN_JUMP", "STALE_CLOSE"})
    assert history.iloc[0]["dataset_id"] == "private_equity_quality"
    assert not drilldown["coverage"].empty
    assert "equity:nvda" in pd.concat([issues["instrument_id"].dropna(), drilldown["coverage"]["instrument_id"]]).tolist()
