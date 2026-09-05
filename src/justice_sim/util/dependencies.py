"""Conservative counter dependencies in data and saved effect payloads."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import ast
from functools import lru_cache
import re

_COUNTER_REFERENCE = re.compile(r"\bcounters\s*\.\s*(\w+)")


@lru_cache(maxsize=2048)
def _text_counter_names(value: str) -> frozenset[str]:
    references = set(_COUNTER_REFERENCE.findall(value))
    try:
        tree = ast.parse(value, mode="eval")
    except SyntaxError:
        return frozenset(references)
    # Parentheses and explicit line continuations are valid around the accessor.
    references.update(
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "counters"
    )
    return frozenset(references)


def referenced_counter_names(*roots: object) -> frozenset[str]:
    """Return counters that can affect data- or rule-driven behavior."""
    references: set[str] = set()
    visited: set[int] = set()

    def visit(value: object) -> None:
        if isinstance(value, str):
            references.update(_text_counter_names(value))
            return
        if value is None or isinstance(value, (bool, int, float, bytes)):
            return
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                visit(getattr(value, item.name))
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(key)
                visit(item)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                visit(item)

    for root in roots:
        visit(root)
    return frozenset(references)
