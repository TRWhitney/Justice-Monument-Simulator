# ADR 0008: Reuse recommendations during manual offer selection

Status: accepted, 2026-09-05.

## Decision

Keep the existing cancellable process worker. Retain up to 32 completed
recommendations in the window, including their scores and samples. Reuse one
only for the same data/offer, serialized state, planner configuration, utility
weights, planner RNG state, encounter model, and suggested rules. Restore it
through the same result-consumption path as a worker result. Never cache worker
errors or incomplete calculations. Keep generation and current-state checks.

Resource adjustments continue to debounce before recalculating a selected offer.

## Alternatives

| Option | Result |
| --- | --- |
| Bounded completed-result reuse (selected) | Switching back to an unchanged offer avoids calculation and process startup. |
| Persistent worker | Could retain more internal caches, but introduces additional cancellation and lifecycle complexity. |

The application itself exposes Full, Mid, and None as configurable workflows.
The direct interaction artifact workflow below captures the selected behavior.

## Verification

Run `tests/gui/test_recommendation_reuse.py` for real selection and process
completion, switching away/back, changed state/settings, and planner-input invalidation.
Use `JUSTICE_OPTIMIZATION_ARTIFACT_DIR=/tmp/justice-optimization-review` for the
explicit optional screenshot workflow. Ordinary tests produce no success images.
Keep the progress, cancellation, close, main-window control, and simulation
interaction tests and run the complete repository gate. This is a native Qt app;
the repository has no configured Playwright suite.
