"""Persisted Alpha Registry with lifecycle events and audit records."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from alphaops.lifecycle.rules import LifecycleState, RiskFlag, RiskSeverity, validate_transition
from alphaops.storage.duckdb import initialize_duckdb


@dataclass(frozen=True)
class AlphaCard:
    alpha_id: str
    formula: str
    ast_version: str
    lifecycle_state: LifecycleState
    metrics: dict[str, float]
    risk_flags: list[RiskFlag]
    report_links: list[str]
    created_at: datetime


class AlphaRegistry:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = initialize_duckdb(db_path)

    def register_for_review(
        self,
        payload: dict[str, object],
        *,
        actor: str = "alpha_factory",
        reason: str = "factory_candidate",
    ) -> AlphaCard:
        alpha_id = str(payload["alpha_id"])
        formula = str(payload["formula"])
        ast_version = str(payload.get("ast_version", "0.1"))
        metrics = {str(key): float(value) for key, value in dict(payload.get("metrics", {})).items()}
        now = _now()
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO alpha_registry VALUES (?, ?, ?, ?, ?)",
                [alpha_id, formula, ast_version, LifecycleState.REGISTRY_REVIEW.value, now],
            )
            _insert_metric_snapshots(conn, alpha_id, metrics, now)
            _insert_event(conn, alpha_id, None, LifecycleState.REGISTRY_REVIEW, actor, reason, now)
        return self.get_card(alpha_id)

    def add_risk_flag(
        self,
        alpha_id: str,
        flag: RiskFlag,
    ) -> None:
        now = _now()
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO alpha_risk_flags VALUES (?, ?, ?, ?, ?, ?, ?)",
                [_flag_id(alpha_id, flag, now), alpha_id, flag.severity.value, flag.code, flag.message, now, None],
            )

    def transition(
        self,
        alpha_id: str,
        target: LifecycleState,
        *,
        actor: str,
        reason: str,
        report_link: str | None = None,
    ) -> AlphaCard:
        card = self.get_card(alpha_id)
        gate = validate_transition(
            card.lifecycle_state,
            target,
            metrics=card.metrics,
            risk_flags=card.risk_flags,
        )
        if not gate.allowed:
            raise ValueError("lifecycle transition blocked: " + ", ".join(gate.reasons))
        now = _now()
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE alpha_registry SET lifecycle_state = ? WHERE alpha_id = ?",
                [target.value, alpha_id],
            )
            _insert_event(conn, alpha_id, card.lifecycle_state, target, actor, reason, now)
            if report_link:
                conn.execute(
                    "INSERT INTO reports VALUES (?, ?, ?, ?, ?)",
                    [_report_id(alpha_id, report_link, now), "alpha_lifecycle", alpha_id, report_link, now],
                )
        return self.get_card(alpha_id)

    def get_card(self, alpha_id: str) -> AlphaCard:
        with duckdb.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT alpha_id, formula, ast_version, lifecycle_state, created_at FROM alpha_registry WHERE alpha_id = ?",
                [alpha_id],
            ).fetchone()
            if row is None:
                raise KeyError(f"alpha_id not found: {alpha_id}")
            metric_rows = conn.execute(
                """
                SELECT metric_name, metric_value
                FROM alpha_metric_snapshots
                WHERE alpha_id = ?
                QUALIFY captured_at = MAX(captured_at) OVER (PARTITION BY metric_name)
                """,
                [alpha_id],
            ).fetchall()
            flag_rows = conn.execute(
                "SELECT severity, code, message FROM alpha_risk_flags WHERE alpha_id = ? AND resolved_at IS NULL",
                [alpha_id],
            ).fetchall()
            report_rows = conn.execute(
                "SELECT path FROM reports WHERE source_run_id = ? ORDER BY created_at",
                [alpha_id],
            ).fetchall()
        return AlphaCard(
            alpha_id=row[0],
            formula=row[1],
            ast_version=row[2],
            lifecycle_state=LifecycleState(row[3]),
            metrics={name: float(value) for name, value in metric_rows},
            risk_flags=[RiskFlag(RiskSeverity(severity), code, message) for severity, code, message in flag_rows],
            report_links=[path for (path,) in report_rows],
            created_at=row[4],
        )

    def events(self, alpha_id: str) -> list[dict[str, object]]:
        with duckdb.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT event_id, alpha_id, from_state, to_state, actor, reason, created_at
                FROM alpha_lifecycle_events
                WHERE alpha_id = ?
                ORDER BY created_at
                """,
                [alpha_id],
            ).fetchall()
        return [
            {
                "event_id": row[0],
                "alpha_id": row[1],
                "from_state": row[2],
                "to_state": row[3],
                "actor": row[4],
                "reason": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def cards_frame(self, *, state: LifecycleState | None = None, query: str | None = None) -> pd.DataFrame:
        clauses = []
        params = []
        if state:
            clauses.append("r.lifecycle_state = ?")
            params.append(state.value)
        if query:
            clauses.append("(lower(r.alpha_id) LIKE lower(?) OR lower(r.formula) LIKE lower(?))")
            params.extend([f"%{query}%", f"%{query}%"])
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with duckdb.connect(str(self.db_path)) as conn:
            return conn.execute(
                f"""
                SELECT
                    r.alpha_id,
                    r.formula,
                    r.ast_version,
                    r.lifecycle_state,
                    r.created_at,
                    COUNT(DISTINCT m.metric_name) AS metric_count,
                    COUNT(DISTINCT f.flag_id) FILTER (WHERE f.resolved_at IS NULL) AS active_risk_flags,
                    COUNT(DISTINCT e.event_id) AS event_count
                FROM alpha_registry r
                LEFT JOIN alpha_metric_snapshots m ON r.alpha_id = m.alpha_id
                LEFT JOIN alpha_risk_flags f ON r.alpha_id = f.alpha_id
                LEFT JOIN alpha_lifecycle_events e ON r.alpha_id = e.alpha_id
                {where_sql}
                GROUP BY r.alpha_id, r.formula, r.ast_version, r.lifecycle_state, r.created_at
                ORDER BY r.created_at DESC
                """,
                params,
            ).fetchdf()

    def metric_history(self, alpha_id: str) -> pd.DataFrame:
        with duckdb.connect(str(self.db_path)) as conn:
            return conn.execute(
                """
                SELECT alpha_id, metric_name, metric_value, captured_at
                FROM alpha_metric_snapshots
                WHERE alpha_id = ?
                ORDER BY captured_at, metric_name
                """,
                [alpha_id],
            ).fetchdf()

    def risk_flags_frame(self, alpha_id: str | None = None, *, active_only: bool = True) -> pd.DataFrame:
        clauses = []
        params = []
        if alpha_id:
            clauses.append("alpha_id = ?")
            params.append(alpha_id)
        if active_only:
            clauses.append("resolved_at IS NULL")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with duckdb.connect(str(self.db_path)) as conn:
            return conn.execute(
                f"""
                SELECT flag_id, alpha_id, severity, code, message, created_at, resolved_at
                FROM alpha_risk_flags
                {where_sql}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchdf()

    def events_frame(self, alpha_id: str | None = None) -> pd.DataFrame:
        clauses = []
        params = []
        if alpha_id:
            clauses.append("alpha_id = ?")
            params.append(alpha_id)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with duckdb.connect(str(self.db_path)) as conn:
            return conn.execute(
                f"""
                SELECT event_id, alpha_id, from_state, to_state, actor, reason, created_at
                FROM alpha_lifecycle_events
                {where_sql}
                ORDER BY created_at
                """,
                params,
            ).fetchdf()

    def reports_frame(self, alpha_id: str | None = None) -> pd.DataFrame:
        clauses = []
        params = []
        if alpha_id:
            clauses.append("source_run_id = ?")
            params.append(alpha_id)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with duckdb.connect(str(self.db_path)) as conn:
            return conn.execute(
                f"""
                SELECT report_id, report_type, source_run_id, path, created_at
                FROM reports
                {where_sql}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchdf()


def _insert_metric_snapshots(conn: duckdb.DuckDBPyConnection, alpha_id: str, metrics: dict[str, float], now: datetime) -> None:
    for name, value in metrics.items():
        conn.execute(
            "INSERT INTO alpha_metric_snapshots VALUES (?, ?, ?, ?)",
            [alpha_id, name, float(value), now],
        )


def _insert_event(
    conn: duckdb.DuckDBPyConnection,
    alpha_id: str,
    from_state: LifecycleState | None,
    to_state: LifecycleState,
    actor: str,
    reason: str,
    now: datetime,
) -> None:
    conn.execute(
        "INSERT INTO alpha_lifecycle_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            _event_id(alpha_id, to_state, now),
            alpha_id,
            from_state.value if from_state else None,
            to_state.value,
            actor,
            reason,
            now,
        ],
    )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _event_id(alpha_id: str, state: LifecycleState, timestamp: datetime) -> str:
    payload = f"{alpha_id}:{state.value}:{timestamp.isoformat()}"
    return "evt_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _flag_id(alpha_id: str, flag: RiskFlag, timestamp: datetime) -> str:
    payload = f"{alpha_id}:{flag.code}:{timestamp.isoformat()}"
    return "risk_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _report_id(alpha_id: str, path: str, timestamp: datetime) -> str:
    payload = f"{alpha_id}:{path}:{timestamp.isoformat()}"
    return "report_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
