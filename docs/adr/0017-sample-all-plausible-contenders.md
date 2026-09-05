# ADR 0017: Sample every plausible contender

Status: accepted, 2026-09-05.

## Decision

Compare each eligible finite-scored action with the current leader when deciding
adaptive sampling. Retain the existing epsilon and 1.96-standard-error threshold.
Use paired sample differences for equal-length streams; unequal-length streams
use the existing marginal-variance estimate. Rank contenders stably by expected
utility, including suggested biases as before.

Extend the leader and all overlapping contenders to the existing per-action
maximum. Recompute contenders after each round because the leader can change.
Only extend actions still below the maximum, using their previously unused seed
range. Each action can be extended once; the loop ends when no contender has
remaining budget. Preserve sample order, aggregation, progress events, and caps.

## Alternatives and limits

Use the [configurable uncertainty comparison](adaptive-sampling-options.html)
to vary means, uncertainty, and sample count and export the comparison.

| Choice | Consequence |
| --- | --- |
| Compare every action with the leader (selected) | Gives an uncertain third action a chance to displace the leader. |
| Compare only the two highest means | Can ignore a lower observed mean whose uncertainty still permits it to be best. |
| Always extend every action | Uses the whole budget even for clearly separated alternatives. |

This can increase total samples. It preserves the existing statistical heuristic;
normal intervals and finite observed variance do not guarantee correct ranking,
especially for rare outcomes. Exhausting the cap does not establish certainty.

## Verification

Cover an uncertain third action, paired streams that distinguish equal marginal
variances, and a leader change that makes an initially excluded action relevant.
Verify each additional seed range runs once, no cap is exceeded, and existing
adaptive and biased-score tests pass. Run the complete repository gate.
