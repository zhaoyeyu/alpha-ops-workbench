from alphaops.agents.orchestrator import agent_trace_frame, get_agent_run_state, list_agent_runs, run_workflow_from_dict
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

    registry.register(ToolDefinition(name="test.ok", category=ToolCategory.EVALUATION, deterministic=True, description="ok"), ok)
    registry.register(ToolDefinition(name="test.flaky", category=ToolCategory.EVALUATION, deterministic=True, description="flaky"), flaky)
    return registry


def test_agent_console_services_run_and_read_persisted_trace(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    state = run_workflow_from_dict(
        db_path,
        run_id="agent_console_ui",
        plan_payload={
            "workflow_name": "ui_console_flow",
            "steps": [
                {"step_id": "ok", "tool_name": "test.ok", "payload": {"value": 7}},
                {"step_id": "flaky", "tool_name": "test.flaky", "payload": {}, "max_retries": 1},
            ],
        },
        tool_registry=_registry_with_test_tools(),
    )
    runs = list_agent_runs(db_path)
    detail = get_agent_run_state(db_path, "agent_console_ui")
    trace = agent_trace_frame(db_path, "agent_console_ui")

    assert state.status == "completed"
    assert runs.iloc[0]["run_id"] == "agent_console_ui"
    assert detail["trace"][0]["output"]["value"] == 7
    assert list(trace["status"]) == ["completed", "completed"]
    assert trace.iloc[1]["attempts"] == 2


def test_agent_console_services_show_waiting_approval(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    state = run_workflow_from_dict(
        db_path,
        run_id="agent_console_approval",
        plan_payload={
            "workflow_name": "approval_flow",
            "steps": [{"step_id": "review", "tool_name": "test.ok", "payload": {"value": 1}, "approval_required": True}],
        },
        tool_registry=_registry_with_test_tools(),
    )
    trace = agent_trace_frame(db_path, "agent_console_approval")

    assert state.status == "waiting_approval"
    assert trace.iloc[0]["status"] == "waiting_approval"
    assert "human approval required" in trace.iloc[0]["error"]
