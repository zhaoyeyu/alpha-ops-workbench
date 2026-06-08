import duckdb

from alphaops.evals.cases import EvaluationCase, EvaluationRunner, built_in_cases
from alphaops.storage.duckdb import initialize_duckdb


def test_built_in_evaluation_cases_pass_and_persist(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    runner = EvaluationRunner(db_path)

    results = runner.run(built_in_cases())

    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT case_id, status FROM evaluation_cases ORDER BY case_id").fetchall()

    assert {result.status for result in results} == {"passed"}
    assert len(rows) == len(results)
    assert all(status == "passed" for _, status in rows)


def test_evaluation_runner_fails_regression_case() -> None:
    runner = EvaluationRunner()

    results = runner.run(
        [EvaluationCase("failing_case", "regression", "Intentional failure", lambda: False)]
    )

    assert results[0].status == "failed"
