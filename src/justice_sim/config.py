"""Configuration and data loading for Justice Simulator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from justice_sim.models.offer import JusticeData
from justice_sim.util.validation import ValidationError, validate_data


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_DATA_PATH = (
    REPO_ROOT / "src" / "justice_sim" / "data" / "builtin" / "justice_data.json"
)
SCHEMA_PATH = (
    REPO_ROOT / "src" / "justice_sim" / "data" / "schema" / "justice_data.schema.json"
)


class DataLoadError(ValueError):
    """Raised when data loading or validation fails."""


def _load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise DataLoadError("JSON root must be an object")
    return data


def _validate_schema(data: Mapping[str, Any], schema_path: Path) -> None:
    schema = _load_json(schema_path)
    jsonschema.validate(instance=data, schema=schema)


def load_data(
    data_path: Path,
    *,
    schema_path: Path | None = None,
    validate_schema: bool = True,
) -> JusticeData:
    data = _load_json(data_path)
    if validate_schema:
        _validate_schema(data, schema_path or SCHEMA_PATH)

    errors = validate_data(data)
    if errors:
        raise ValidationError("\n".join(errors))

    return JusticeData.from_dict(data)


def load_builtin_data() -> JusticeData:
    return load_data(BUILTIN_DATA_PATH)
