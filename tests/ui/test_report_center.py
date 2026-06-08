import duckdb

from alphaops.reports.renderer import list_report_inventory, read_report_preview, render_report, save_report_document
from alphaops.storage.duckdb import initialize_duckdb


def test_report_center_saves_registers_and_reads_existing_reports(tmp_path) -> None:
    db_path = initialize_duckdb(tmp_path / "alphaops.duckdb")
    document = render_report(
        report_id="report_ui",
        title="Report UI",
        sections={"Metrics": {"rank_ic_mean": 0.1}},
        source_links=["alpha_registry:alpha_ui"],
        reproducibility={"run_id": "run_ui"},
    )

    paths = save_report_document(
        db_path,
        document,
        output_dir=tmp_path / "reports",
        report_type="alpha_review",
        source_run_id="alpha_ui",
    )
    inventory = list_report_inventory(db_path)
    preview = read_report_preview(paths["md"])

    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute("SELECT report_type, source_run_id, path FROM reports WHERE report_id = 'report_ui'").fetchone()

    assert paths["md"].exists()
    assert paths["html"].exists()
    assert row[0] == "alpha_review"
    assert row[1] == "alpha_ui"
    assert bool(inventory.iloc[0]["exists"]) is True
    assert "rank_ic_mean" in preview
