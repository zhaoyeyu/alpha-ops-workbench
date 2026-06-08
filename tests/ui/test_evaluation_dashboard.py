from alphaops.evals.cases import evaluation_case_catalog, list_evaluation_results, run_evaluation_cases
from alphaops.storage.duckdb import initialize_duckdb


def test_evaluation_dashboard_runs_selected_case_and_reads_results(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")

    catalog = evaluation_case_catalog()
    results = run_evaluation_cases(db_path, case_ids=["schema_tool_registry"])
    persisted = list_evaluation_results(db_path)

    assert set(catalog["case_id"]) >= {"schema_tool_registry", "tool_factor_success", "risk_flag_coverage"}
    assert len(results) == 1
    assert results[0].status == "passed"
    assert persisted.iloc[0]["case_id"] == "schema_tool_registry"
    assert persisted.iloc[0]["status"] == "passed"
