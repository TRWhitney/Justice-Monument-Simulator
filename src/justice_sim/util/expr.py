"""Safe expression and predicate evaluation for Justice Simulator."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Mapping


class ExprError(ValueError):
    """Raised when an expression is invalid or unsafe."""


@dataclass(frozen=True)
class ExprContext:
    variables: Mapping[str, Any]
    functions: Mapping[str, Callable[..., Any]]


_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub, ast.Not)
_ALLOWED_CMPOPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_ALLOWED_BOOLOPS = (ast.And, ast.Or)


def _validate_node(
    node: ast.AST, allowed_names: set[str], allowed_funcs: set[str]
) -> None:
    if isinstance(node, ast.Expression):
        _validate_node(node.body, allowed_names, allowed_funcs)
        return

    if isinstance(node, ast.Constant):
        return

    if isinstance(node, ast.Name):
        if node.id not in allowed_names:
            raise ExprError(f"Unknown name '{node.id}'")
        return

    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise ExprError("Disallowed binary operator")
        _validate_node(node.left, allowed_names, allowed_funcs)
        _validate_node(node.right, allowed_names, allowed_funcs)
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            raise ExprError("Disallowed unary operator")
        _validate_node(node.operand, allowed_names, allowed_funcs)
        return

    if isinstance(node, ast.Compare):
        if not all(isinstance(op, _ALLOWED_CMPOPS) for op in node.ops):
            raise ExprError("Disallowed comparison operator")
        _validate_node(node.left, allowed_names, allowed_funcs)
        for comparator in node.comparators:
            _validate_node(comparator, allowed_names, allowed_funcs)
        return

    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, _ALLOWED_BOOLOPS):
            raise ExprError("Disallowed boolean operator")
        for value in node.values:
            _validate_node(value, allowed_names, allowed_funcs)
        return

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExprError("Only simple function calls allowed")
        if node.func.id not in allowed_funcs:
            raise ExprError(f"Unknown function '{node.func.id}'")
        for arg in node.args:
            _validate_node(arg, allowed_names, allowed_funcs)
        return

    if isinstance(node, ast.Attribute):
        if not isinstance(node.value, ast.Name) or node.value.id not in {
            "counters",
            "flags",
            "statuses",
        }:
            raise ExprError("Only counters/flags/statuses attribute access allowed")
        if node.attr.startswith("_"):
            raise ExprError("Invalid attribute access")
        return

    raise ExprError(f"Disallowed expression node: {type(node).__name__}")


def _compile_expr(expr: str, ctx: ExprContext) -> ast.Expression:
    try:
        parsed = ast.parse(expr, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - tested via validate_predicate
        raise ExprError("Malformed expression") from exc

    allowed_names = set(ctx.variables.keys())
    allowed_funcs = set(ctx.functions.keys())
    _validate_node(parsed, allowed_names, allowed_funcs)
    return parsed


def evaluate(expr: str, ctx: ExprContext) -> Any:
    parsed = _compile_expr(expr, ctx)
    safe_globals = {"__builtins__": {}}
    safe_locals = dict(ctx.variables)
    safe_locals.update(ctx.functions)
    return eval(compile(parsed, "<expr>", "eval"), safe_globals, safe_locals)


def evaluate_numeric(expr: str, ctx: ExprContext) -> float:
    value = evaluate(expr, ctx)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ExprError("Expression did not evaluate to a number") from exc


def evaluate_predicate(expr: str, ctx: ExprContext) -> bool:
    value = evaluate(expr, ctx)
    if not isinstance(value, bool):
        raise ExprError("Predicate did not evaluate to boolean")
    return value


class _FlagAccessor:
    def __init__(self, values: set[str]) -> None:
        self._values = values

    def __getattr__(self, name: str) -> bool:
        return name in self._values


class _CounterAccessor:
    def __init__(self, values: Mapping[str, float]) -> None:
        self._values = values

    def __getattr__(self, name: str) -> float:
        return float(self._values.get(name, 0.0))


def build_predicate_context(
    *,
    case_index: int,
    coins: float,
    pop: float,
    mh: float,
    dismissals: float,
    retirement_chests: float,
    flags: set[str],
    statuses: set[str],
    counters: Mapping[str, int],
    extra_vars: Mapping[str, Any] | None = None,
) -> ExprContext:
    variables: dict[str, Any] = {
        "case_index": case_index,
        "coins": coins,
        "pop": pop,
        "mh": mh,
        "dismissals": dismissals,
        "retirement_chests": retirement_chests,
        "flags": _FlagAccessor(flags),
        "statuses": _FlagAccessor(statuses),
        "counters": _CounterAccessor(counters),
        "true": True,
        "false": False,
    }
    if extra_vars:
        variables.update(extra_vars)

    def has_flag(name: str) -> bool:
        return name in flags

    def has_status(name: str) -> bool:
        return name in statuses

    functions: dict[str, Callable[..., Any]] = {
        "has_flag": has_flag,
        "has_status": has_status,
    }

    return ExprContext(variables=variables, functions=functions)


def build_numeric_context(
    variables: Mapping[str, Any], functions: Mapping[str, Callable[..., Any]]
) -> ExprContext:
    return ExprContext(variables=variables, functions=functions)


def validate_predicate(expr: str) -> str | None:
    """Return error string if predicate is invalid, else None."""
    try:
        dummy_ctx = build_predicate_context(
            case_index=1,
            coins=0,
            pop=0,
            mh=1,
            dismissals=0,
            retirement_chests=0,
            flags=set(),
            statuses=set(),
            counters={},
        )
        _compile_expr(expr, dummy_ctx)
    except ExprError as exc:
        return str(exc)
    return None
