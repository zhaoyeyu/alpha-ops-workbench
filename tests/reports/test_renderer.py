from datetime import datetime

import pandas as pd

from alphaops.agents.orchestrator import AgentRunState, ToolTrace
from alphaops.data.contracts import AssetClass, BacktestContract
from alphaops.lifecycle.rules import LifecycleState
from alphaops.quant.evaluation import AlphaEvaluationResult
from alphaops.reports.renderer import (
    render_agent_run_report,
    render_alpha_review_report,
    render_backtest_report,
    render_evaluation_summary_report,
    render_report,
    render_synthetic_index_report,
)
from alphaops.risk.critic import RiskReview
from alphaops.synthetic.engine import SyntheticIndexConfig, SyntheticIndexResult


class _Card:
    alpha_id = "alpha_report"
    formula = "rank(close)"
    lifecycle_state = LifecycleState.APPROVED
    metrics = {"rank_ic_mean": 0.05}


def test_generic_report_contains_sources_and_reproducibility() -> None:
    report = render_report(
        report_id="report_generic",
        title="Generic Report",
        sections={"Metrics": {"rank_ic_mean": 0.05}},
        source_links=["alpha_registry:alpha_report"],
        reproducibility={"run_id": "run_1"},
    )

    assert "alpha_registry:alpha_report" in report.markdown
    assert "rank_ic_mean" in report.markdown
    assert "<h1>Generic Report</h1>" in report.html
    assert report.metadata["reproducibility"]["run_id"] == "run_1"


def test_alpha_review_report_uses_card_and_risk_review() -> None:
    risk_review = RiskReview(alpha_id="alpha_report", findings=[])

    report = render_alpha_review_report(_Card(), risk_review, source_links=["registry:alpha_report"])

    assert "Alpha Review alpha_report" in report.markdown
    assert "rank(close)" in report.markdown
    assert "blocks_promotion" in report.markdown


def test_backtest_and_synthetic_reports_include_metrics() -> None:
    contract = BacktestContract(
        contract_id="bt_report",
        asset_classes=[AssetClass.EQUITY],
        rebalance_frequency="1d",
        benchmark_id="eq:b",
        portfolio_constraints={"max_positions": 1},
        equity_cost_model={"commission_bps": 1},
    )
    backtest = type(
        "Backtest",
        (),
        {
            "run_id": "run_report",
            "contract": contract,
            "metrics": pd.DataFrame([{"metric_name": "cumulative_return", "metric_value": 0.12}]),
            "weights": pd.DataFrame([{"w": 1}]),
            "trades": pd.DataFrame([{"t": 1}]),
            "equity_curve": pd.DataFrame([{"e": 1}]),
        },
    )()
    synthetic = SyntheticIndexResult(
        config=SyntheticIndexConfig(index_id="syn_report", name="Synthetic Report"),
        levels=pd.DataFrame([{"level": 1000}]),
        constituents=pd.DataFrame([{"instrument_id": "eq:a"}]),
        benchmark=pd.DataFrame(),
        metrics=pd.DataFrame([{"metric_name": "index_cumulative_return", "metric_value": 0.1}]),
        methodology={"weighting_scheme": "equal_weight"},
    )

    backtest_report = render_backtest_report(backtest, source_links=["backtest:run_report"])
    synthetic_report = render_synthetic_index_report(synthetic, source_links=["synthetic:syn_report"])

    assert "cumulative_return" in backtest_report.markdown
    assert "index_cumulative_return" in synthetic_report.markdown
    assert "equal_weight" in synthetic_report.markdown


def test_agent_and_evaluation_reports_include_trace_and_summary() -> None:
    state = AgentRunState(run_id="agent_report", workflow_name="workflow", status="completed")
    state.trace.append(
        ToolTrace(step_id="s1", tool_name="test.ok", status="completed", attempts=1, output={"value": 1})
    )
    evaluation = AlphaEvaluationResult(
        alpha_id="alpha_eval",
        aligned=pd.DataFrame([{"row": 1}]),
        by_date=pd.DataFrame([{"row": 1}]),
        summary=pd.DataFrame([{"metric_name": "rank_ic_mean", "metric_value": 0.02}]),
    )

    agent_report = render_agent_run_report(state, source_links=["agent:agent_report"])
    eval_report = render_evaluation_summary_report(evaluation, source_links=["evaluation:alpha_eval"])

    assert "test.ok" in agent_report.markdown
    assert "rank_ic_mean" in eval_report.markdown
    assert "evaluation:alpha_eval" in eval_report.markdown
