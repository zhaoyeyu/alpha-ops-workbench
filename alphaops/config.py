"""Configuration for AlphaOps Workbench."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


def _load_local_environment() -> None:
    explicit_path = os.getenv("ALPHAOPS_ENV_FILE")
    if explicit_path:
        load_dotenv(dotenv_path=Path(explicit_path).expanduser(), override=False)
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


_load_local_environment()


@dataclass(frozen=True)
class AppConfig:
    env: str
    api_host: str
    api_port: int
    streamlit_port: int


@dataclass(frozen=True)
class PathConfig:
    storage_dir: Path
    duckdb_path: Path


@dataclass(frozen=True)
class LlmGatewayConfig:
    provider: str
    base_url: str
    primary_key_env: str
    secondary_key_env: str
    has_primary_key: bool
    has_secondary_key: bool


@dataclass(frozen=True)
class AlphaOpsConfig:
    app: AppConfig
    paths: PathConfig
    llm_gateway: LlmGatewayConfig


def load_config() -> AlphaOpsConfig:
    storage_dir = Path(os.getenv("ALPHAOPS_STORAGE_DIR", "storage"))
    duckdb_path = storage_dir / "warehouse" / "alphaops.duckdb"
    return AlphaOpsConfig(
        app=AppConfig(
            env=os.getenv("ALPHAOPS_ENV", "local"),
            api_host=os.getenv("ALPHAOPS_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("ALPHAOPS_API_PORT", "8000")),
            streamlit_port=int(os.getenv("ALPHAOPS_STREAMLIT_PORT", "8501")),
        ),
        paths=PathConfig(storage_dir=storage_dir, duckdb_path=duckdb_path),
        llm_gateway=LlmGatewayConfig(
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            primary_key_env="OPENROUTER_API_KEY_PRIMARY",
            secondary_key_env="OPENROUTER_API_KEY_SECONDARY",
            has_primary_key=bool(os.getenv("OPENROUTER_API_KEY_PRIMARY")),
            has_secondary_key=bool(os.getenv("OPENROUTER_API_KEY_SECONDARY")),
        ),
    )
