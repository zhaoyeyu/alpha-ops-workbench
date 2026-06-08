from datetime import datetime

import pandas as pd

from alphaops.data.contracts import AssetClass
from alphaops.data.hub import (
    adapter_inventory,
    ingest_demo_market_data,
    ingest_private_file,
    ingest_public_equity_alpaca,
    ingest_public_market_massive,
    lineage_summary,
    sample_market_bars,
    storage_summary,
)
from alphaops.storage.duckdb import initialize_duckdb


def _private_csv(tmp_path):
    path = tmp_path / "private_bars.csv"
    pd.DataFrame(
        [
            {
                "ticker": "QQQ",
                "trade_date": datetime(2026, 1, 2),
                "open_px": 100,
                "high_px": 101,
                "low_px": 99,
                "close_px": 100.5,
                "adj_close_px": 100.5,
                "vol": 1000,
            }
        ]
    ).to_csv(path, index=False)
    return path


def test_data_hub_inventory_and_storage_summary(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    source = _private_csv(tmp_path)

    inventory = adapter_inventory(source)
    result = ingest_private_file(
        db_path=db_path,
        file_path=source,
        asset_class=AssetClass.ETF,
        instruments=["QQQ"],
        start="2026-01-01",
        end="2026-01-31",
        source_id="private_ui_test",
    )
    summary = storage_summary(db_path)
    lineage = lineage_summary(db_path)
    sample = sample_market_bars(db_path)

    assert {item["name"] for item in inventory} == {
        "yfinance_equity",
        "massive_market_data",
        "alpaca_market_data",
        "private_csv_parquet",
    }
    assert result["rows"] == 1
    assert summary["coverage"] == {"etf": 1}
    assert lineage[0]["lineage_id"] == result["lineage_id"]
    assert sample.iloc[0]["instrument_id"] == "etf:qqq"


def test_data_hub_sample_data_populates_all_required_asset_classes(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    result = ingest_demo_market_data(db_path)
    summary = storage_summary(db_path)

    assert result["rows"] == 20
    assert result["source_id"] == "demo_sample_data"
    assert set(summary["coverage"]) == {"equity", "etf", "futures"}


def test_data_hub_alpaca_ingestion_writes_standardized_bars(tmp_path, monkeypatch) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    def fake_load_bars(self, instruments, start, end, frequency):
        return pd.DataFrame(
            [
                {
                    "instrument_id": "equity:nvda",
                    "symbol": "NVDA",
                    "asset_class": "equity",
                    "timestamp": datetime(2026, 1, 2),
                    "frequency": frequency,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "adj_close": 100.5,
                    "volume": 1000.0,
                    "currency": "USD",
                    "exchange": "ALPACA",
                    "source_id": "alpaca_market_data",
                    "data_version": "test",
                    "ingested_at": datetime(2026, 1, 2),
                    "contract_id": None,
                }
            ]
        )

    monkeypatch.setattr("alphaops.data.adapters.alpaca_market_data.AlpacaMarketDataAdapter.load_bars", fake_load_bars)

    result = ingest_public_equity_alpaca(
        db_path=db_path,
        symbols=["NVDA"],
        start="2026-01-01",
        end="2026-01-03",
        frequency="1d",
    )

    assert result["rows"] == 1
    assert storage_summary(db_path)["coverage"] == {"equity": 1}
    assert lineage_summary(db_path)[0]["adapter_name"] == "alpaca_market_data"


def test_data_hub_massive_ingestion_writes_standardized_bars(tmp_path, monkeypatch) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    def fake_load_bars(self, instruments, start, end, frequency):
        return pd.DataFrame(
            [
                {
                    "instrument_id": "etf:qqq",
                    "symbol": "QQQ",
                    "asset_class": "etf",
                    "timestamp": datetime(2026, 1, 2),
                    "frequency": frequency,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "adj_close": 100.5,
                    "volume": 1000.0,
                    "currency": "USD",
                    "exchange": "MASSIVE",
                    "source_id": "massive_market_data",
                    "data_version": "test",
                    "ingested_at": datetime(2026, 1, 2),
                    "contract_id": None,
                }
            ]
        )

    monkeypatch.setattr("alphaops.data.adapters.massive_market_data.MassiveMarketDataAdapter.load_bars", fake_load_bars)

    result = ingest_public_market_massive(
        db_path=db_path,
        symbols=["QQQ"],
        start="2026-01-01",
        end="2026-01-03",
        frequency="1d",
        asset_class=AssetClass.ETF,
    )

    assert result["rows"] == 1
    assert storage_summary(db_path)["coverage"] == {"etf": 1}
    assert lineage_summary(db_path)[0]["adapter_name"] == "massive_market_data"
