"""Exact input dependencies for reusing predicate results."""

import ast
from collections.abc import Callable, Iterable
from math import isfinite
import operator

Comparison = tuple[Callable[[float, float], bool], int | float, bool]
Reads = dict[str, tuple[Comparison, ...] | None]
RESOURCES = {"case_index", "coins", "pop", "mh", "dismissals", "retirement_chests"}
_COMPARISONS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def condition_reads(predicates: Iterable[str]) -> tuple[set[str], Reads]:
    """Use truth values only when every read is a direct literal comparison.

    Arithmetic, chained comparisons and dynamic arguments retain exact values.
    The caller still evaluates predicates on cache misses, including errors.
    """
    names: set[str] = set()
    reads: dict[str, list[Comparison] | None] = {}
    for predicate in predicates:
        tree = ast.parse(predicate, mode="eval")
        parents = {
            child: node
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            if isinstance(node, ast.Name) and node.id in RESOURCES:
                key = node.id
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "counters"
            ):
                key = f"counters.{node.attr}"
            else:
                continue
            comparisons = reads.setdefault(key, [])
            if comparisons is None:
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Compare) and len(parent.ops) == 1:
                other = parent.comparators[0] if parent.left is node else parent.left
                try:
                    literal = ast.literal_eval(other)
                    finite = isinstance(literal, (int, float)) and isfinite(literal)
                except (ValueError, TypeError, OverflowError):
                    finite = False
                if finite and type(parent.ops[0]) in _COMPARISONS:
                    comparisons.append(
                        (
                            _COMPARISONS[type(parent.ops[0])],
                            literal,
                            parent.left is node,
                        )
                    )
                    continue
            reads[key] = None
    return names, {key: tuple(value) if value else None for key, value in reads.items()}


def comparison_key(value: int | float, comparisons: tuple[Comparison, ...] | None):
    if comparisons is None:
        return type(value), value
    return tuple(
        compare(value, literal) if left else compare(literal, value)
        for compare, literal, left in comparisons
    )
