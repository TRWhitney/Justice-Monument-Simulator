# ADR 0025: Report settled actions before forecasts

Status: accepted, 2026-10-10.

Whitney wants a consumer to recognize when an action is final even while its
statistics remain unfinished. For example, insufficient coins can exclude
approval while zero dismissals excludes dismissal, leaving rejection.

Append `decision_final=False` to the public immutable `PlannerUpdate`. A final
decision means the planner will not revise its action for this input. Existing
`complete` continues to mean configured statistics calculation has finished.
Finite sampling does not establish optimality or remove forecast uncertainty.

If eligibility leaves one action and the decision requires sampled forecasts,
yield that action before sampling or starting CPU workers. Set `decision_final`
and leave `complete` false. Supply an empty score tuple rather than inventing
utility, chest, death or variance estimates. Consumers can close at this yield to
avoid forecast work, or continue for all configured samples. All subsequent
updates retain the final action. Recheck cancellation before worker startup.

For competing actions, partial estimates remain provisional until successful
completion. Exact shortcuts and completed no-action results set both flags.
Cancellation before evaluation has no final decision. Cancellation after a sole
action was established preserves its finality and any estimates already produced,
while leaving `complete` false. Inputs, data and rules must remain stable;
consumers invalidate updates when their live decision changes.

Keep synchronous recommendations and their scores, progress counts, sample
indices, adaptive boundaries, horizon, risk and pacing unchanged. This refines
[ADR 0012](0012-share-action-evaluation-results.md): root scores still run when
iteration continues, while an action-only consumer can stop before those scores.
Future simulated sole-action selection keeps its existing shortcut.

A separate forecast API would duplicate decision setup and worker ownership.
Overloading `complete` would falsely claim statistics existed. A placeholder
zero-sample numeric score would confuse unavailable estimates with exact results.
The additional flag and an empty initial score tuple keep the distinction explicit.

See [public API](../headless/api.md) and
[configurable examples](headless-options.html).
