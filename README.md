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

Optional GUI launch overrides:

```bash
uv run justice-sim-gui --theme dark --ui-scale large --prompt-tour
```

## GUI Notes

- Bottom-left buttons toggle theme and UI scale (Auto/Small/Medium/Large).
- Theme and UI scale persist between runs.
- Guided tour appears once until dismissed or completed.
- Hold a resource's `-` or `+` button to adjust it repeatedly at increasing speed.
- Use the NPC shortcut row's circle-slash button to clear the active offer filter.
- Unfiltered offers show their deal-luck rank among the encounters currently possible; the run indicator summarizes recorded deal rankings.
- Recommendation utility includes a 95% confidence interval; close calls automatically receive additional rollouts under the builtin planner defaults.

## CLI Notes

- Type `help` for commands.
- Typical flow: `search offer`, `select 1`, `recommend`, `apply best`.
- Use `show-all on/off` to ignore offer conditions (when allowed).
- Switch sim modes with `sim full|mid|none` (manual randomness uses `choose`/`value`).
- Inspect history with `log` and `log show 1`.

## Tests

```bash
uv run pytest -m "unit"
uv run pytest -m "gui"
```

## Validation

```bash
./scripts/validate_repo.sh
```

The full gate checks Ruff formatting and linting, validates both builtin JSON
datasets against their schemas, runs unit and native Qt GUI tests, and performs a
smoke launch.

## Data Validation

```bash
uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/justice_data.schema.json \
  --instance src/justice_sim/data/builtin/justice_data.json \
  --format

uv run python scripts/validate_schema.py \
  --schema src/justice_sim/data/schema/suggested_rules.schema.json \
  --instance src/justice_sim/data/builtin/suggested_rules.json \
  --format
```
