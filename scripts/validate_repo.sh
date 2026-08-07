#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

uv sync

export PYTHONPATH="${repo_root}/src${PYTHONPATH:+:$PYTHONPATH}"

uv run --with ruff ruff format --check .
uv run --with ruff ruff check .

uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/justice_data.schema.json \
  --instance src/justice_sim/data/builtin/justice_data.json \
  --format
uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/suggested_rules.schema.json \
  --instance src/justice_sim/data/builtin/suggested_rules.json \
  --format

uv run --with pytest pytest -m "unit"
uv run --with pytest pytest -m "gui"

if [[ ! -f "src/justice_sim/main.py" ]]; then
  echo "Missing entry point: src/justice_sim/main.py" >&2
  exit 1
fi

uv run python -m justice_sim.main --smoke
