"""Adapter ingestion into DuckDB with lineage."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from alphaops.data.adapters.base import DataAdapter
from alphaops.data.contracts import AssetClass, MARKET_BAR_COLUMNS
from alphaops.data.lineage import create_lineage_record, persist_lineage
from alphaops.storage.duckdb import initialize_duckdb


def ingest_bars(
    *,
    adapter: DataAdapter,
    db_path: str | Path,
    instruments: Iterable[str],
    start: str,
    end: str,
    frequency: str,
    run_id: str | None = None,
) -> tuple[pd.DataFrame, str]:
    target = initialize_duckdb(db_path)
    run = run_id or f"run_{uuid4().hex}"
    bars = adapter.load_bars(instruments, start, end, frequency)
    _write_market_bars(target, bars)

    asset_class = _single_asset_class(bars)
    lineage = create_lineage_record(
        source_kind=adapter.metadata.source_kind,
        source_id=bars["source_id"].iloc[0],
        adapter_name=adapter.name,
        schema_name="CanonicalMarketBar",
        input_payload={"instruments": list(instruments), "start": start, "end": end, "frequency": frequency},
        output_payload={"rows": len(bars), "columns": list(bars.columns)},
        run_id=run,
        permission_scope=adapter.metadata.permission_scope,
        asset_class=asset_class,
    )
    persist_lineage(str(target), lineage)
    return bars, lineage.lineage_id


def _write_market_bars(db_path: Path, bars: pd.DataFrame) -> None:
    ordered = bars[list(MARKET_BAR_COLUMNS)].copy()
    with duckdb.connect(str(db_path)) as conn:
        conn.register("incoming_market_bars", ordered)
        conn.execute(
            """
            INSERT OR REPLACE INTO market_bars
            SELECT
                instrument_id, symbol, asset_class, timestamp, frequency,
                open, high, low, close, adj_close, volume, currency, exchange,
                source_id, data_version, ingested_at, contract_id
            FROM incoming_market_bars
            """
        )


def _single_asset_class(bars: pd.DataFrame) -> AssetClass | None:
    values = bars["asset_class"].dropna().astype(str).unique()
    if len(values) != 1:
        return None
    return AssetClass(values[0])

