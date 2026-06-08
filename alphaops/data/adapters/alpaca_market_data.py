"""Alpaca market data adapter for US equity bars and live trade subscriptions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
import os
from typing import Any

import pandas as pd

from alphaops.data.adapters.base import AdapterHealth, AdapterMetadata, DataAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, MARKET_BAR_COLUMNS, validate_market_bars_frame


ALPACA_KEY_ENV = "ALPACA_API_KEY_ID"
ALPACA_SECRET_ENV = "ALPACA_API_SECRET_KEY"


class AlpacaMarketDataAdapter(DataAdapter):
    metadata = AdapterMetadata(
        name="alpaca_market_data",
        asset_classes=[AssetClass.EQUITY],
        source_kind=DataSourceKind.PUBLIC_ONLINE,
        permission_scope="research_public_authenticated",
        description="Authenticated Alpaca Market Data adapter for US Equity bars and live trade streams.",
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        feed: str = "iex",
        source_id: str = "alpaca_market_data",
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv(ALPACA_KEY_ENV, "")
        self.secret_key = secret_key if secret_key is not None else os.getenv(ALPACA_SECRET_ENV, "")
        self.feed = os.getenv("ALPACA_DATA_FEED", feed)
        self.source_id = source_id

    def healthcheck(self) -> AdapterHealth:
        configured = bool(self.api_key and self.secret_key)
        return AdapterHealth(
            ok=configured,
            adapter=self.name,
            message="configured" if configured else f"missing {ALPACA_KEY_ENV}/{ALPACA_SECRET_ENV}",
            details={"feed": self.feed, "asset_class": AssetClass.EQUITY.value},
        )

    def load_bars(
        self,
        instruments: Iterable[str],
        start: str,
        end: str,
        frequency: str,
    ) -> pd.DataFrame:
        self._require_credentials()
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest

        client = StockHistoricalDataClient(self.api_key, self.secret_key)
        request = StockBarsRequest(
            symbol_or_symbols=[symbol.strip().upper() for symbol in instruments if symbol.strip()],
            start=pd.Timestamp(start).to_pydatetime(),
            end=pd.Timestamp(end).to_pydatetime(),
            timeframe=_alpaca_timeframe(frequency),
            feed=DataFeed(self.feed),
        )
        response = client.get_stock_bars(request)
        frame = _bars_response_to_frame(response)
        if frame.empty:
            raise RuntimeError("Alpaca returned no equity rows")
        return self._normalize_bars(frame, frequency=frequency)

    def create_trade_stream(self):
        """Create an authenticated Alpaca StockDataStream for callers that need live trades."""
        self._require_credentials()
        from alpaca.data.enums import DataFeed
        from alpaca.data.live import StockDataStream

        return StockDataStream(self.api_key, self.secret_key, feed=DataFeed(self.feed))

    def subscribe_trades(
        self,
        symbols: Iterable[str],
        handler: Callable[[Any], Awaitable[None]],
    ):
        """Return a configured StockDataStream after subscribing a trade handler.

        The caller owns `stream.run()` so UI code does not block the Streamlit process.
        """
        stream = self.create_trade_stream()
        stream.subscribe_trades(handler, *[symbol.strip().upper() for symbol in symbols if symbol.strip()])
        return stream

    def _require_credentials(self) -> None:
        if not self.api_key or not self.secret_key:
            raise RuntimeError(f"Set {ALPACA_KEY_ENV} and {ALPACA_SECRET_ENV} before using Alpaca market data.")

    def _normalize_bars(self, frame: pd.DataFrame, *, frequency: str) -> pd.DataFrame:
        normalized = frame.reset_index() if isinstance(frame.index, pd.MultiIndex) else frame.copy()
        rename_map = {
            "symbol": "symbol",
            "timestamp": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "vwap": "adj_close",
        }
        normalized = normalized.rename(columns=rename_map)
        if "symbol" not in normalized.columns and "level_0" in normalized.columns:
            normalized = normalized.rename(columns={"level_0": "symbol"})
        if "timestamp" not in normalized.columns and "level_1" in normalized.columns:
            normalized = normalized.rename(columns={"level_1": "timestamp"})

        normalized["symbol"] = normalized["symbol"].astype(str).str.upper()
        normalized["asset_class"] = AssetClass.EQUITY.value
        normalized["frequency"] = frequency
        normalized["currency"] = "USD"
        normalized["exchange"] = "ALPACA"
        normalized["source_id"] = self.source_id
        normalized["data_version"] = datetime.now(timezone.utc).strftime("%Y%m%d")
        normalized["ingested_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized["instrument_id"] = normalized["symbol"].map(lambda symbol: f"equity:{symbol.lower()}")
        normalized["contract_id"] = None
        if "adj_close" not in normalized.columns or normalized["adj_close"].isna().all():
            normalized["adj_close"] = normalized["close"]

        output = normalized[list(MARKET_BAR_COLUMNS)].copy()
        output["timestamp"] = pd.to_datetime(output["timestamp"]).dt.tz_localize(None)
        missing = validate_market_bars_frame(output)
        if missing:
            raise ValueError("market bars missing required columns: " + ", ".join(missing))
        return output


def _bars_response_to_frame(response: Any) -> pd.DataFrame:
    if hasattr(response, "df"):
        return response.df.copy()
    if isinstance(response, pd.DataFrame):
        return response.copy()
    raise TypeError("Unsupported Alpaca bars response type")


def _alpaca_timeframe(frequency: str):
    from alpaca.data.timeframe import TimeFrame

    mapping = {
        "1m": TimeFrame.Minute,
        "1h": TimeFrame.Hour,
        "1d": TimeFrame.Day,
        "1wk": TimeFrame.Week,
        "1mo": TimeFrame.Month,
    }
    if frequency not in mapping:
        raise ValueError("Alpaca adapter supports 1m, 1h, 1d, 1wk, and 1mo bars")
    return mapping[frequency]
