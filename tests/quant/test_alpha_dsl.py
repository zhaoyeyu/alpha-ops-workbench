import pytest

from alphaops.quant.alpha_dsl import (
    AlphaDslError,
    BinaryOpNode,
    CallNode,
    compile_formula,
    default_operator_registry,
    parse_formula,
)


def test_formula_parser_builds_ast_and_tracks_dependencies() -> None:
    expression = compile_formula(
        "rank(ts_mean(close, 2) - ts_mean(adj_close, 2))",
        available_fields={"close", "adj_close", "instrument_id", "timestamp"},
    )

    assert isinstance(expression.ast, CallNode)
    assert expression.dependencies == ("adj_close", "close")
    assert expression.operator_names == ("rank", "sub", "ts_mean")
    assert expression.to_contract().requires_ic_analysis is True
    assert expression.workflow_metadata()["can_feed_backtest"] is True


def test_parser_rejects_unsafe_syntax() -> None:
    with pytest.raises(AlphaDslError) as error:
        parse_formula("__import__('os').system('dir')")

    assert error.value.code in {"unsafe_call", "unsupported_syntax"}


def test_validation_rejects_unknown_operator_and_field() -> None:
    with pytest.raises(AlphaDslError) as unknown_operator:
        compile_formula("mystery(close)", available_fields={"close"})
    with pytest.raises(AlphaDslError) as unknown_field:
        compile_formula("rank(not_a_column)", available_fields={"close"})

    assert unknown_operator.value.code == "unknown_operator"
    assert unknown_field.value.code == "unknown_field"


def test_operator_registry_exposes_v01_operator_set() -> None:
    registry = default_operator_registry()

    assert registry.names() == [
        "delta",
        "neutralize",
        "pct_change",
        "rank",
        "ts_mean",
        "ts_std",
        "ts_zscore",
        "zscore",
    ]


def test_binary_ast_is_not_placeholder_text() -> None:
    ast = parse_formula("(close - open) / open")

    assert isinstance(ast, BinaryOpNode)
    assert ast.operator == "div"

