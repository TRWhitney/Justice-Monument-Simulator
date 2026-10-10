# Reuse simple health probes by payment eligibility

Status: accepted, 2026-10-09.

Profiling the 32-sample, three-action, 20-case workload found projected Harbinger
risk to be the largest cost. Within ADR 0010's existing restricted deterministic
profiles, non-health balances affect immediate health safety only through
payment eligibility and the base Harbinger's unpaid check. Cache these boolean
conditions instead of every raw balance. Evaluate arrivals and affordability
through the reducer; retain case index, original and arrived MH, ended state,
MH floor and native action blocks. Keep the existing bypass for randomness,
conditions, dynamic formulas, chains, matching triggers, requirements and due
next-case events. No general dependency compiler is introduced.

Probe dismissal first when checking whether any action preserves health.
Each probe has its own `Rng(0)`, so changing this existence-check order changes
neither safety nor encounter probabilities. Successful dismissal probes can
avoid unnecessary approval work. The cache still uses the reducer on misses,
retains definition identity, survives worker serialization and remains bounded.

Using complete raw balances remains a valid reference but misses equivalent
payment conditions. Broader caching of resource-dependent effects was rejected
because it would require a larger dependency proof. See the
[configurable options](headless-options.html) and
[profile and timings](../headless/latency.md).

Equivalence checks cover every builtin action across payment boundaries, health,
floors, blocks, history and active agreements, plus custom dependencies and
complete seeded recommendation hashes. This refines ADR 0010's key without
changing simulation or scoring rules.
