"""Deterministic Markdown and HTML report rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from alphaops.storage.duckdb import initialize_duckdb


@dataclass(frozen=True)
class ReportDocument:
    report_id: str
    title: str
    markdown: str
    html: str
    metadata: dict[str, Any] = field(default_factory=dict)


def render_report(
    *,
    report_id: str,
    title: str,
    sections: dict[str, Any],
    source_links: list[str],
    reproducibility: dict[str, Any],
) -> ReportDocument:
    generated_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    lines = [f"# {title}", "", "## Reproducibility", f"- generated_at: {generated_at}"]
    for key, value in sorted(reproducibility.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Sources"])
    lines.extend(f"- {source}" for source in source_links)
    for section_name, payload in sections.items():
        lines.extend(["", f"## {section_name}"])
        lines.extend(_render_payload(payload))
    markdown = "\n".join(lines)
    return ReportDocument(
        report_id=report_id,
        title=title,
        markdown=markdown,
        html=_markdown_to_html(markdown),
        metadata={
            "generated_at": generated_at,
            "source_links": source_links,
            "reproducibility": reproducibility,
        },
    )


def render_data_quality_report(report: Any, *, source_links: list[str]) -> ReportDocument:
    return render_report(
        report_id=getattr(report, "report_id", "data_quality_report"),
        title="Data Quality Report",
        sections={
            "Metrics": {
                "dataset_id": getattr(report, "dataset_id", None),
                "row_count": getattr(report, "row_count", None),
                "quality_score": getattr(report, "quality_score", None),
            },
            "Issues": [issue.model_dump() if hasattr(issue, "model_dump") else issue for issue in getattr(report, "issues", [])],
        },
        source_links=source_links,
        reproducibility={"renderer": "alphaops.reports.renderer", "artifact_type": "data_quality"},
    )


def render_alpha_review_report(card: Any, risk_review: Any, *, source_links: list[str]) -> ReportDocument:
    return render_report(
        report_id=f"report_{card.alpha_id}",
        title=f"Alpha Review {card.alpha_id}",
        sections={
            "Alpha Card": {
                "formula": card.formula,
                "state": card.lifecycle_state.value,
                "metrics": card.metrics,
            },
            "Risk Findings": risk_review.summary(),
        },
        source_links=source_links,
        reproducibility={"renderer": "alphaops.reports.renderer", "artifact_type": "alpha_review"},
    )


def render_backtest_report(result: Any, *, source_links: list[str]) -> ReportDocument:
    metrics = dict(zip(result.metrics["metric_name"], result.metrics["metric_value"], strict=True))
    return render_report(
        report_id=f"report_{result.run_id}",
        title=f"Backtest Report {result.run_id}",
        sections={
            "Metrics": metrics,
            "Rows": {
                "weights": len(result.weights),
                "trades": len(result.trades),
                "equity_curve": len(result.equity_curve),
            },
        },
        source_links=source_links,
        reproducibility={"renderer": "alphaops.reports.renderer", "artifact_type": "backtest", "contract_id": result.contract.contract_id},
    )


def render_synthetic_index_report(result: Any, *, source_links: list[str]) -> ReportDocument:
    metrics = dict(zip(result.metrics["metric_name"], result.metrics["metric_value"], strict=True))
    return render_report(
        report_id=f"report_{result.config.index_id}",
        title=f"Synthetic Index {result.config.name}",
        sections={
            "Methodology": result.methodology,
            "Metrics": metrics,
            "Rows": {"levels": len(result.levels), "constituents": len(result.constituents)},
        },
        source_links=source_links,
        reproducibility={"renderer": "alphaops.reports.renderer", "artifact_type": "synthetic_index"},
    )


def render_agent_run_report(state: Any, *, source_links: list[str]) -> ReportDocument:
    return render_report(
        report_id=f"report_{state.run_id}",
        title=f"Agent Run {state.run_id}",
        sections={
            "Run": {"workflow": state.workflow_name, "status": state.status},
            "Trace": [trace.__dict__ for trace in state.trace],
        },
        source_links=source_links,
        reproducibility={"renderer": "alphaops.reports.renderer", "artifact_type": "agent_run"},
    )


def render_evaluation_summary_report(result: Any, *, source_links: list[str]) -> ReportDocument:
    summary = dict(zip(result.summary["metric_name"], result.summary["metric_value"], strict=True))
    return render_report(
        report_id=f"report_eval_{result.alpha_id}",
        title=f"Evaluation Summary {result.alpha_id}",
        sections={"Summary": summary, "Rows": {"aligned": len(result.aligned), "by_date": len(result.by_date)}},
        source_links=source_links,
        reproducibility={"renderer": "alphaops.reports.renderer", "artifact_type": "evaluation"},
    )


def save_report_document(
    db_path: str | Path,
    document: ReportDocument,
    *,
    output_dir: str | Path,
    report_type: str,
    source_run_id: str,
    formats: tuple[str, ...] = ("md", "html"),
) -> dict[str, Path]:
    initialize_duckdb(db_path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    if "md" in formats:
        md_path = target_dir / f"{document.report_id}.md"
        md_path.write_text(document.markdown, encoding="utf-8")
        paths["md"] = md_path
    if "html" in formats:
        html_path = target_dir / f"{document.report_id}.html"
        html_path.write_text(document.html, encoding="utf-8")
        paths["html"] = html_path
    primary_path = paths.get("md") or next(iter(paths.values()))
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reports VALUES (?, ?, ?, ?, ?)",
            [document.report_id, report_type, source_run_id, str(primary_path), datetime.now(timezone.utc).replace(tzinfo=None)],
        )
    return paths


def list_report_inventory(db_path: str | Path, *, require_existing: bool = True) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        frame = conn.execute(
            """
            SELECT report_id, report_type, source_run_id, path, created_at
            FROM reports
            ORDER BY created_at DESC
            """
        ).fetchdf()
    if frame.empty:
        return frame
    frame["exists"] = frame["path"].map(lambda item: Path(str(item)).exists())
    return frame[frame["exists"]].reset_index(drop=True) if require_existing else frame


def read_report_preview(path: str | Path, *, max_chars: int = 6000) -> str:
    report_path = Path(path)
    if not report_path.exists():
        raise FileNotFoundError(str(report_path))
    return report_path.read_text(encoding="utf-8")[:max_chars]


def _render_payload(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [f"- {key}: {value}" for key, value in payload.items()]
    if isinstance(payload, list):
        if not payload:
            return ["- none"]
        return [f"- {item}" for item in payload]
    return [str(payload)]


def _markdown_to_html(markdown: str) -> str:
    html_lines = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            html_lines.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("- "):
            html_lines.append(f"<li>{escape(line[2:])}</li>")
        elif line:
            html_lines.append(f"<p>{escape(line)}</p>")
    return "\n".join(html_lines)
