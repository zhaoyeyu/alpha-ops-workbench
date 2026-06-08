from datetime import datetime, timedelta

import duckdb
import pandas as pd

from alphaops.data.quality import persist_quality_report, profile_market_bars
from alphaops.storage.duckdb import initialize_duckdb


def _bars() -> pd.DataFrame:
    base = datetime(2026, 1, 5, 9, 30)
    rows = []
    for index in range(4):
        rows.append(
            {
                "instrument_id": "equity:nvda",
                "symbol": "NVDA",
                "asset_class": "equity",
                "timestamp": base + timedelta(minutes=index),
                "frequency": "1m",
                "open": 100 + index,
                "high": 101 + index,
                "low": 99 + index,
                "close": 100.5 + index,
                "volume": 1000 + index,
                "currency": "USD",
                "exchange": "NASDAQ",
                "source_id": "internal_equity",
                "data_version": "fixture",
                "ingested_at": base,
                "adj_close": 100.5 + index,
                "contract_id": None,
            }
        )
    return pd.DataFrame(rows)


def test_quality_report_scores_clean_market_bars() -> None:
    report = profile_market_bars(_bars(), dataset_id="clean_equity")
    assert report.row_count == 4
    assert report.quality_score == 1.0
    assert report.issues == []


def test_quality_report_detects_ohlc_and_futures_contract_issues() -> None:
    frame = _bars()
    frame.loc[0, "high"] = 90
    frame.loc[1, "asset_class"] = "futures"
    frame.loc[1, "contract_id"] = None
    report = profile_market_bars(frame, dataset_id="bad_mixed")
    codes = {issue.code for issue in report.issues}
    assert "INVALID_OHLC_RANGE" in codes
    assert "FUTURES_CONTRACT_ID_MISSING" in codes
    assert report.quality_score < 1.0


def test_quality_report_persists_report_and_issues(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    frame = _bars()
    frame.loc[0, "high"] = 90
    report = profile_market_bars(frame, dataset_id="persisted_quality")
    persist_quality_report(str(db_path), report)

    with duckdb.connect(str(db_path)) as conn:
        report_count = conn.execute("SELECT COUNT(*) FROM quality_reports").fetchone()[0]
        issue_count = conn.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0]

    assert report_count == 1
    assert issue_count >= 1

