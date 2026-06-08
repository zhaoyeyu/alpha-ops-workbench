"""Private CSV/Parquet ingestion adapter."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from alphaops.data.adapters.base import AdapterHealth, AdapterMetadata, DataAdapter
from alphaops.data.contracts import AssetClass, DataSourceKind, MARKET_BAR_COLUMNS, validate_market_bars_frame


DEFAULT_SCHEMA_MAP = {
    "ticker": "symbol",
    "trade_date": "timestamp",
    "open_px": "open",
    "high_px": "high",
    "low_px": "low",
    "close_px": "close",
    "adj_close_px": "adj_close",
    "vol": "volume",
}


class PrivateFileDataAdapter(DataAdapter):
    def __init__(
        self,
        file_path: str | Path,
        *,
        asset_class: AssetClass,
        schema_map: dict[str, str] | None = None,
        source_id: str = "private_file",
        exchange: str = "UNKNOWN",
        currency: str = "USD",
    ) -> None:
        self.file_path = Path(file_path)
        self.asset_class = asset_class
        self.schema_map = schema_map or DEFAULT_SCHEMA_MAP
        self.source_id = source_id
        self.exchange = exchange
        self.currency = currency
        self.metadata = AdapterMetadata(
            name="private_csv_parquet",
            asset_classes=[AssetClass.EQUITY, AssetClass.ETF, AssetClass.FUTURES],
            source_kind=DataSourceKind.PRIVATE_FILE,
            permission_scope="research_internal",
            description="Private Data Ingestion Adapter for local CSV/Parquet sources.",
        )

    def healthcheck(self) -> AdapterHealth:
        return AdapterHealth(
            ok=self.file_path.exists(),
            adapter=self.name,
            message="file exists" if self.file_path.exists() else "file not found",
            details={"path": str(self.file_path), "source_kind": self.metadata.source_kind.value},
        )

    def load_bars(
        self,
        instruments: Iterable[str],
        start: str,
        end: str,
        frequency: str,
    ) -> pd.DataFrame:
        frame = self._read_file().rename(columns=self.schema_map)
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
        symbols = {instrument.upper() for instrument in instruments}
        if symbols:
            frame = frame[frame["symbol"].isin(symbols)]

        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame[
            (frame["timestamp"] >= pd.Timestamp(start)) & (frame["timestamp"] <= pd.Timestamp(end))
        ]
        frame["asset_class"] = self.asset_class.value
        frame["frequency"] = frequency
        frame["currency"] = frame.get("currency", self.currency)
        frame["exchange"] = frame.get("exchange", self.exchange)
        frame["source_id"] = self.source_id
        frame["data_version"] = str(self.file_path.stat().st_mtime_ns)
        frame["ingested_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        frame["instrument_id"] = frame.apply(
            lambda row: f"{self.asset_class.value}:{str(row['symbol']).lower()}",
            axis=1,
        )
        if "contract_id" not in frame.columns:
            frame["contract_id"] = None
        if "adj_close" not in frame.columns:
            frame["adj_close"] = frame["close"]

        output = frame[list(MARKET_BAR_COLUMNS)].copy()
        missing = validate_market_bars_frame(output)
        if missing:
            raise ValueError("market bars missing required columns: " + ", ".join(missing))
        return output

    def _read_file(self) -> pd.DataFrame:
        suffix = self.file_path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(self.file_path)
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(self.file_path)
        raise ValueError(f"Unsupported private file type: {self.file_path.suffix}")

