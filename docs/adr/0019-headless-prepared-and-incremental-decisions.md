# Prepared roots and incremental headless recommendations

Status: accepted, 2026-10-09.

Overlay consumers observe arrival processing before asking for a decision.
`arrival_processed=False` preserves the public recommendation API's existing
pre-arrival behavior. Prepared roots reuse the reducer's `encounter_start`
protocol, with an empty set of root overrides to consume. The visible state
retains every remaining contract. Future encounters use ordinary arrival and
completion processing. Eligibility, exact evaluation, samples and failed action
fallbacks all receive the same root context.

Expose `recommend_incremental` as a pull iterator of immutable estimates. The
consumer controls scheduling and may close the iterator or provide a cancellation
predicate. Keep the synchronous API and progress callback. Sampling remains paired
by absolute sample index. Reporting batches never alter the initial budget,
adaptive contender boundaries, top-up seed ranges, maximum, risk preset or depth.
Online intermediate moments avoid repeated full-sample scans and copies; complete
scores use the existing arithmetic and retain the original samples.

Provide the public imports through `justice_sim.headless`, and load packaged JSON
and schemas through package-relative resources. Consumers own Idleon state
reconstruction and worker scheduling. Neither API imports Qt.

Review and export the [configurable options](headless-options.html).
An iterator was selected over callbacks because a consumer can stop work by
closing it and can choose when to request the next batch. A separate mutable
simulation engine was rejected because it would duplicate reducer rules.

See the [public interface](../headless/api.md). This extends ADR 0001 and preserves
ADRs 0006, 0016 and 0017's policy and sampling decisions.
