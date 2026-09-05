# ADR 0002: Preserve client row probabilities in grouped offers

Status: accepted, 2026-09-05.

## Decision

Keep the 85 existing offer IDs and their search/manual-selection behavior. Record
all 90 client row IDs in the case JSON. Grouped Grumblo offers retain their row
multiplicity, and their approval and rejection distributions use matching latent
row order. A player resolves only one action per encounter; integrating the
unobserved row preserves each action's observable probability distribution without
revealing a hidden reward to the planner before its decision.

The builtin dataset opts into the pinned client's encounter rules. Compose an
exact distribution from the ordinary row weights, loan proposals (including
rejected proposals), post-Harbinger replacement, and magnet/Secret priority.
Sampling and possible-encounter enumeration use that same distribution. Existing
custom datasets retain their original defaults and generic override behavior.
Weighted and learned models continue to adjust the ordinary proposal.

Use existing effects and saved state for conditional rewards, arrival counter
resets, and pending deals. Optional payment-resource and approval-trigger-order
fields express client action gates and the position of Bean's bonus. Scheduled
labels identify investments while their events remain pending. No persistence
format or UI rendering architecture is replaced.

The bounded implementation in `engine/encounter.py` follows the pinned client's
row identifiers; new client versions require deliberate re-auditing of these rules.
A [configurable comparison](client-case-options.html) describes the alternatives
and exports the selected tradeoff without changing application settings.

## Alternatives

- Expanding the UI to 90 offers would expose duplicate indistinguishable dialogue
  and change manual case selection. Reject for this correction.
- Retaining one weight per grouped offer would preserve the observed frequency
  defect. Reject.
- Giving characters equal weights would depart from the client's row lottery.
  Reject.

## Verification and limits

Exact fixtures cover the 71-row clean pool, post-Harbinger mixtures, forced
Harbingers, pending-deal gates, magnet/Secret ordering, and action outcomes.
The existing planner shortcut and custom-model suites remain required.

The simulator does not reproduce the browser's PRNG stream or number of discarded
proposal draws. It preserves seeded reproducibility of its own simulations and
the client distributions. Serialized runs remain readable; already-saved pending
effect payloads retain their original contract amounts rather than silently
rewriting historical state.
