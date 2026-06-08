"""Home workbench state loaded from real AlphaOps storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from alphaops.config import load_config


REQUIRED_PAGES = [
    "首页",
    "数据中心",
    "数据质量",
    "合成指数实验室",
    "Alpha 工厂",
    "回测实验室",
    "Alpha 注册表",
    "风险监控",
    "Agent 控制台",
    "报告中心",
    "连接器管理",
    "评估仪表盘",
]


class HomeStateError(RuntimeError):
    pass


def collect_home_state(db_path: str | Path | None = None) -> dict[str, Any]:
    target = Path(db_path) if db_path else load_config().paths.duckdb_path
    if not target.exists():
        raise HomeStateError(f"DuckDB file does not exist: {target}")
    with duckdb.connect(str(target)) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        _require_tables(
            tables,
            {
                "market_bars",
                "quality_reports",
                "alpha_registry",
                "alpha_risk_flags",
                "agent_runs",
                "reports",
                "evaluation_cases",
            },
        )
        data_coverage = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT asset_class, COUNT(*) FROM market_bars GROUP BY asset_class ORDER BY asset_class"
            ).fetchall()
        }
        quality = conn.execute(
            "SELECT COUNT(*), COALESCE(AVG(quality_score), 0) FROM quality_reports"
        ).fetchone()
        alpha_states = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT lifecycle_state, COUNT(*) FROM alpha_registry GROUP BY lifecycle_state ORDER BY lifecycle_state"
            ).fetchall()
        }
        risk_flags = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT severity, COUNT(*) FROM alpha_risk_flags WHERE resolved_at IS NULL GROUP BY severity ORDER BY severity"
            ).fetchall()
        }
        agent_runs = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT json_extract_string(state, '$.status') AS status, COUNT(*) FROM agent_runs GROUP BY status ORDER BY status"
            ).fetchall()
        }
        report_count = int(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
        eval_states = {
            row[0]: int(row[1])
            for row in conn.execute(
                "SELECT status, COUNT(*) FROM evaluation_cases GROUP BY status ORDER BY status"
            ).fetchall()
        }
    missing_assets = sorted({"equity", "etf", "futures"}.difference(data_coverage))
    readiness = {
        "market_data_ready": not missing_assets,
        "alpha_registry_ready": bool(alpha_states),
        "evaluation_ready": bool(eval_states),
        "missing_market_coverage": missing_assets,
    }
    return {
        "db_path": str(target),
        "required_pages": REQUIRED_PAGES,
        "data_coverage": data_coverage,
        "readiness": readiness,
        "quality": {"report_count": int(quality[0]), "average_score": float(quality[1])},
        "alpha_states": alpha_states,
        "risk_flags": risk_flags,
        "agent_runs": agent_runs,
        "report_count": report_count,
        "evaluation_cases": eval_states,
        "implemented_capabilities": [
            {"capability": "数据契约", "description": "统一 Equity、ETF、Futures 的标准行情字段"},
            {"capability": "数据血缘", "description": "记录每次公开数据或私有文件导入来源"},
            {"capability": "数据质量", "description": "检查缺失、价格区间、重复、覆盖缺口和期货合约字段"},
            {"capability": "Universe 构建", "description": "从已入库行情动态构建研究股票池或合约池"},
            {"capability": "收益与指标", "description": "计算收益、回撤、换手、风险收益指标"},
            {"capability": "Alpha DSL", "description": "公式解析、AST、校验、依赖跟踪和算子注册"},
            {"capability": "IC/RankIC", "description": "评估因子与未来收益的相关性和排序相关性"},
            {"capability": "研究级回测", "description": "支持调仓、成本、约束、Benchmark 与期货交易规则"},
            {"capability": "合成指数", "description": "构建篮子、权重、换手、成本和基准比较"},
            {"capability": "Alpha 工厂", "description": "生成候选 Alpha 并提交注册表审核"},
            {"capability": "Alpha 注册表", "description": "管理生命周期、指标快照、风险标记和报告链接"},
            {"capability": "Agent 工具", "description": "把量化能力暴露为可审计工具调用"},
            {"capability": "Agent 编排", "description": "执行研究计划、审批点、重试和风险阻断"},
            {"capability": "风险评审", "description": "检查回撤、换手、集中度、陈旧数据和成本敏感度"},
            {"capability": "报告生成", "description": "生成可复现 Markdown/HTML 研究报告"},
            {"capability": "评估用例", "description": "运行确定性用例验证系统行为"},
        ],
    }


def _require_tables(tables: set[str], required: set[str]) -> None:
    missing = required.difference(tables)
    if missing:
        raise HomeStateError("missing required tables: " + ", ".join(sorted(missing)))
