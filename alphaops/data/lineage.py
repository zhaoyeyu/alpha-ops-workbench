"""Lineage utilities for data and research artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

import duckdb

from alphaops.data.contracts import AssetClass, DataLineageRecord, DataSourceKind


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_lineage_record(
    *,
    source_kind: DataSourceKind,
    source_id: str,
    adapter_name: str,
    schema_name: str,
    input_payload: Any,
    output_payload: Any,
    run_id: str,
    permission_scope: str,
    asset_class: AssetClass | None = None,
) -> DataLineageRecord:
    schema_payload = {"schema_name": schema_name, "version": "0.1"}
    return DataLineageRecord(
        lineage_id=f"lin_{uuid4().hex}",
        asset_class=asset_class,
        source_kind=source_kind,
        source_id=source_id,
        adapter_name=adapter_name,
        schema_name=schema_name,
        schema_hash=stable_hash(schema_payload),
        input_hash=stable_hash(input_payload),
        output_hash=stable_hash(output_payload),
        run_id=run_id,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        permission_scope=permission_scope,
    )


def persist_lineage(db_path: str, record: DataLineageRecord) -> None:
    with duckdb.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO data_lineage (
                lineage_id, asset_class, source_kind, source_id, adapter_name,
                schema_name, schema_hash, input_hash, output_hash, run_id,
                created_at, permission_scope
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.lineage_id,
                record.asset_class.value if record.asset_class else None,
                record.source_kind.value,
                record.source_id,
                record.adapter_name,
                record.schema_name,
                record.schema_hash,
                record.input_hash,
                record.output_hash,
                record.run_id,
                record.created_at,
                record.permission_scope,
            ],
        )

