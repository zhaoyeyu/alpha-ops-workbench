"""DuckDB initialization and inspection."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import duckdb

from alphaops.config import load_config


def initialize_duckdb(db_path: str | Path | None = None) -> Path:
    config = load_config()
    target = Path(db_path) if db_path else config.paths.duckdb_path
    target.parent.mkdir(parents=True, exist_ok=True)
    schema = files("alphaops.storage").joinpath("schema.sql").read_text(encoding="utf-8")
    with duckdb.connect(str(target)) as conn:
        conn.execute(schema)
    return target


def list_tables(db_path: str | Path | None = None) -> list[str]:
    config = load_config()
    target = Path(db_path) if db_path else config.paths.duckdb_path
    with duckdb.connect(str(target)) as conn:
        rows = conn.execute("SHOW TABLES").fetchall()
    return [row[0] for row in rows]

