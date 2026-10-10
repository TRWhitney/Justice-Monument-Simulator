# Prepared decision roots

Status: accepted, 2026-10-09.

Overlay consumers observe arrival processing before asking for a decision.
`arrival_processed=False` preserves the public recommendation API's existing
pre-arrival behavior. Prepared roots reuse the reducer's `encounter_start`
protocol, with an empty set of root overrides to consume. The visible state
retains every remaining contract. Future encounters use ordinary arrival and
completion processing. Eligibility, exact evaluation, samples and failed action
fallbacks all receive the same root context.
