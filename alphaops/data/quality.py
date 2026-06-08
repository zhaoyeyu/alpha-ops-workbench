"""Multi-asset data quality engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from alphaops.data.contracts import AssetClass, MARKET_BAR_COLUMNS
from alphaops.storage.duckdb import initialize_duckdb


class QualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str
    message: str
    field: str | None = None
    instrument_id: str | None = None


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    dataset_id: str
    asset_class: AssetClass | None = None
    row_count: int
    quality_score: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    issues: list[QualityIssue]


def profile_market_bars(
    frame: pd.DataFrame,
    *,
    dataset_id: str,
    max_abs_return: float = 0.8,
    stale_duplicate_threshold: int = 3,
) -> QualityReport:
    issues: list[QualityIssue] = []
    issues.extend(_missing_columns(frame))
    if not issues:
        issues.extend(_missing_values(frame))
        issues.extend(_duplicates(frame))
        issues.extend(_ohlc_checks(frame))
        issues.extend(_volume_checks(frame))
        issues.extend(_return_jumps(frame, max_abs_return=max_abs_return))
        issues.extend(_futures_contract_checks(frame))
        issues.extend(_stale_close_checks(frame, threshold=stale_duplicate_threshold))
        issues.extend(_coverage_gaps(frame))

    return QualityReport(
        report_id=f"qr_{uuid4().hex}",
        dataset_id=dataset_id,
        asset_class=_single_asset_class(frame),
        row_count=len(frame),
        quality_score=_score(issues),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        issues=issues,
    )


def persist_quality_report(db_path: str, report: QualityReport) -> None:
    with duckdb.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO quality_reports VALUES (?, ?, ?, ?, ?, ?)",
            [
                report.report_id,
                report.dataset_id,
                report.asset_class.value if report.asset_class else None,
                report.row_count,
                report.quality_score,
                report.created_at,
            ],
        )
        for issue in report.issues:
            conn.execute(
                "INSERT INTO quality_issues VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    f"qi_{uuid4().hex}",
                    report.report_id,
                    issue.code,
                    issue.severity,
                    issue.field,
                    issue.instrument_id,
                    issue.message,
                ],
            )


def fetch_market_bars_for_quality(
    db_path: str | Path,
    *,
    asset_class: AssetClass | None = None,
    symbol: str | None = None,
    source_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if asset_class is not None:
        clauses.append("asset_class = ?")
        params.append(asset_class.value)
    if symbol:
        clauses.append("upper(symbol) = upper(?)")
        params.append(symbol)
    if source_id:
        clauses.append("source_id = ?")
        params.append(source_id)
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = "LIMIT ?" if limit else ""
    if limit:
        params.append(limit)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            f"""
            SELECT {", ".join(MARKET_BAR_COLUMNS)}
            FROM market_bars
            {where_sql}
            ORDER BY instrument_id, timestamp
            {limit_sql}
            """,
            params,
        ).fetchdf()


def profile_stored_market_bars(
    db_path: str | Path,
    *,
    asset_class: AssetClass | None = None,
    symbol: str | None = None,
    source_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    dataset_id: str | None = None,
) -> QualityReport:
    bars = fetch_market_bars_for_quality(
        db_path,
        asset_class=asset_class,
        symbol=symbol,
        source_id=source_id,
        start=start,
        end=end,
    )
    if bars.empty:
        raise ValueError("No market_bars rows match the selected Data Quality filters.")
    report = profile_market_bars(bars, dataset_id=dataset_id or source_id or _dataset_id(asset_class, symbol, start, end))
    persist_quality_report(str(db_path), report)
    return report


def quality_overview(db_path: str | Path, *, limit: int = 25) -> dict[str, Any]:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        report_count = int(conn.execute("SELECT COUNT(*) FROM quality_reports").fetchone()[0])
        issue_count = int(conn.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0])
        average_score = conn.execute("SELECT AVG(quality_score) FROM quality_reports").fetchone()[0]
        severity_rows = conn.execute(
            "SELECT severity, COUNT(*) FROM quality_issues GROUP BY severity ORDER BY severity"
        ).fetchall()
        recent = conn.execute(
            """
            SELECT
                q.report_id,
                q.dataset_id,
                q.asset_class,
                q.row_count,
                q.quality_score,
                q.created_at,
                COUNT(i.issue_id) AS issue_count,
                max(dl.lineage_id) AS lineage_id,
                max(dl.source_kind) AS source_kind,
                max(dl.adapter_name) AS adapter_name
            FROM quality_reports q
            LEFT JOIN quality_issues i ON q.report_id = i.report_id
            LEFT JOIN data_lineage dl ON q.dataset_id = dl.source_id
            GROUP BY q.report_id, q.dataset_id, q.asset_class, q.row_count, q.quality_score, q.created_at
            ORDER BY q.created_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()
    return {
        "report_count": report_count,
        "issue_count": issue_count,
        "average_score": float(average_score or 0.0),
        "issues_by_severity": {row[0]: int(row[1]) for row in severity_rows},
        "recent_reports": recent,
    }


def quality_issue_table(
    db_path: str | Path,
    *,
    report_id: str | None = None,
    severity: str | None = None,
    code: str | None = None,
) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if report_id:
        clauses.append("i.report_id = ?")
        params.append(report_id)
    if severity:
        clauses.append("i.severity = ?")
        params.append(severity)
    if code:
        clauses.append("i.code = ?")
        params.append(code)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            f"""
            SELECT
                i.report_id,
                q.dataset_id,
                q.asset_class,
                i.code,
                i.severity,
                i.field,
                i.instrument_id,
                i.message
            FROM quality_issues i
            JOIN quality_reports q ON i.report_id = q.report_id
            {where_sql}
            ORDER BY q.created_at DESC, i.severity, i.code
            """,
            params,
        ).fetchdf()


def quality_score_history(db_path: str | Path, *, asset_class: AssetClass | None = None) -> pd.DataFrame:
    target = initialize_duckdb(db_path)
    params: list[Any] = []
    where_sql = ""
    if asset_class:
        where_sql = "WHERE asset_class = ?"
        params.append(asset_class.value)
    with duckdb.connect(str(target)) as conn:
        return conn.execute(
            f"""
            SELECT created_at, dataset_id, asset_class, quality_score, row_count
            FROM quality_reports
            {where_sql}
            ORDER BY created_at
            """,
            params,
        ).fetchdf()


def symbol_quality_drilldown(db_path: str | Path, instrument_id: str) -> dict[str, Any]:
    target = initialize_duckdb(db_path)
    with duckdb.connect(str(target)) as conn:
        coverage = conn.execute(
            """
            SELECT
                instrument_id,
                symbol,
                asset_class,
                COUNT(*) AS rows,
                MIN(timestamp) AS first_timestamp,
                MAX(timestamp) AS last_timestamp,
                COUNT(DISTINCT source_id) AS source_count
            FROM market_bars
            WHERE instrument_id = ?
            GROUP BY instrument_id, symbol, asset_class
            """,
            [instrument_id],
        ).fetchdf()
        issues = conn.execute(
            """
            SELECT report_id, code, severity, field, message
            FROM quality_issues
            WHERE instrument_id = ?
            ORDER BY severity, code
            """,
            [instrument_id],
        ).fetchdf()
    return {"coverage": coverage, "issues": issues}


def _dataset_id(asset_class: AssetClass | None, symbol: str | None, start: str | None, end: str | None) -> str:
    parts = ["market_bars", asset_class.value if asset_class else "all", symbol or "all", start or "min", end or "max"]
    return ":".join(parts)


def _missing_columns(frame: pd.DataFrame) -> list[QualityIssue]:
    return [
        QualityIssue(
            code="MISSING_COLUMN",
            severity="error",
            field=column,
            message=f"Missing required column: {column}",
        )
        for column in MARKET_BAR_COLUMNS
        if column not in frame.columns
    ]


def _missing_values(frame: pd.DataFrame) -> list[QualityIssue]:
    issues = []
    required = [column for column in MARKET_BAR_COLUMNS if column != "contract_id"]
    for column in required:
        missing = int(frame[column].isna().sum())
        if missing:
            issues.append(
                QualityIssue(
                    code="MISSING_VALUE",
                    severity="error",
                    field=column,
                    message=f"{missing} rows have missing {column}",
                )
            )
    return issues


def _duplicates(frame: pd.DataFrame) -> list[QualityIssue]:
    count = int(frame.duplicated(subset=["instrument_id", "timestamp", "frequency", "source_id"]).sum())
    if not count:
        return []
    return [QualityIssue(code="DUPLICATE_BAR", severity="error", message=f"{count} duplicate bars found")]


def _ohlc_checks(frame: pd.DataFrame) -> list[QualityIssue]:
    issues = []
    prices = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    non_positive = (prices <= 0).any(axis=1) | prices.isna().any(axis=1)
    if int(non_positive.sum()):
        issues.append(
            QualityIssue(
                code="INVALID_PRICE",
                severity="error",
                message=f"{int(non_positive.sum())} rows have non-positive or invalid prices",
            )
        )
    bad_range = (prices["high"] < prices[["open", "low", "close"]].max(axis=1)) | (
        prices["low"] > prices[["open", "high", "close"]].min(axis=1)
    )
    if int(bad_range.sum()):
        issues.append(
            QualityIssue(
                code="INVALID_OHLC_RANGE",
                severity="error",
                message=f"{int(bad_range.sum())} rows have invalid OHLC ranges",
            )
        )
    return issues


def _volume_checks(frame: pd.DataFrame) -> list[QualityIssue]:
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    bad = (volume < 0) | volume.isna()
    if not int(bad.sum()):
        return []
    return [
        QualityIssue(
            code="INVALID_VOLUME",
            severity="warning",
            field="volume",
            message=f"{int(bad.sum())} rows have negative or invalid volume",
        )
    ]


def _return_jumps(frame: pd.DataFrame, *, max_abs_return: float) -> list[QualityIssue]:
    working = frame[["instrument_id", "timestamp", "close"]].copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"])
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    working = working.sort_values(["instrument_id", "timestamp"])
    returns = working.groupby("instrument_id")["close"].pct_change().abs()
    count = int((returns > max_abs_return).sum())
    if not count:
        return []
    return [
        QualityIssue(
            code="LARGE_RETURN_JUMP",
            severity="warning",
            field="close",
            message=f"{count} absolute returns exceed {max_abs_return:.0%}",
        )
    ]


def _futures_contract_checks(frame: pd.DataFrame) -> list[QualityIssue]:
    futures = frame[frame["asset_class"].astype(str) == AssetClass.FUTURES.value]
    if futures.empty:
        return []
    missing = int(futures["contract_id"].isna().sum())
    if not missing:
        return []
    return [
        QualityIssue(
            code="FUTURES_CONTRACT_ID_MISSING",
            severity="error",
            field="contract_id",
            message=f"{missing} futures rows are missing contract_id",
        )
    ]


def _stale_close_checks(frame: pd.DataFrame, *, threshold: int) -> list[QualityIssue]:
    working = frame[["instrument_id", "timestamp", "close"]].copy().sort_values(["instrument_id", "timestamp"])
    issues = []
    for instrument_id, group in working.groupby("instrument_id"):
        runs = (group["close"] != group["close"].shift()).cumsum()
        max_run = int(group.groupby(runs)["close"].size().max())
        if max_run >= threshold:
            issues.append(
                QualityIssue(
                    code="STALE_CLOSE",
                    severity="warning",
                    field="close",
                    instrument_id=str(instrument_id),
                    message=f"{instrument_id} has {max_run} repeated close values",
                )
            )
    return issues


def _coverage_gaps(frame: pd.DataFrame) -> list[QualityIssue]:
    issues = []
    working = frame[["instrument_id", "timestamp"]].copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"])
    for instrument_id, group in working.groupby("instrument_id"):
        if len(group) < 2:
            continue
        deltas = group.sort_values("timestamp")["timestamp"].diff().dropna()
        if deltas.empty:
            continue
        if deltas.max() > deltas.median() * 3:
            issues.append(
                QualityIssue(
                    code="COVERAGE_GAP",
                    severity="warning",
                    field="timestamp",
                    instrument_id=str(instrument_id),
                    message=f"{instrument_id} has a large timestamp gap",
                )
            )
    return issues


def _single_asset_class(frame: pd.DataFrame) -> AssetClass | None:
    if "asset_class" not in frame.columns:
        return None
    values = frame["asset_class"].dropna().astype(str).unique()
    if len(values) != 1:
        return None
    return AssetClass(values[0])


def _score(issues: list[QualityIssue]) -> float:
    penalty = 0.0
    for issue in issues:
        penalty += 0.2 if issue.severity == "error" else 0.08
    return round(max(0.0, 1.0 - penalty), 4)
