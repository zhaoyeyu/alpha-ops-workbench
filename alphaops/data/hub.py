"""Data Hub service functions for adapters, storage, and lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from alphaops.data.adapters import AlpacaMarketDataAdapter, MassiveMarketDataAdapter, PrivateFileDataAdapter, YFinanceEquityAdapter
from alphaops.data.contracts import AssetClass
from alphaops.data.ingest import ingest_bars
from alphaops.storage.duckdb import initialize_duckdb


def adapter_inventory(private_file_path: str | Path | None = None) -> list[dict[str, Any]]:
    adapters = [YFinanceEquityAdapter(), MassiveMarketDataAdapter(), AlpacaMarketDataAdapter()]
    if private_file_path:
        adapters.append(PrivateFileDataAdapter(private_file_path, asset_class=AssetClass.EQUITY))
    rows = []
    for adapter in adapters:
        health = adapter.healthcheck()
        rows.append(
            {
                "name": adapter.name,
                "source_kind": adapter.metadata.source_kind.value,
                "asset_classes": [asset.value for asset in adapter.metadata.asset_classes],
                "permission_scope": adapter.metadata.permission_scope,
                "ok": health.ok,
                "message": health.message,
            }
        )
    return rows


def ingest_private_file(
    *,
    db_path: str | Path,
    file_path: str | Path,
    asset_class: AssetClass,
    instruments: list[str],
    start: str,
    end: str,
    frequency: str = "1d",
    source_id: str = "private_file",
) -> dict[str, Any]:
    adapter = PrivateFileDataAdapter(file_path, asset_class=asset_class, source_id=source_id)
    bars, lineage_id = ingest_bars(
        adapter=adapter,
        db_path=db_path,
        instruments=instruments,
        start=start,
        end=end,
        frequency=frequency,
    )
    return {"rows": len(bars), "lineage_id": lineage_id, "sample": bars.head(20).to_dict(orient="records")}


def ingest_public_equity_yfinance(
    *,
    db_path: str | Path,
    symbols: list[str],
    start: str,
    end: str,
    frequency: str = "1d",
) -> dict[str, Any]:
    """Load public US equity bars through yfinance and persist them into DuckDB."""
    cleaned_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not cleaned_symbols:
        raise ValueError("At least one equity symbol is required.")

    adapter = YFinanceEquityAdapter()
    bars, lineage_id = ingest_bars(
        adapter=adapter,
        db_path=db_path,
        instruments=cleaned_symbols,
        start=start,
        end=end,
        frequency=frequency,
        run_id="ui_yfinance_ingest",
    )
    return {"rows": len(bars), "lineage_id": lineage_id, "sample": bars.head(20).to_dict(orient="records")}


def ingest_public_equity_alpaca(
    *,
    db_path: str | Path,
    symbols: list[str],
    start: str,
    end: str,
    frequency: str = "1d",
    feed: str = "iex",
) -> dict[str, Any]:
    """Load authenticated Alpaca US equity bars and persist them into DuckDB."""
    cleaned_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not cleaned_symbols:
        raise ValueError("At least one equity symbol is required.")

    adapter = AlpacaMarketDataAdapter(feed=feed)
    bars, lineage_id = ingest_bars(
        adapter=adapter,
        db_path=db_path,
        instruments=cleaned_symbols,
        start=start,
        end=end,
        frequency=frequency,
        run_id="ui_alpaca_ingest",
    )
    return {"rows": len(bars), "lineage_id": lineage_id, "sample": bars.head(20).to_dict(orient="records")}


def ingest_public_market_massive(
    *,
    db_path: str | Path,
    symbols: list[str],
    start: str,
    end: str,
    frequency: str = "1d",
    asset_class: AssetClass = AssetClass.EQUITY,
) -> dict[str, Any]:
    """Load authenticated Massive US equity/ETF bars and persist them into DuckDB."""
    cleaned_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not cleaned_symbols:
        raise ValueError("At least one symbol is required.")
    if asset_class not in {AssetClass.EQUITY, AssetClass.ETF}:
        raise ValueError("Massive public market ingestion currently supports equity and ETF.")

    adapter = MassiveMarketDataAdapter(asset_class=asset_class)
    bars, lineage_id = ingest_bars(
        adapter=adapter,
        db_path=db_path,
        instruments=cleaned_symbols,
        start=start,
        end=end,
        frequency=frequency,
        run_id="ui_massive_ingest",
    )
    return {"rows": len(bars), "lineage_id": lineage_id, "sample": bars.head(20).to_dict(orient="records")}


def ingest_demo_market_data(db_path: str | Path) -> dict[str, Any]:
    """Persist clearly marked sample bars so a new local install can exercise the workflow.

    These rows are for learning the product flow only. They are not research data and are
    intentionally labeled with source_id=demo_sample_data.
    """
    target = initialize_duckdb(db_path)
    base = pd.Timestamp("2026-01-02")
    instruments = {
        "equity:nvda": ("NVDA", AssetClass.EQUITY.value, [100.0, 103.5, 102.2, 106.8, 109.4], 12_000_000.0, None),
        "equity:msft": ("MSFT", AssetClass.EQUITY.value, [100.0, 101.2, 102.8, 102.1, 104.7], 8_000_000.0, None),
        "etf:qqq": ("QQQ", AssetClass.ETF.value, [100.0, 101.0, 101.8, 102.6, 103.3], 18_000_000.0, None),
        "futures:mnq": ("MNQ", AssetClass.FUTURES.value, [100.0, 102.4, 101.5, 104.2, 105.6], 45_000.0, "mnq_202603"),
    }
    rows = []
    for instrument_id, (symbol, asset_class, prices, volume, contract_id) in instruments.items():
        for offset, close in enumerate(prices):
            timestamp = base + pd.Timedelta(days=offset)
            rows.append(
                (
                    instrument_id,
                    symbol,
                    asset_class,
                    timestamp.to_pydatetime(),
                    "1d",
                    close * 0.995,
                    close * 1.01,
                    close * 0.99,
                    close,
                    close,
                    volume,
                    "USD",
                    "CME" if asset_class == AssetClass.FUTURES.value else "NASDAQ",
                    "demo_sample_data",
                    "sample_v1",
                    pd.Timestamp.utcnow().to_pydatetime().replace(tzinfo=None),
                    contract_id,
                )
            )
    with duckdb.connect(str(target)) as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO market_bars
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return {"rows": len(rows), "source_id": "demo_sample_data", "sample": sample_market_bars(target, limit=20)}


def storage_summary(db_path: str | Path) -> dict[str, Any]:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        coverage = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT asset_class, COUNT(*) FROM market_bars GROUP BY asset_class ORDER BY asset_class"
            ).fetchall()
        }
        instruments = int(conn.execute("SELECT COUNT(DISTINCT instrument_id) FROM market_bars").fetchone()[0])
        rows = int(conn.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0])
        latest = conn.execute("SELECT MAX(timestamp) FROM market_bars").fetchone()[0]
    return {"rows": rows, "instruments": instruments, "coverage": coverage, "latest_timestamp": latest}


def lineage_summary(db_path: str | Path) -> list[dict[str, Any]]:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        rows = conn.execute(
            """
            SELECT lineage_id, asset_class, source_kind, source_id, adapter_name, created_at
            FROM data_lineage
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [
        {
            "lineage_id": row[0],
            "asset_class": row[1],
            "source_kind": row[2],
            "source_id": row[3],
            "adapter_name": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


def sample_market_bars(db_path: str | Path, *, limit: int = 50) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            """
            SELECT instrument_id, symbol, asset_class, timestamp, frequency, close, volume, source_id
            FROM market_bars
            ORDER BY timestamp DESC, instrument_id
            LIMIT ?
            """,
            [limit],
        ).fetchdf()
