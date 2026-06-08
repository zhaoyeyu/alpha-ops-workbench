from pathlib import Path

from alphaops.agents.orchestrator import agent_trace_frame, run_workflow_from_dict
from alphaops.cli import main
from alphaops.data.adapters.admin import connector_admin_snapshot
from alphaops.storage.duckdb import initialize_duckdb
from alphaops.tools.registry import ToolRegistry
from alphaops.tools.schema import ToolCategory, ToolDefinition, ToolResult
from apps.api_fastapi.main import status


ROOT = Path(__file__).resolve().parents[2]
PAGE_FILES = [
    ROOT / "apps" / "dashboard_streamlit" / "Home.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "01_Data_Hub.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "02_Data_Quality.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "03_Synthetic_Index_Lab.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "04_Alpha_Factory.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "05_Backtest_Lab.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "06_Alpha_Registry.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "07_Risk_Monitor.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "08_Agent_Console.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "09_Report_Center.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "10_Connector_Admin.py",
    ROOT / "apps" / "dashboard_streamlit" / "pages" / "11_Evaluation_Dashboard.py",
]


def _smoke_registry() -> ToolRegistry:
    registry = ToolRegistry()

    def ok(payload):
        return ToolResult(
            tool_name="smoke.ok",
            output={"value": payload["value"]},
            audit={"deterministic": True, "service": "smoke", "agent_direct_metric_calculation": False},
        )

    registry.register(ToolDefinition(name="smoke.ok", category=ToolCategory.EVALUATION, deterministic=True, description="smoke"), ok)
    return registry


def test_full_product_smoke_covers_core_paths_pages_api_agents_and_connectors(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ALPHAOPS_STORAGE_DIR", str(tmp_path / "storage"))

    assert main(["smoke"]) == 0
    output = capsys.readouterr().out
    for marker in [
        "smoke=passed",
        "quality_score=",
        "alpha_id=",
        "backtest_rows=",
        "synthetic_rows=",
        "risk_findings=",
        "evaluation_status=passed",
    ]:
        assert marker in output

    for page in PAGE_FILES:
        assert page.exists(), page
    home_source = PAGE_FILES[0].read_text(encoding="utf-8")
    assert "st.navigation" in home_source
    assert "数据中心" in home_source
    assert "风险监控" in home_source

    api_status = status()
    assert api_status["primary_ui"] == "streamlit"
    assert "market_bars" in api_status["tables"]

    agent_db = initialize_duckdb(tmp_path / "agent.duckdb")
    state = run_workflow_from_dict(
        agent_db,
        run_id="full_smoke_agent",
        plan_payload={"workflow_name": "full_smoke", "steps": [{"step_id": "ok", "tool_name": "smoke.ok", "payload": {"value": 1}}]},
        tool_registry=_smoke_registry(),
    )
    trace = agent_trace_frame(agent_db, "full_smoke_agent")
    assert state.status == "completed"
    assert trace.iloc[0]["tool_name"] == "smoke.ok"

    connector_snapshot = connector_admin_snapshot()
    assert all(item["raw_secret_exposed"] is False for item in connector_snapshot["credential_slots"])
    assert all(item["display_value"] in {"<set>", "<missing>"} for item in connector_snapshot["credential_slots"])
    assert any(item["connector"] == "openrouter" for item in connector_snapshot["credential_slots"])
