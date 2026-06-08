from datetime import datetime

import duckdb
import pandas as pd

from alphaops.data.adapters import PrivateFileDataAdapter
from alphaops.data.contracts import AssetClass
from alphaops.data.ingest import ingest_bars


def test_private_file_ingestion_writes_bars_and_lineage(tmp_path) -> None:
    source = tmp_path / "private_equity.csv"
    pd.DataFrame(
        [
            {
                "ticker": "QQQ",
                "trade_date": datetime(2026, 1, 5, 9, 30),
                "open_px": 500.0,
                "high_px": 501.0,
                "low_px": 499.0,
                "close_px": 500.5,
                "adj_close_px": 500.5,
                "vol": 100000,
            }
        ]
    ).to_csv(source, index=False)

    db_path = tmp_path / "alphaops.duckdb"
    adapter = PrivateFileDataAdapter(source, asset_class=AssetClass.ETF, source_id="internal_etf")
    bars, lineage_id = ingest_bars(
        adapter=adapter,
        db_path=db_path,
        instruments=["QQQ"],
        start="2026-01-01",
        end="2026-01-31",
        frequency="1m",
        run_id="run_private_ingest",
    )

    with duckdb.connect(str(db_path)) as conn:
        market_count = conn.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0]
        lineage = conn.execute(
            "SELECT asset_class, source_kind, source_id FROM data_lineage WHERE lineage_id = ?",
            [lineage_id],
        ).fetchone()

    assert len(bars) == 1
    assert market_count == 1
    assert lineage == ("etf", "private_file", "internal_etf")

