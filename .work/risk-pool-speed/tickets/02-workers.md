# 02 Optional CPU workers

**What to build:** Faster opt-in synchronous and incremental recommendations using CPU workers.

**Blocked by:** none

**Status:** delivered

- [x] `workers=1` remains the default; opt-in workers preserve exact samples across worker counts and reporting batches, including adaptive sampling and prepared roots.
- [x] Cancellation and iterator close release workers; fast paths and pre-cancellation start none; exceptions propagate.
- [x] Preserve builtin encounter-model configuration and explicit seed/weights. Reject unsupported custom models with an actionable message.
- [x] Validate isolated packaged spawning without Qt, full repository compatibility and repeated measured latency.

## Accepted sources
[Specification](../spec.md) and Whitney's explicit acceptance of optional CPU workers.

## Completion evidence
[Verification and comparison](../../../docs/headless/latency.md), focused unit tests
and the full repository gate passed. Independent intent and engineering reviews passed without findings.
