from datetime import datetime

import duckdb
import pandas as pd

from alphaops.data.contracts import AssetClass
from alphaops.quant.universe import UniverseDefinition, build_universe_members, persist_universe_members
from alphaops.storage.duckdb import initialize_duckdb


def test_dynamic_universe_selects_liquid_multi_asset_members(tmp_path) -> None:
    instruments = pd.DataFrame(
        [
            {
                "instrument_id": "eq:nvda",
                "symbol": "NVDA",
                "asset_class": "equity",
                "exchange": "NASDAQ",
                "root_symbol": None,
            },
            {
                "instrument_id": "eq:thin",
                "symbol": "THIN",
                "asset_class": "equity",
                "exchange": "NASDAQ",
                "root_symbol": None,
            },
            {
                "instrument_id": "fut:mnq_cont",
                "symbol": "MNQ.C",
                "asset_class": "futures",
                "exchange": "CME",
                "root_symbol": "MNQ",
            },
        ]
    )
    bars = pd.DataFrame(
        [
            {
                "instrument_id": "eq:nvda",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 2),
                "volume": 90_000_000,
            },
            {
                "instrument_id": "eq:nvda",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 3),
                "volume": 100_000_000,
            },
            {
                "instrument_id": "eq:thin",
                "asset_class": "equity",
                "timestamp": datetime(2026, 1, 3),
                "volume": 100,
            },
            {
                "instrument_id": "fut:mnq_cont",
                "asset_class": "futures",
                "timestamp": datetime(2026, 1, 2),
                "volume": 800_000,
            },
            {
                "instrument_id": "fut:mnq_cont",
                "asset_class": "futures",
                "timestamp": datetime(2026, 1, 3),
                "volume": 850_000,
            },
        ]
    )
    definition = UniverseDefinition(
        universe_id="short_horizon_liquid",
        name="Short horizon liquid multi-asset universe",
        asset_classes=[AssetClass.EQUITY, AssetClass.FUTURES],
        min_average_volume=500_000,
        min_observations=2,
    )

    members = build_universe_members(instruments, bars, definition, "2026-01-03")

    assert {member.instrument_id for member in members} == {"eq:nvda", "fut:mnq_cont"}
    assert {member.asset_class for member in members} == {AssetClass.EQUITY, AssetClass.FUTURES}
    assert all("dynamic_liquidity_filter" in member.inclusion_reason for member in members)


def test_universe_members_persist_to_duckdb(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    members = build_universe_members(
        pd.DataFrame(
            [
                {
                    "instrument_id": "etf:qqq",
                    "symbol": "QQQ",
                    "asset_class": "etf",
                    "exchange": "NASDAQ",
                }
            ]
        ),
        pd.DataFrame(
            [
                {
                    "instrument_id": "etf:qqq",
                    "asset_class": "etf",
                    "timestamp": datetime(2026, 1, 2),
                    "volume": 50_000_000,
                }
            ]
        ),
        UniverseDefinition(
            universe_id="private_ingestion_etf_universe",
            name="ETF private ingestion universe",
            asset_classes=[AssetClass.ETF],
            min_average_volume=10_000,
        ),
        "2026-01-02",
    )

    inserted = persist_universe_members(db_path, members)

    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT universe_id, instrument_id, asset_class FROM universe_members"
        ).fetchone()
    assert inserted == 1
    assert row == ("private_ingestion_etf_universe", "etf:qqq", "etf")

