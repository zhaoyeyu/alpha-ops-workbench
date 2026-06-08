"""yfinance Equity adapter.

yfinance is intentionally scoped as one Equity adapter, not the system core.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

import pandas as pd

from alphaops.data.adapters.base import AdapterHealth, AdapterMetadata, DataAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, MARKET_BAR_COLUMNS, validate_market_bars_frame


class YFinanceEquityAdapter(DataAdapter):
    metadata = AdapterMetadata(
        name="yfinance_equity",
        asset_classes=[AssetClass.EQUITY],
        source_kind=DataSourceKind.PUBLIC_ONLINE,
        permission_scope="research_public",
        description="Public yfinance adapter scoped to Equity bars.",
    )

    def healthcheck(self) -> AdapterHealth:
        return AdapterHealth(
            ok=True,
            adapter=self.name,
            message="configured; network availability is verified during load_bars",
            details={"asset_class": AssetClass.EQUITY.value},
        )

    def load_bars(
        self,
        instruments: Iterable[str],
        start: str,
        end: str,
        frequency: str,
    ) -> pd.DataFrame:
        import yfinance as yf

        if frequency not in {"1d", "1wk", "1mo"}:
            raise ValueError("YFinanceEquityAdapter supports 1d, 1wk, and 1mo bars")

        frames = []
        for symbol in instruments:
            data = yf.download(symbol, start=start, end=end, interval=frequency, progress=False)
            if data.empty:
                continue
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [column[0] for column in data.columns]
            normalized = data.reset_index().rename(
                columns={
                    "Date": "timestamp",
                    "Datetime": "timestamp",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adj_close",
                    "Volume": "volume",
                }
            )
            normalized["symbol"] = symbol.upper()
            frames.append(normalized)
        if not frames:
            raise RuntimeError("yfinance returned no equity rows")

        frame = pd.concat(frames, ignore_index=True)
        frame["asset_class"] = AssetClass.EQUITY.value
        frame["frequency"] = frequency
        frame["currency"] = "USD"
        frame["exchange"] = "UNKNOWN"
        frame["source_id"] = self.name
        frame["data_version"] = datetime.now(timezone.utc).strftime("%Y%m%d")
        frame["ingested_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        frame["instrument_id"] = frame["symbol"].map(lambda symbol: f"equity:{symbol.lower()}")
        frame["contract_id"] = None
        if "adj_close" not in frame.columns:
            frame["adj_close"] = frame["close"]
        output = frame[list(MARKET_BAR_COLUMNS)].copy()
        missing = validate_market_bars_frame(output)
        if missing:
            raise ValueError("market bars missing required columns: " + ", ".join(missing))
        return output

