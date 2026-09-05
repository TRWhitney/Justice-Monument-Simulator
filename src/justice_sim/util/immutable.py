"""Owned immutable JSON-like payloads with reusable canonical representations."""

from collections.abc import Iterator, Mapping
from dataclasses import fields, is_dataclass
from functools import cached_property
from types import MappingProxyType
from typing import Any


class FrozenMapping(Mapping[str, Any]):
    """Copy inputs recursively; expose read-only data and support worker pickling."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        object.__setattr__(
            self,
            "_values",
            MappingProxyType(
                {key: freeze_payload(value) for key, value in values.items()}
            ),
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def items(self):
        return self._values.items()

    def keys(self):
        return self._values.keys()

    def values(self):
        return self._values.values()

    @cached_property
    def cache_key(self) -> tuple:
        return tuple(sorted((key, payload_key(value)) for key, value in self.items()))

    def __reduce__(self):
        # MappingProxyType itself cannot be pickled. Reconstruct ownership rather
        # than serializing cached keys or process-local object identities.
        return FrozenMapping, (dict(self._values),)

    def __deepcopy__(self, memo):
        return self

    def __repr__(self) -> str:
        return repr(dict(self._values))


def freeze_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float, bytes)):
        return value
    if isinstance(value, FrozenMapping):
        return value
    if isinstance(value, Mapping):
        return FrozenMapping(value)
    if isinstance(value, (tuple, list)):
        frozen = tuple(freeze_payload(item) for item in value)
        return (
            value
            if isinstance(value, tuple)
            and all(a is b for a, b in zip(value, frozen, strict=True))
            else frozen
        )
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze_payload(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        # Programmatic schedule/trigger payloads also accept EffectSpec records.
        # Normalize their declared fields to the same representation as raw JSON.
        return FrozenMapping(
            {item.name: getattr(value, item.name) for item in fields(value)}
        )
    raise TypeError(f"Unsupported mutable payload type: {type(value).__name__}")


def payload_key(value: Any) -> Any:
    """Canonicalize supported containers, reusing owned mapping keys."""
    if isinstance(value, FrozenMapping):
        return value.cache_key
    if isinstance(value, Mapping):
        return tuple(sorted((key, payload_key(item)) for key, item in value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(payload_key(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(payload_key(item) for item in value))
    return value


def thaw_payload(value: Any) -> Any:
    """Return independent ordinary JSON containers for persistence and exports."""
    if isinstance(value, Mapping):
        return {key: thaw_payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw_payload(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(thaw_payload(item) for item in value)
    return value
