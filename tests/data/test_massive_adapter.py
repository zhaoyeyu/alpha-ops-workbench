from datetime import datetime

import pandas as pd
import pytest

from alphaops.data.adapters.massive_market_data import MassiveMarketDataAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, validate_market_bars_frame


def test_massive_adapter_reports_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    adapter = MassiveMarketDataAdapter()
    health = adapter.healthcheck()

    assert health.ok is False
    assert adapter.metadata.asset_classes == [AssetClass.EQUITY, AssetClass.ETF]
    assert adapter.metadata.source_kind == DataSourceKind.PUBLIC_ONLINE
    assert "MASSIVE_API_KEY" in health.message


def test_massive_adapter_normalizes_aggregate_rows(monkeypatch) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "test_key")
    adapter = MassiveMarketDataAdapter(asset_class=AssetClass.ETF)
    frame = pd.DataFrame(
        [
            {
                "t": int(datetime(2026, 1, 2, 14, 30).timestamp() * 1000),
                "o": 100.0,
                "h": 101.0,
                "l": 99.0,
                "c": 100.5,
                "v": 1000.0,
            }
        ]
    )

    bars = adapter._normalize_bars(symbol="QQQ", frame=frame, frequency="1d")

    assert validate_market_bars_frame(bars) == []
    assert bars.iloc[0]["instrument_id"] == "etf:qqq"
    assert bars.iloc[0]["source_id"] == "massive_market_data"


def test_massive_adapter_uses_results_payload(monkeypatch) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "test_key")
    adapter = MassiveMarketDataAdapter()

    def fake_fetch_json(path, params):
        assert "/v2/aggs/ticker/NVDA/range/1/day/" in path
        assert params["adjusted"] == "true"
        return {
            "status": "OK",
            "results": [
                {"t": int(datetime(2026, 1, 2).timestamp() * 1000), "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000}
            ],
        }

    monkeypatch.setattr(adapter, "_fetch_json", fake_fetch_json)

    bars = adapter.load_bars(["NVDA"], "2026-01-01", "2026-01-03", "1d")

    assert len(bars) == 1
    assert bars.iloc[0]["symbol"] == "NVDA"


def test_massive_adapter_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MASSIVE_API_KEY"):
        MassiveMarketDataAdapter().load_bars(["NVDA"], "2026-01-01", "2026-01-02", "1d")
