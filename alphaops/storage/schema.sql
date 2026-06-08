CREATE TABLE IF NOT EXISTS instruments (
    instrument_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('equity', 'etf', 'futures')),
    exchange TEXT NOT NULL,
    currency TEXT NOT NULL,
    root_symbol TEXT,
    name TEXT
);

CREATE TABLE IF NOT EXISTS futures_contracts (
    contract_id TEXT PRIMARY KEY,
    root_symbol TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    contract_month TEXT NOT NULL,
    multiplier DOUBLE NOT NULL,
    tick_size DOUBLE NOT NULL,
    currency TEXT NOT NULL,
    first_trade_date DATE,
    last_trade_date DATE,
    initial_margin DOUBLE,
    maintenance_margin DOUBLE,
    trading_session_id TEXT
);

CREATE TABLE IF NOT EXISTS trading_sessions (
    trading_session_id TEXT PRIMARY KEY,
    exchange TEXT NOT NULL,
    timezone TEXT NOT NULL,
    day_session_start TIME NOT NULL,
    day_session_end TIME NOT NULL,
    night_session_start TIME,
    night_session_end TIME
);

CREATE TABLE IF NOT EXISTS continuous_contract_map (
    continuous_symbol TEXT NOT NULL,
    root_symbol TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    roll_date DATE NOT NULL,
    roll_rule TEXT NOT NULL,
    weight DOUBLE NOT NULL,
    PRIMARY KEY (continuous_symbol, contract_id, roll_date)
);

CREATE TABLE IF NOT EXISTS market_bars (
    instrument_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('equity', 'etf', 'futures')),
    timestamp TIMESTAMP NOT NULL,
    frequency TEXT NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    adj_close DOUBLE,
    volume DOUBLE NOT NULL,
    currency TEXT NOT NULL,
    exchange TEXT NOT NULL,
    source_id TEXT NOT NULL,
    data_version TEXT NOT NULL,
    ingested_at TIMESTAMP NOT NULL,
    contract_id TEXT,
    PRIMARY KEY (instrument_id, timestamp, frequency, source_id)
);

CREATE TABLE IF NOT EXISTS universe_members (
    universe_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    effective_date DATE NOT NULL,
    end_date DATE,
    inclusion_reason TEXT NOT NULL,
    PRIMARY KEY (universe_id, instrument_id, effective_date)
);

CREATE TABLE IF NOT EXISTS return_series (
    run_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    frequency TEXT NOT NULL,
    return_value DOUBLE NOT NULL,
    cumulative_return DOUBLE NOT NULL,
    price_column TEXT NOT NULL,
    source_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (run_id, instrument_id, timestamp, frequency)
);

CREATE TABLE IF NOT EXISTS metric_results (
    run_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE NOT NULL,
    frequency TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (run_id, scope_id, metric_name)
);

CREATE TABLE IF NOT EXISTS backtest_contracts (
    contract_id TEXT PRIMARY KEY,
    asset_classes TEXT NOT NULL,
    rebalance_frequency TEXT NOT NULL,
    benchmark_id TEXT NOT NULL,
    portfolio_constraints_json TEXT NOT NULL,
    equity_cost_model_json TEXT,
    futures_cost_model_json TEXT,
    futures_rules_json TEXT
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    alpha_id TEXT NOT NULL,
    initial_capital DOUBLE NOT NULL,
    final_equity DOUBLE NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_weights (
    run_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    instrument_id TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    target_weight DOUBLE NOT NULL,
    PRIMARY KEY (run_id, timestamp, instrument_id)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    run_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    instrument_id TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    trade_weight DOUBLE NOT NULL,
    notional DOUBLE NOT NULL,
    cost DOUBLE NOT NULL,
    contract_count DOUBLE,
    margin_requirement DOUBLE,
    PRIMARY KEY (run_id, timestamp, instrument_id)
);

CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    run_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    gross_return DOUBLE NOT NULL,
    period_return DOUBLE NOT NULL,
    turnover DOUBLE NOT NULL,
    cost DOUBLE NOT NULL,
    equity DOUBLE NOT NULL,
    drawdown DOUBLE NOT NULL,
    PRIMARY KEY (run_id, timestamp)
);

CREATE TABLE IF NOT EXISTS data_lineage (
    lineage_id TEXT PRIMARY KEY,
    asset_class TEXT,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    permission_scope TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_reports (
    report_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    asset_class TEXT,
    row_count BIGINT NOT NULL,
    quality_score DOUBLE NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_issues (
    issue_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    field TEXT,
    instrument_id TEXT,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alpha_registry (
    alpha_id TEXT PRIMARY KEY,
    formula TEXT NOT NULL,
    ast_version TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS alpha_lifecycle_events (
    event_id TEXT PRIMARY KEY,
    alpha_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS alpha_metric_snapshots (
    alpha_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    PRIMARY KEY (alpha_id, metric_name, captured_at)
);

CREATE TABLE IF NOT EXISTS alpha_risk_flags (
    flag_id TEXT PRIMARY KEY,
    alpha_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    source_run_id TEXT,
    path TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_cases (
    case_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
