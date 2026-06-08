"""Tool schemas, audit envelopes, and OpenRouter gateway guards."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolCategory(StrEnum):
    DATA = "data"
    QUANT = "quant"
    REGISTRY = "registry"
    RISK = "risk"
    REPORT = "report"
    EVALUATION = "evaluation"
    LLM_GATEWAY = "llm_gateway"


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: ToolCategory
    deterministic: bool
    description: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    output: dict[str, Any]
    audit: dict[str, Any]


class OpenRouterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: str
    model: str
    messages: list[dict[str, str]]

    @field_validator("workflow")
    @classmethod
    def workflow_allowed(cls, value: str) -> str:
        allowed = {"planning", "formula_generation", "report_generation", "research_workflow"}
        if value not in allowed:
            raise ValueError("OpenRouter workflow must be planning/formula_generation/report_generation/research_workflow")
        return value


class ToolCallError(ValueError):
    pass


def openrouter_financial_data_guard(payload: dict[str, Any]) -> None:
    requested = str(payload.get("requested_use", "")).lower()
    blocked_terms = {"market_data", "financial_data", "price_source", "行情", "数据源"}
    if any(term in requested for term in blocked_terms):
        raise ToolCallError("OpenRouter is an LLM gateway, not a financial market data source")
