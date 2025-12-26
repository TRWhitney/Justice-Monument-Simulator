"""
validate_schema.py — Validate a JSON instance against a JSON Schema.

Usage:
  python scripts/validate_schema.py --schema path/to/schema.json --instance path/to/data.json
  python scripts/validate_schema.py --schema schema.json --instance data.json --schema-dir ./schemas --format

Exit codes:
  0 = valid
  1 = instance invalid
  2 = schema invalid / runtime error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema
from jsonschema import validators

# jsonschema v4 uses the "referencing" library for $ref resolution (RefResolver is deprecated).
try:
    import referencing
    from referencing import Registry, Resource
except Exception:  # pragma: no cover
    referencing = None
    Registry = None
    Resource = None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_registry(
    schema_path: Path, schema: Dict[str, Any], schema_dir: Optional[Path]
) -> Optional["Registry"]:
    """
    Best-effort $ref support:
      - Registers the root schema
      - Optionally registers all *.json files under schema_dir (non-recursive by default)
    If 'referencing' isn't available, returns None (jsonschema will still work for internal refs).
    """
    if referencing is None:
        return None

    reg = Registry()

    # Helper: add a schema to the registry if it has an identifiable ID.
    def add_schema_to_registry(
        schema_obj: Dict[str, Any], default_uri: Optional[str] = None
    ) -> None:
        # jsonschema's internal id_of depends on draft; use Draft2020-12's id_of for robustness
        # (works fine even if schema declares an earlier draft in practice).
        id_of = referencing.jsonschema.DRAFT202012.id_of
        uri = id_of(schema_obj) or default_uri
        if not uri:
            return
        reg_resource = Resource.from_contents(schema_obj)
        nonlocal reg
        reg = reg.with_resource(uri, reg_resource)

    # Root schema: use file:// URI as a fallback base for relative refs.
    root_uri = schema_path.resolve().as_uri()
    add_schema_to_registry(schema, default_uri=root_uri)

    # If a schema directory is provided, register sibling schemas to help resolve $ref like "other.schema.json"
    if schema_dir and schema_dir.exists() and schema_dir.is_dir():
        for p in sorted(schema_dir.glob("*.json")):
            try:
                obj = load_json(p)
                if isinstance(obj, dict):
                    add_schema_to_registry(obj, default_uri=p.resolve().as_uri())
            except Exception:
                # Ignore unreadable schemas; registry is best-effort.
                pass

    return reg


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate JSON instance against JSON Schema."
    )
    ap.add_argument(
        "--schema", required=True, type=Path, help="Path to JSON Schema file"
    )
    ap.add_argument(
        "--instance", required=True, type=Path, help="Path to JSON instance file"
    )
    ap.add_argument(
        "--schema-dir",
        type=Path,
        default=None,
        help="Optional directory of additional schemas to help resolve $ref (defaults to schema file's directory)",
    )
    ap.add_argument(
        "--format",
        action="store_true",
        help="Enable JSON Schema 'format' checks (requires supported formats / extras).",
    )
    ap.add_argument(
        "--all-errors",
        action="store_true",
        help="Print all validation errors (default). If unset, prints all anyway; kept for compatibility.",
    )
    args = ap.parse_args()

    schema_path: Path = args.schema
    instance_path: Path = args.instance
    schema_dir: Optional[Path] = args.schema_dir or schema_path.parent

    try:
        schema = load_json(schema_path)
        instance = load_json(instance_path)

        if not isinstance(schema, dict):
            print("Schema root must be a JSON object.", file=sys.stderr)
            return 2

        # Pick the right validator based on $schema (or default to latest) and validate schema itself.
        ValidatorCls = validators.validator_for(schema)
        ValidatorCls.check_schema(schema)

        registry = build_registry(schema_path, schema, schema_dir)

        kwargs: Dict[str, Any] = {}
        if registry is not None:
            kwargs["registry"] = registry
        if args.format:
            # Enables 'format' checks when supported by the validator.
            kwargs["format_checker"] = getattr(ValidatorCls, "FORMAT_CHECKER", None)

        validator = ValidatorCls(schema, **kwargs)

        errors = sorted(
            validator.iter_errors(instance),
            key=lambda e: (list(e.absolute_path), e.message),
        )

        if not errors:
            print("✅ VALID: instance conforms to schema")
            return 0

        print(f"❌ INVALID: {len(errors)} error(s)")
        for i, err in enumerate(errors, 1):
            path = "$"
            if err.absolute_path:
                path += "".join(
                    f"[{p!r}]" if isinstance(p, str) else f"[{p}]"
                    for p in err.absolute_path
                )
            print(f"\n{i}. Path: {path}\n   Message: {err.message}")
            if err.schema_path:
                spath = "$" + "".join(
                    f"[{p!r}]" if isinstance(p, str) else f"[{p}]"
                    for p in err.schema_path
                )
                print(f"   Schema path: {spath}")

        return 1

    except jsonschema.exceptions.SchemaError as e:
        print("❌ SCHEMA ERROR: The provided schema is invalid.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"❌ FILE NOT FOUND: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"❌ JSON PARSE ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
