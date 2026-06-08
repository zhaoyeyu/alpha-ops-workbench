import json

import duckdb

from alphaops.agents.orchestrator import AgentOrchestrator, ToolStep, WorkflowPlan
from alphaops.storage.duckdb import initialize_duckdb
from alphaops.tools.registry import ToolRegistry
from alphaops.tools.schema import ToolCategory, ToolDefinition, ToolResult


def _registry_with_test_tools() -> ToolRegistry:
    registry = ToolRegistry()
    attempts = {"flaky": 0}

    def ok(payload):
        return ToolResult(
            tool_name="test.ok",
            output={"value": payload["value"]},
            audit={"deterministic": True, "service": "test", "agent_direct_metric_calculation": False},
        )

    def flaky(payload):
        attempts["flaky"] += 1
        if attempts["flaky"] == 1:
            raise ValueError("temporary failure")
        return ToolResult(
            tool_name="test.flaky",
            output={"attempts": attempts["flaky"]},
            audit={"deterministic": True, "service": "test", "agent_direct_metric_calculation": False},
        )

    def risk(payload):
        return ToolResult(
            tool_name="test.risk",
            output={"flags": [{"severity": "critical", "code": "drawdown", "message": "too much risk"}]},
            audit={"deterministic": True, "service": "test", "agent_direct_metric_calculation": False},
        )

    registry.register(
        ToolDefinition(name="test.ok", category=ToolCategory.EVALUATION, deterministic=True, description="ok"),
        ok,
    )
    registry.register(
        ToolDefinition(name="test.flaky", category=ToolCategory.EVALUATION, deterministic=True, description="flaky"),
        flaky,
    )
    registry.register(
        ToolDefinition(name="test.risk", category=ToolCategory.RISK, deterministic=True, description="risk"),
        risk,
    )
    return registry


def test_orchestrator_executes_tools_and_persists_trace(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    orchestrator = AgentOrchestrator(tool_registry=_registry_with_test_tools(), db_path=db_path)
    plan = WorkflowPlan(
        workflow_name="research_eval",
        steps=[ToolStep(step_id="s1", tool_name="test.ok", payload={"value": 42})],
    )

    state = orchestrator.run(plan, run_id="agent_run_ok")

    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute("SELECT state FROM agent_runs WHERE run_id = ?", ["agent_run_ok"]).fetchone()
    persisted = json.loads(row[0])
    assert state.status == "completed"
    assert state.trace[0].audit["agent_direct_metric_calculation"] is False
    assert persisted["trace"][0]["output"]["value"] == 42


def test_orchestrator_waits_for_human_approval() -> None:
    orchestrator = AgentOrchestrator(tool_registry=_registry_with_test_tools())
    plan = WorkflowPlan(
        workflow_name="approval_flow",
        steps=[ToolStep(step_id="approval_step", tool_name="test.ok", payload={"value": 1}, approval_required=True)],
    )

    state = orchestrator.run(plan, run_id="agent_run_wait")

    assert state.status == "waiting_approval"
    assert state.trace[0].attempts == 0


def test_orchestrator_retries_failed_tool() -> None:
    orchestrator = AgentOrchestrator(tool_registry=_registry_with_test_tools())
    plan = WorkflowPlan(
        workflow_name="retry_flow",
        steps=[ToolStep(step_id="flaky", tool_name="test.flaky", payload={}, max_retries=1)],
    )

    state = orchestrator.run(plan, run_id="agent_run_retry")

    assert state.status == "completed"
    assert state.trace[0].attempts == 2


def test_orchestrator_stops_on_critical_risk_checkpoint() -> None:
    orchestrator = AgentOrchestrator(tool_registry=_registry_with_test_tools())
    plan = WorkflowPlan(
        workflow_name="risk_flow",
        steps=[ToolStep(step_id="risk", tool_name="test.risk", payload={}, risk_checkpoint=True)],
    )

    state = orchestrator.run(plan, run_id="agent_run_risk")

    assert state.status == "risk_blocked"
    assert state.trace[0].status == "completed"
