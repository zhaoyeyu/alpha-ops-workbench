from datetime import datetime

import pandas as pd
import pytest

from alphaops.data.adapters.alpaca_market_data import AlpacaMarketDataAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, validate_market_bars_frame


def test_alpaca_adapter_reports_missing_credentials_without_exposing_values(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    adapter = AlpacaMarketDataAdapter()
    health = adapter.healthcheck()

    assert health.ok is False
    assert adapter.metadata.asset_classes == [AssetClass.EQUITY]
    assert adapter.metadata.source_kind == DataSourceKind.PUBLIC_ONLINE
    assert "ALPACA_API_KEY_ID" in health.message


def test_alpaca_adapter_normalizes_bar_dataframe(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    adapter = AlpacaMarketDataAdapter()
    frame = pd.DataFrame(
        [
            {
                "symbol": "NVDA",
                "timestamp": datetime(2026, 1, 2, 14, 30),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
                "vwap": 100.4,
            }
        ]
    )

    bars = adapter._normalize_bars(frame, frequency="1d")

    assert validate_market_bars_frame(bars) == []
    assert bars.iloc[0]["instrument_id"] == "equity:nvda"
    assert bars.iloc[0]["source_id"] == "alpaca_market_data"


def test_alpaca_adapter_requires_credentials_for_remote_calls(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ALPACA_API_KEY_ID"):
        AlpacaMarketDataAdapter().load_bars(["NVDA"], "2026-01-01", "2026-01-02", "1d")
