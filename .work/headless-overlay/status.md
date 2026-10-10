# Headless overlay

## Destination
[Specification](spec.md), [implementation tickets](tickets/) and [public interface](../../docs/headless/api.md).

## Current state
Delivered. Implementation, verification, independent review and focused repository history are complete.

## Progress
Prepared roots, cancellable incremental sampling, package-relative builtin loading and measured health-probe optimization are implemented. GUI/CLI entry points and planner defaults remain unchanged.

## Accepted sources
User requirements and ADRs 0001, 0006, 0016, 0017, 0018, [0019](../../docs/adr/0019-headless-prepared-and-incremental-decisions.md) and [0020](../../docs/adr/0020-cache-health-by-payment-eligibility.md).

## Verification
`./scripts/validate_repo.sh` passed formatting, linting, both schemas, 433 unit tests, 69 GUI tests and smoke launch. The focused command in `docs/headless/latency.md` produced matching full sample hashes. A targeted planner/packaging/health/policy/config/transition run passed 100 tests; the subsequent completed prepared/fallback suite passed 19 tests.

The analyzer import regression failed at `--help` before the fix and now passes. The script owns its checkout root independently of package resources. Renewed package/analyzer checks passed 12 tests; the full gate passed without retries.

The isolated wheel test installs into a separate temporary virtual environment and invokes the public API outside the checkout with Qt imports blocked. [Profile and timing evidence](../../docs/headless/latency.md) includes medians and time to first estimate.

## Review
Independent intent review passed with no findings. Engineering review admitted one compatibility blocker: the analyzer imported the removed checkout-root constant. A fresh correction review passed after the script took ownership of its checkout root and the subprocess regression check was added. No unresolved findings or judgments remain.

## Out of scope
Overlay integration, rule changes, reduced sampling, reduced horizon and GUI changes.

## Continuation
No accepted work remains. Branch `main`, initial commit `adfec5317f25b6cafeaaf9c32ec4c224549e58fa`.

Focused history: `eefee90` supports prepared decisions; `681314b` streams cancellable recommendations; `ae467d6` reuses equivalent payment probes. The final `[Fix] Load builtin data from installed packages` commit includes the public interface, isolated installation proof and this completed record. No history was squashed and no changes are intentionally left uncommitted.
