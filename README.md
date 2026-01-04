# Justice Monument Simulator

Simulator and advisor for the Idleon Justice Monument minigame. Provides both a Qt GUI and an interactive Rich CLI, backed by a shared simulation engine and JSON-driven data.

## Setup

```bash
uv sync
```

## Run

```bash
uv run justice-sim
uv run justice-sim-gui
```

## GUI Notes

- Bottom-left buttons toggle theme and UI scale (Auto/Small/Medium/Large).
- Theme and UI scale persist between runs.

## Tests

```bash
uv run pytest -m "unit"
uv run pytest -m "gui"
```

## Validation

```bash
./scripts/validate_repo.sh
```

## Data Validation

```bash
uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/justice_data.schema.json \
  --instance src/justice_sim/data/builtin/justice_data.json
```
