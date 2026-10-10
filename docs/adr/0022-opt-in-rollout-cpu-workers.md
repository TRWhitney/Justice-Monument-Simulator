# ADR 0022: Offer CPU workers for rollout sampling

Status: accepted, 2026-10-10.

Whitney approved optional CPU workers alongside shared-core optimization. Add a
positive integer `workers` keyword to synchronous and incremental recommendation
APIs. Its default is one, preserving local dispatch, existing GUI and CLI use,
and planner configuration defaults.

For sampled work, use the standard library process executor with an explicit
spawn context. Each process receives one stable decision, data, configuration,
model, suggested rules, actual seed and utility weights. Each owns fresh caches.
Submit action and absolute sample-index pairs in bounded batches. Consume results
in submission order. Preserve paired action seeds, phase boundaries, adaptive
selection, final budgets and final aggregation exactly.

The incremental iterator owns its executor. Finish only the current batch before
checking cancellation. Close processes before emitting a terminal cancelled or
complete update, and release them on iterator close and exceptions. Do not queue
future batches. Worker exceptions propagate. Synchronous progress reports the
number of newly completed samples per batch when workers are enabled.

Support the builtin uniform, weighted and learned encounter models. Reject
custom planner or model types with an actionable configuration error when CPU
workers are requested, since reconstructing a plain planner would lose their
custom dispatch. They retain local dispatch with one worker. Data and model
configuration must stay stable during a decision. Consumers need a guarded main
entry point for spawn. Headless modules themselves import no Qt.

Threads do not provide this CPU parallelism under the Python interpreter lock.
Fork would inherit the GUI process and platform state. Persistent worker pools
could reduce repeated startup cost, but would need a separate ownership and
stale-decision protocol. Per-decision spawn keeps cancellation and cleanup explicit.
No native dependency or approximation is added.

See [public usage](../headless/api.md),
[measurements](../headless/latency.md) and
[configurable execution choices](planner-execution-options.html).
