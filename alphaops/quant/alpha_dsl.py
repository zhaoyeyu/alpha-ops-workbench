"""Alpha DSL v0.1 parser, AST, validation, and dependency tracking."""

from __future__ import annotations

import ast as py_ast
from dataclasses import dataclass
from typing import Any, Protocol

from alphaops.data.contracts import AlphaDslContract


class AlphaDslError(ValueError):
    """Structured Alpha DSL failure."""

    def __init__(self, code: str, message: str, *, node: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.node = node

    def as_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "node": self.node}


@dataclass(frozen=True)
class DslNode:
    node_type: str


@dataclass(frozen=True)
class NumberNode(DslNode):
    value: float

    def __init__(self, value: float) -> None:
        object.__setattr__(self, "node_type", "number")
        object.__setattr__(self, "value", float(value))


@dataclass(frozen=True)
class FieldNode(DslNode):
    name: str

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "node_type", "field")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True)
class BinaryOpNode(DslNode):
    operator: str
    left: DslNode
    right: DslNode

    def __init__(self, operator: str, left: DslNode, right: DslNode) -> None:
        object.__setattr__(self, "node_type", "binary_op")
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)


@dataclass(frozen=True)
class CallNode(DslNode):
    function: str
    args: tuple[DslNode, ...]

    def __init__(self, function: str, args: tuple[DslNode, ...]) -> None:
        object.__setattr__(self, "node_type", "call")
        object.__setattr__(self, "function", function)
        object.__setattr__(self, "args", args)


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    min_args: int
    max_args: int
    category: str
    description: str


class OperatorRegistry:
    """Registry for safe Alpha DSL operators."""

    def __init__(self) -> None:
        self._operators: dict[str, OperatorSpec] = {}

    def register(self, spec: OperatorSpec) -> None:
        self._operators[spec.name] = spec

    def get(self, name: str) -> OperatorSpec:
        try:
            return self._operators[name]
        except KeyError as exc:
            raise AlphaDslError("unknown_operator", f"operator is not registered: {name}", node=name) from exc

    def validate_call(self, node: CallNode) -> None:
        spec = self.get(node.function)
        count = len(node.args)
        if count < spec.min_args or count > spec.max_args:
            raise AlphaDslError(
                "invalid_argument_count",
                f"{node.function} expects {spec.min_args}-{spec.max_args} args, got {count}",
                node=node.function,
            )

    def names(self) -> list[str]:
        return sorted(self._operators)


def default_operator_registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    for spec in [
        OperatorSpec("ts_mean", 2, 2, "time_series", "Rolling mean by instrument."),
        OperatorSpec("ts_std", 2, 2, "time_series", "Rolling standard deviation by instrument."),
        OperatorSpec("ts_zscore", 2, 2, "time_series", "Rolling z-score by instrument."),
        OperatorSpec("delta", 2, 2, "time_series", "Lagged difference by instrument."),
        OperatorSpec("pct_change", 2, 2, "time_series", "Lagged percent change by instrument."),
        OperatorSpec("rank", 1, 1, "cross_sectional", "Cross-sectional percentile rank by timestamp."),
        OperatorSpec("zscore", 1, 1, "cross_sectional", "Cross-sectional z-score by timestamp."),
        OperatorSpec("neutralize", 2, 2, "neutralization", "Subtract group mean by timestamp and group field."),
    ]:
        registry.register(spec)
    return registry


class AstVisitor(Protocol):
    def visit(self, node: DslNode) -> Any: ...


_BINARY_OPERATORS: dict[type[py_ast.operator], str] = {
    py_ast.Add: "add",
    py_ast.Sub: "sub",
    py_ast.Mult: "mul",
    py_ast.Div: "div",
}


def parse_formula(formula: str) -> DslNode:
    """Parse a formula string into the Alpha DSL AST."""

    try:
        parsed = py_ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise AlphaDslError("syntax_error", exc.msg, node=str(exc.offset)) from exc
    return _convert_py_ast(parsed.body)


def _convert_py_ast(node: py_ast.AST) -> DslNode:
    if isinstance(node, py_ast.Constant) and isinstance(node.value, int | float):
        return NumberNode(float(node.value))
    if isinstance(node, py_ast.Name):
        return FieldNode(node.id)
    if isinstance(node, py_ast.UnaryOp) and isinstance(node.op, py_ast.USub):
        return BinaryOpNode("mul", NumberNode(-1), _convert_py_ast(node.operand))
    if isinstance(node, py_ast.BinOp):
        operator = _BINARY_OPERATORS.get(type(node.op))
        if operator is None:
            raise AlphaDslError("unsupported_binary_operator", "only +, -, *, and / are supported")
        return BinaryOpNode(operator, _convert_py_ast(node.left), _convert_py_ast(node.right))
    if isinstance(node, py_ast.Call):
        if not isinstance(node.func, py_ast.Name):
            raise AlphaDslError("unsafe_call", "only direct registered operator calls are allowed")
        if node.keywords:
            raise AlphaDslError("unsupported_keyword_args", "keyword arguments are not supported")
        return CallNode(node.func.id, tuple(_convert_py_ast(arg) for arg in node.args))
    raise AlphaDslError("unsupported_syntax", f"unsupported syntax node: {type(node).__name__}")


def collect_dependencies(node: DslNode) -> list[str]:
    dependencies: set[str] = set()

    def visit(current: DslNode) -> None:
        if isinstance(current, FieldNode):
            dependencies.add(current.name)
        elif isinstance(current, BinaryOpNode):
            visit(current.left)
            visit(current.right)
        elif isinstance(current, CallNode):
            for arg in current.args:
                visit(arg)

    visit(node)
    return sorted(dependencies)


def collect_operator_names(node: DslNode) -> list[str]:
    operators: set[str] = set()

    def visit(current: DslNode) -> None:
        if isinstance(current, BinaryOpNode):
            operators.add(current.operator)
            visit(current.left)
            visit(current.right)
        elif isinstance(current, CallNode):
            operators.add(current.function)
            for arg in current.args:
                visit(arg)

    visit(node)
    return sorted(operators)


def validate_ast(
    node: DslNode,
    *,
    available_fields: set[str],
    registry: OperatorRegistry | None = None,
) -> None:
    """Validate fields, operators, arity, and unsafe constructs."""

    active_registry = registry or default_operator_registry()
    binary_operator_names = {"add", "sub", "mul", "div"}

    def visit(current: DslNode) -> None:
        if isinstance(current, FieldNode):
            if current.name not in available_fields:
                raise AlphaDslError(
                    "unknown_field",
                    f"field is not available in input data: {current.name}",
                    node=current.name,
                )
        elif isinstance(current, BinaryOpNode):
            if current.operator not in binary_operator_names:
                raise AlphaDslError("unknown_operator", f"binary operator is not supported: {current.operator}")
            visit(current.left)
            visit(current.right)
        elif isinstance(current, CallNode):
            active_registry.validate_call(current)
            for arg in current.args:
                visit(arg)
        elif not isinstance(current, NumberNode):
            raise AlphaDslError("unknown_node", f"unknown node type: {type(current).__name__}")

    visit(node)


@dataclass(frozen=True)
class AlphaExpression:
    formula: str
    ast: DslNode
    dependencies: tuple[str, ...]
    operator_names: tuple[str, ...]

    def to_contract(self) -> AlphaDslContract:
        return AlphaDslContract(
            formula=self.formula,
            dependencies=list(self.dependencies),
            operator_names=list(self.operator_names),
        )

    def workflow_metadata(self) -> dict[str, bool | list[str] | str]:
        return {
            "ast_version": "0.1",
            "can_feed_ic_analysis": True,
            "can_feed_backtest": True,
            "can_feed_alpha_registry": True,
            "dependencies": list(self.dependencies),
            "operator_names": list(self.operator_names),
        }


def compile_formula(
    formula: str,
    *,
    available_fields: set[str],
    registry: OperatorRegistry | None = None,
) -> AlphaExpression:
    """Parse and validate a formula for downstream factor evaluation."""

    active_registry = registry or default_operator_registry()
    root = parse_formula(formula)
    validate_ast(root, available_fields=available_fields, registry=active_registry)
    return AlphaExpression(
        formula=formula,
        ast=root,
        dependencies=tuple(collect_dependencies(root)),
        operator_names=tuple(collect_operator_names(root)),
    )
