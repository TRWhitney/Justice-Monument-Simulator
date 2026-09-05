# ADR 0016: Integrate known outcomes in future comparisons

Status: accepted, 2026-09-05.

## Decision

Extend ADR 0006 to retain the probabilities already enumerated by immediate
action evaluation. For each known branch, run two nonrecursive continuations to
the full remaining horizon. Weight terminal utilities by branch probability,
then average the two estimates. A known rare loss must contribute even when two
random draws would miss it. Deterministic actions reuse their evaluated state.

Only use results that the shared reducer proves contain no unexpanded randomness
in preparation or completion. Unknown outcomes, including random arrival or
commitment effects, retain the existing two sampled action-and-future paths.
Do not shorten the horizon, prune branches, or change root rollout budgets.

Each enumerated branch starts a fresh RNG from the same sample token, paired
across actions and branches. These streams sample the future conditional on an
already selected branch; they do not replay the removed action draw. The actual
rollout's RNG remains untouched by policy evaluation, and applying its chosen
random action still consumes the original draws. Deterministic policy paths keep
their previous stream. Stochastic recommendation samples intentionally change.

This fixes a calculable counterexample: under balanced weights, a 99% delayed
ten-coin reward and 1% immediate loss of three MH at MH 3 has expected utility
11.125, below safe rejection's 11.8. The old future policy approved in 97 of 100
tested seeds. A thirty-coin reward reverses that inequality and remains accepted.

## Alternatives and limits

Compare branch counts and export the
[policy work options](planner-policy-options.html).

| Choice | Consequence |
| --- | --- |
| Integrate enumerable branches (selected) | Includes every known outcome at its probability; work scales with branch count. |
| Increase two action samples | Can reduce noise but can still omit known rare outcomes. |
| Shorten comparisons | Can hide delayed benefits or costs; rejected for this task. |
| Enumerate the entire future tree | Could provide exact answers for small trees, but is not tractable for the general encounter tree. |

Future encounters still use sampling, inner decisions still use immediate
scoring, and unknown randomness retains its existing approximation. This does
not establish globally optimal recommendations. Existing sample confidence
intervals do not measure policy approximation error.

## Verification

Use independently calculated terminal utilities for both unfavorable and
favorable rare-risk choices across 100 seeds. Exercise a root recommendation
whose correct value depends on rejecting a later unfavorable gamble. Verify
full depth, branch pairing, RNG isolation, and unexpanded-preparation fallback.
Retain delayed-payoff, eligibility, dead-end, shared-stream, and planner tests;
run the complete repository gate.
