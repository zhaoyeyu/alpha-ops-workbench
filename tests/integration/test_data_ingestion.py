from datetime import datetime

import duckdb
import pandas as pd

from alphaops.data.contracts import AssetClass
from alphaops.data.hub import ingest_private_file
from alphaops.storage.duckdb import initialize_duckdb


def test_data_hub_private_ingestion_writes_standardized_bars_and_lineage(tmp_path) -> None:
    source = tmp_path / "private_futures.csv"
    pd.DataFrame(
        [
            {
                "ticker": "MNQ",
                "trade_date": datetime(2026, 1, 2),
                "open_px": 20000,
                "high_px": 20100,
                "low_px": 19900,
                "close_px": 20050,
                "adj_close_px": 20050,
                "vol": 2000,
                "contract_id": "mnq_202603",
            }
        ]
    ).to_csv(source, index=False)
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    result = ingest_private_file(
        db_path=db_path,
        file_path=source,
        asset_class=AssetClass.FUTURES,
        instruments=["MNQ"],
        start="2026-01-01",
        end="2026-01-31",
        source_id="private_futures_test",
    )

    with duckdb.connect(str(db_path)) as conn:
        bar = conn.execute("SELECT asset_class, contract_id, source_id FROM market_bars").fetchone()
        lineage = conn.execute("SELECT source_kind, adapter_name FROM data_lineage").fetchone()

    assert result["rows"] == 1
    assert bar == ("futures", "mnq_202603", "private_futures_test")
    assert lineage == ("private_file", "private_csv_parquet")
