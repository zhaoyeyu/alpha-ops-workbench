"""Massive market data adapter for authenticated US stock and ETF bars."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from alphaops.data.adapters.base import AdapterHealth, AdapterMetadata, DataAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, MARKET_BAR_COLUMNS, validate_market_bars_frame


MASSIVE_API_KEY_ENV = "MASSIVE_API_KEY"
MASSIVE_API_BASE_URL_ENV = "MASSIVE_API_BASE_URL"


class MassiveMarketDataAdapter(DataAdapter):
    metadata = AdapterMetadata(
        name="massive_market_data",
        asset_classes=[AssetClass.EQUITY, AssetClass.ETF],
        source_kind=DataSourceKind.PUBLIC_ONLINE,
        permission_scope="research_public_authenticated",
        description="Authenticated Massive Market Data adapter for US Equity and ETF aggregate bars.",
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        asset_class: AssetClass = AssetClass.EQUITY,
        source_id: str = "massive_market_data",
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv(MASSIVE_API_KEY_ENV, "")
        self.base_url = (base_url or os.getenv(MASSIVE_API_BASE_URL_ENV, "https://api.massive.com")).rstrip("/")
        self.asset_class = asset_class
        self.source_id = source_id

    def healthcheck(self) -> AdapterHealth:
        configured = bool(self.api_key)
        return AdapterHealth(
            ok=configured,
            adapter=self.name,
            message="configured" if configured else f"missing {MASSIVE_API_KEY_ENV}",
            details={"base_url": self.base_url, "asset_classes": "equity,etf"},
        )

    def load_bars(
        self,
        instruments: Iterable[str],
        start: str,
        end: str,
        frequency: str,
    ) -> pd.DataFrame:
        self._require_api_key()
        symbols = [symbol.strip().upper() for symbol in instruments if symbol.strip()]
        if not symbols:
            raise ValueError("At least one symbol is required.")

        frames = [
            self._load_symbol_bars(symbol=symbol, start=start, end=end, frequency=frequency)
            for symbol in symbols
        ]
        output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=MARKET_BAR_COLUMNS)
        if output.empty:
            raise RuntimeError("Massive returned no market bar rows")
        return output

    def _load_symbol_bars(self, *, symbol: str, start: str, end: str, frequency: str) -> pd.DataFrame:
        timespan = _massive_timespan(frequency)
        path = (
            f"/v2/aggs/ticker/{quote(symbol)}/range/1/{timespan}/"
            f"{quote(str(pd.Timestamp(start).date()))}/{quote(str(pd.Timestamp(end).date()))}"
        )
        payload = self._fetch_json(
            path,
            {
                "adjusted": "true",
                "sort": "asc",
                "limit": "50000",
            },
        )
        if payload.get("status") not in {None, "OK", "DELAYED"}:
            raise RuntimeError(f"Massive request failed for {symbol}: {payload.get('status')}")
        rows = payload.get("results") or []
        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=MARKET_BAR_COLUMNS)
        return self._normalize_bars(symbol=symbol, frame=frame, frequency=frequency)

    def _fetch_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = dict(params)
        query["apiKey"] = self.api_key
        request = Request(f"{self.base_url}{path}?{urlencode(query)}", headers={"User-Agent": "alphaops-workbench"})
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _normalize_bars(self, *, symbol: str, frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized = pd.DataFrame(
            {
                "instrument_id": f"{self.asset_class.value}:{symbol.lower()}",
                "symbol": symbol,
                "asset_class": self.asset_class.value,
                "timestamp": pd.to_datetime(frame["t"], unit="ms").dt.tz_localize(None),
                "frequency": frequency,
                "open": frame["o"].astype(float),
                "high": frame["h"].astype(float),
                "low": frame["l"].astype(float),
                "close": frame["c"].astype(float),
                "adj_close": frame["c"].astype(float),
                "volume": frame.get("v", pd.Series([0] * len(frame))).astype(float),
                "currency": "USD",
                "exchange": "MASSIVE",
                "source_id": self.source_id,
                "data_version": datetime.now(timezone.utc).strftime("%Y%m%d"),
                "ingested_at": now,
                "contract_id": None,
            }
        )
        output = normalized[list(MARKET_BAR_COLUMNS)].copy()
        missing = validate_market_bars_frame(output)
        if missing:
            raise ValueError("market bars missing required columns: " + ", ".join(missing))
        return output

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(f"Set {MASSIVE_API_KEY_ENV} before using Massive market data.")


def _massive_timespan(frequency: str) -> str:
    mapping = {
        "1m": "minute",
        "1h": "hour",
        "1d": "day",
        "1wk": "week",
        "1mo": "month",
    }
    if frequency not in mapping:
        raise ValueError("Massive adapter supports 1m, 1h, 1d, 1wk, and 1mo bars")
    return mapping[frequency]
