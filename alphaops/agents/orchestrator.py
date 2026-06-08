"""Auditable agent workflow orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from alphaops.storage.duckdb import initialize_duckdb
from alphaops.tools.registry import ToolRegistry, default_tool_registry
from alphaops.tools.schema import ToolCallError, ToolDefinition, ToolResult


class ToolStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    tool_name: str
    payload: dict[str, Any]
    approval_required: bool = False
    risk_checkpoint: bool = False
    max_retries: int = Field(default=0, ge=0)


class WorkflowPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_name: str
    steps: list[ToolStep]


@dataclass
class ToolTrace:
    step_id: str
    tool_name: str
    status: str
    attempts: int
    output: dict[str, Any] | None = None
    error: str | None = None
    audit: dict[str, Any] | None = None


@dataclass
class AgentRunState:
    run_id: str
    workflow_name: str
    status: str
    trace: list[ToolTrace] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def as_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "workflow_name": self.workflow_name,
                "status": self.status,
                "trace": [
                    {
                        "step_id": item.step_id,
                        "tool_name": item.tool_name,
                        "status": item.status,
                        "attempts": item.attempts,
                        "output": item.output,
                        "error": item.error,
                        "audit": item.audit,
                    }
                    for item in self.trace
                ],
                "created_at": self.created_at.isoformat(),
            },
            default=str,
        )


class AgentOrchestrator:
    def __init__(self, *, tool_registry: ToolRegistry | None = None, db_path: str | Path | None = None) -> None:
        self.tool_registry = tool_registry or default_tool_registry()
        self.db_path = Path(db_path) if db_path else None

    def run(
        self,
        plan: WorkflowPlan,
        *,
        run_id: str,
        approvals: dict[str, bool] | None = None,
    ) -> AgentRunState:
        approvals = approvals or {}
        state = AgentRunState(run_id=run_id, workflow_name=plan.workflow_name, status="running")
        for step in plan.steps:
            if step.approval_required and not approvals.get(step.step_id, False):
                state.trace.append(
                    ToolTrace(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        status="waiting_approval",
                        attempts=0,
                        error="human approval required",
                    )
                )
                state.status = "waiting_approval"
                self.persist(state)
                return state
            trace = self._execute_step(step)
            state.trace.append(trace)
            if trace.status != "completed":
                state.status = "failed"
                self.persist(state)
                return state
            if step.risk_checkpoint and _has_critical_risk(trace.output or {}):
                state.status = "risk_blocked"
                self.persist(state)
                return state
        state.status = "completed"
        self.persist(state)
        return state

    def _execute_step(self, step: ToolStep) -> ToolTrace:
        attempts = 0
        last_error: str | None = None
        while attempts <= step.max_retries:
            attempts += 1
            try:
                result: ToolResult = self.tool_registry.call(step.tool_name, step.payload)
                _assert_tool_audit(step.tool_name, self.tool_registry.definition(step.tool_name), result)
                return ToolTrace(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    status="completed",
                    attempts=attempts,
                    output=result.output,
                    audit=result.audit,
                )
            except (ToolCallError, ValueError, KeyError) as exc:
                last_error = str(exc)
        return ToolTrace(
            step_id=step.step_id,
            tool_name=step.tool_name,
            status="failed",
            attempts=attempts,
            error=last_error,
        )

    def persist(self, state: AgentRunState) -> None:
        if self.db_path is None:
            return
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_runs VALUES (?, ?, ?, ?)",
                [state.run_id, state.workflow_name, state.as_json(), state.created_at],
            )


def run_workflow_from_dict(
    db_path: str | Path,
    *,
    run_id: str,
    plan_payload: dict[str, Any],
    approvals: dict[str, bool] | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AgentRunState:
    plan = WorkflowPlan(**plan_payload)
    orchestrator = AgentOrchestrator(tool_registry=tool_registry, db_path=initialize_duckdb(db_path))
    return orchestrator.run(plan, run_id=run_id, approvals=approvals)


def list_agent_runs(db_path: str | Path) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            """
            SELECT run_id, workflow_name, created_at, json_extract_string(state, '$.status') AS status
            FROM agent_runs
            ORDER BY created_at DESC
            """
        ).fetchdf()


def get_agent_run_state(db_path: str | Path, run_id: str) -> dict[str, Any]:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        row = conn.execute("SELECT state FROM agent_runs WHERE run_id = ?", [run_id]).fetchone()
    if row is None:
        raise KeyError(f"agent run not found: {run_id}")
    return json.loads(row[0])


def agent_trace_frame(db_path: str | Path, run_id: str) -> pd.DataFrame:
    state = get_agent_run_state(db_path, run_id)
    return pd.DataFrame(
        [
            {
                "step_id": item.get("step_id"),
                "tool_name": item.get("tool_name"),
                "status": item.get("status"),
                "attempts": item.get("attempts"),
                "error": item.get("error"),
                "output": json.dumps(item.get("output"), default=str, ensure_ascii=False),
                "audit": json.dumps(item.get("audit"), default=str, ensure_ascii=False),
            }
            for item in state.get("trace", [])
        ]
    )


def _assert_tool_audit(tool_name: str, definition: ToolDefinition, result: ToolResult) -> None:
    if result.tool_name != tool_name:
        raise ToolCallError("tool result name mismatch")
    if definition.deterministic and result.audit.get("agent_direct_metric_calculation") is not False:
        raise ToolCallError("deterministic tools must report no direct agent metric calculation")


def _has_critical_risk(output: dict[str, Any]) -> bool:
    for flag in output.get("flags", []):
        if str(flag.get("severity")) == "critical":
            return True
    return False
