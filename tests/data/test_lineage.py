import duckdb

from alphaops.data.contracts import AssetClass, DataSourceKind
from alphaops.data.lineage import create_lineage_record, persist_lineage, stable_hash
from alphaops.storage.duckdb import initialize_duckdb


def test_stable_hash_is_order_independent() -> None:
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})


def test_lineage_record_persists_asset_class_and_source_kind(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    record = create_lineage_record(
        source_kind=DataSourceKind.PRIVATE_FILE,
        source_id="internal_research_file",
        adapter_name="local_csv_parquet_private_adapter",
        schema_name="CanonicalMarketBar",
        input_payload={"path": "private.csv"},
        output_payload={"rows": 10},
        run_id="run_test",
        permission_scope="research_internal",
        asset_class=AssetClass.FUTURES,
    )
    persist_lineage(str(db_path), record)

    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT asset_class, source_kind, adapter_name FROM data_lineage WHERE lineage_id = ?",
            [record.lineage_id],
        ).fetchone()
    assert row == ("futures", "private_file", "local_csv_parquet_private_adapter")

