from __future__ import annotations

from fastapi import FastAPI

from alphaops.config import load_config
from alphaops.storage.duckdb import initialize_duckdb, list_tables


app = FastAPI(title="AlphaOps Workbench API", version="0.1.0")


@app.get("/status")
def status() -> dict[str, object]:
    config = load_config()
    db_path = initialize_duckdb(config.paths.duckdb_path)
    return {
        "app": "alphaops_workbench",
        "primary_ui": "streamlit",
        "duckdb_path": str(db_path),
        "tables": sorted(list_tables(db_path)),
        "openrouter_gateway": {
            "provider": config.llm_gateway.provider,
            "primary_key_env": config.llm_gateway.primary_key_env,
            "secondary_key_env": config.llm_gateway.secondary_key_env,
            "primary_configured": config.llm_gateway.has_primary_key,
            "secondary_configured": config.llm_gateway.has_secondary_key,
        },
    }
