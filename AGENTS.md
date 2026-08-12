# Project Instructions

## Verification

- Use Python 3.12 or newer; `pyproject.toml` and `uv.lock` are authoritative.
- `./scripts/validate_repo.sh` is the required everyday gate. It runs formatting, linting, schema validation, unit tests, GUI tests, and the smoke launch.
- Investigate verification-time regressions instead of removing behavioral coverage.
- Reduce duplicated setup, unnecessary output, or slow critical-path work before increasing concurrency. Do not change production rendering architecture solely to make verification faster.
- Documentation-only changes require no pipeline or test execution.
- Engine, persistence, planner, or CLI changes require `./scripts/validate_repo.sh` plus the directly affected unit tests.
- UI changes require `./scripts/validate_repo.sh` plus the exact affected GUI and Playwright interaction path.
- Changes involving layout, focus, selection, drag and drop, image decoding, or Qt platform behavior require the full repository gate and direct GUI verification artifacts.
- Changes to Playwright configuration or browser-specific behavior require the complete configured Playwright suite across every assigned browser engine.
- Release verification requires `./scripts/validate_repo.sh` plus any applicable packaging checks.
- Only an explicit artifact-producing workflow may update tracked review screenshots or comparison data. Other verification commands must leave review artifacts unchanged.
- Do not hide flaky tests with retries. A retry that recovers is still a failed verification run.

## Playwright

- Keep browser verification state isolated between tests. First-launch tests explicitly use empty state; generated state is additional evidence and does not replace any product-test assignment.
- Ordinary runs capture screenshots only when an assertion needs the pixels or Playwright records a failure. Use the repository's explicit artifact-producing workflow for success-only review captures.
- Keep Playwright reports, traces, and performance output ignored unless they are intentional review artifacts. They must not contain source, storage state, or application data.
- Playwright HTML reports never open automatically. Open the most recent report explicitly after the verification command has exited.
- If Playwright fixtures, seed projects, or sample content are mutated during debugging, restore or recreate a known-clean baseline before using later verification runs as evidence.

## Documentation

- Keep `AGENTS.md` and `README.md` at the repository root.
- Keep other documentation in a separate folder structure and use HTML, CSS, and JavaScript as necessary.
- When documenting nontrivial design choices, provide interactive mockups or multiple configurable options so the developer can evaluate and export a selection.
- Write ADRs and consult existing ADRs when making architectural decisions.
