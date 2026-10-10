# ADR 0024: Make CPU pacing optional and configurable

Status: accepted, 2026-10-10.

Whitney chose 5 ms pauses after approximately 50 ms of computation, with
configurable durations and pacing disabled unless a caller enables it.
Expose `PacingConfig(pause_ms=5, work_ms=50)` through the headless interface and
accept it on both recommendation APIs. `pacing=None` preserves GUI and CLI
behavior. Simulation configuration and builtin sampling defaults remain intact.

Pass a decision-local pacer explicitly through rollout and continuation
evaluation. Count calling-thread CPU time only while a sample executes. Retain
the accumulated budget across samples and adaptive phases, excluding caller work
between incremental updates. Check before simulated action selection, matching
the experiment's frequent continuation checkpoints. Reset the work budget after
a positive sleep. Inject the clock and sleeper into the pacer for deterministic
checks; neither changes simulator RNG or game time.

Spawned workers receive only the immutable configuration and construct their own
pacers. Each tracks its own sampling work, excluding startup and idle waits.
No global or planner-scoped mutable pacing state crosses decisions or iterator
suspensions. Worker cleanup and cancellation boundaries remain unchanged.

Sleeping only between batches cannot reproduce this cadence because a batch can
last longer than 50 ms. Wall-clock budgets would also count descheduling and caller
waits. A pacer stored on the planner would mix suspended incremental decisions.
Checking every reducer operation would add overhead in a hotter loop.

This is cooperative pacing, not a strict burst limit or guaranteed cooling.
Exact preparation and summarization do not receive checkpoints, and an expensive
individual action can overrun the interval. OS scheduling can extend sleeps.
Pacing lowers average CPU duty by increasing elapsed time; shared-core efficiency
remains the way to reduce total CPU work.

See [public API](../headless/api.md#optional-cpu-pacing),
[measurements](../headless/latency.md#cpu-pacing) and
[configurable choices](planner-execution-options.html).
