# Headless overlay recommendations

## Problem statement
Overlay callers observe arrival effects before requesting a recommendation. The planner must accept that state and allow callers to stop obsolete sampling and consume intermediate estimates. Installed consumers must load builtin data without Qt or source paths.

## Solution
Add an optional arrival_processed input, defaulting to false, to recommendation entry points. Use the existing reducer encounter_start protocol with no root override consumption for prepared states. Future encounters retain ordinary processing. Expose an opt-in batched iterator with immutable per-action estimates, suggested action, completion and cancellation flags. Keep synchronous behavior and final adaptive decision boundaries, seeds, budgets, risk settings and horizon.

## User stories
1. As an overlay consumer, I can evaluate a visible prepared state without repeating arrival processing.
2. As an overlay consumer, I can display intermediate estimates and cancel between batches.
3. As an installed library consumer, I can load validated builtin data and run the planner without importing Qt.

## Implementation decisions
Consumers own state reconstruction and identify whether arrival processing and override consumption have already occurred. Cancellation is cooperative between batches. Batch size controls reporting only. Keep existing entry points. Profile the supplied 32-sample, three-action, 20-case workload and optimize only measured shared-core costs with seeded equivalence checks. Consult ADRs 0001, 0006, 0016, 0017 and 0018.

## Testing decisions
Test prepared resource values, preserved future contracts, eligibility, exact and sampled paths and failed transitions. Compare incremental and synchronous seeded results across batch sizes and adaptive rounds. Test cancellation before work and after partial work. Build and install a wheel into a temporary location and run in isolation with Qt imports blocked. Run affected unit tests and the repository gate.

## Out of scope
Overlay integration, new GUI behavior, rule changes, budget reductions, horizon changes and altered policy accuracy.
