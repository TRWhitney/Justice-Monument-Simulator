# Repository Guidelines

## Project Structure & Module Organization
- Root docs and config live at `Spec.md`, `pyproject.toml`, and `uv.lock`.
- Data and assets are under `src/justice_sim/data/builtin/`, with images in `src/justice_sim/data/builtin/images/`.
- JSON schema lives in `src/justice_sim/data/schema/justice_data.schema.json`; the validator script is `scripts/validate_schema.py`.
- Validation lives in `scripts/validate_repo.sh`.
- Application modules and tests follow the `Spec.md` layout: `src/justice_sim/...`, `tests/unit/`, and `tests/gui/`.

## Build, Test, and Development Commands
- `uv sync` installs Python dependencies from `uv.lock`.
- `./scripts/validate_repo.sh` runs the required gate: ruff format check, unit + GUI tests, and a smoke launch.
- `uv run python scripts/validate_schema.py --schema src/justice_sim/data/schema/justice_data.schema.json --instance src/justice_sim/data/builtin/justice_data.json` validates the builtin data (add `--format` for format checks).

## Validation & Definition of Done
- Every task must end with `./scripts/validate_repo.sh` passing locally; all checks green is required to complete work.
- Fix formatting, tests, or smoke-launch failures before requesting review.
- Smoke launch contract: `uv run python -m justice_sim.main --smoke` must start and exit quickly without user input.

## Documentation Updates
- Update relevant docs (including `Spec.md`) alongside code changes so instructions stay accurate.
- Check off completed items in `Spec.md` as tasks are finished.

## Coding Style & Naming Conventions
- Python: 4-space indentation; `snake_case` for modules, functions, and variables.
- JSON: use `snake_case` keys (example: `default_probability_format`).
- Assets: keep filenames lowercase in `src/justice_sim/data/builtin/images/`.
- Formatting is enforced by `ruff format`; avoid manual deviations.

## Testing Guidelines (TDD)
- Use test-driven development: write a failing test first, then implement, then refactor.
- Use `pytest` with `@pytest.mark.unit` and `@pytest.mark.gui` to distinguish suites.
- Place tests in `tests/unit/` and `tests/gui/` using `test_*.py` naming.
- Run `uv run pytest -m "unit"` and `uv run pytest -m "gui"` (mirrors validation).

## Architecture & Reactivity
- UI and state updates must be fully reactive: a single source of truth drives the UI, with no manual refresh or duplicated state.

## Commit & Pull Request Guidelines
- Git history currently uses short, imperative messages (example: "Initialize repo"); no formal convention enforced.
- PRs should include a concise summary, call out changes to `justice_data.json` or schema files, and note `./scripts/validate_repo.sh` results.

## Data & Schema Notes
- `justice_data.json` is the source-of-truth dataset; keep it in sync with `justice_data.schema.json`.
- If you add new schema files, pass `--schema-dir` to the validator to resolve `$ref` targets.
