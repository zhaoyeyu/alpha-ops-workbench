from datetime import datetime

import pandas as pd

from alphaops.data.adapters import FuturesDataAdapter, PrivateFileDataAdapter, YFinanceEquityAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, validate_market_bars_frame


def test_yfinance_is_equity_adapter_only() -> None:
    adapter = YFinanceEquityAdapter()
    assert adapter.metadata.asset_classes == [AssetClass.EQUITY]
    assert adapter.metadata.source_kind == DataSourceKind.PUBLIC_ONLINE
    assert "core" not in adapter.metadata.description.lower()


def test_futures_adapter_family_is_independent() -> None:
    assert issubclass(FuturesDataAdapter, object)
    assert "load_contracts" in FuturesDataAdapter.__abstractmethods__
    assert "load_continuous_map" in FuturesDataAdapter.__abstractmethods__


def test_private_csv_adapter_loads_equity_contract(tmp_path) -> None:
    source = tmp_path / "private_equity.csv"
    pd.DataFrame(
        [
            {
                "ticker": "NVDA",
                "trade_date": datetime(2026, 1, 5, 9, 30),
                "open_px": 100.0,
                "high_px": 101.0,
                "low_px": 99.0,
                "close_px": 100.5,
                "adj_close_px": 100.5,
                "vol": 10000,
            }
        ]
    ).to_csv(source, index=False)

    adapter = PrivateFileDataAdapter(source, asset_class=AssetClass.EQUITY, source_id="internal_equity")
    bars = adapter.load_bars(["NVDA"], "2026-01-01", "2026-01-31", "1m")
    assert validate_market_bars_frame(bars) == []
    assert bars.iloc[0]["asset_class"] == "equity"
    assert bars.iloc[0]["source_id"] == "internal_equity"


def test_private_csv_adapter_loads_futures_contract(tmp_path) -> None:
    source = tmp_path / "private_futures.csv"
    pd.DataFrame(
        [
            {
                "ticker": "MNQU6",
                "trade_date": datetime(2026, 9, 1, 18, 0),
                "open_px": 20000.0,
                "high_px": 20020.0,
                "low_px": 19990.0,
                "close_px": 20010.0,
                "vol": 42,
                "contract_id": "cme_mnq_202609",
            }
        ]
    ).to_csv(source, index=False)

    adapter = PrivateFileDataAdapter(source, asset_class=AssetClass.FUTURES, source_id="internal_futures")
    bars = adapter.load_bars(["MNQU6"], "2026-09-01", "2026-09-02", "1m")
    assert validate_market_bars_frame(bars) == []
    assert bars.iloc[0]["asset_class"] == "futures"
    assert bars.iloc[0]["contract_id"] == "cme_mnq_202609"

