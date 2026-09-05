# Case JSON audit against the deployed client

Reviewed September 5, 2026, after implementing the preceding behavior audit.
The original pass identified the boundary findings below. The subsequent
correction resolves all three runtime findings and the stale case annotations.

## Source and coverage

Primary source: the [official play page](https://www.legendsofidleon.com/ytGl5oc/)
loads [N.js](https://www.legendsofidleon.com/ytGl5oc/N.js). A fresh download matched
the implementation's pinned source: 26,029,206 bytes, SHA-256
`079728c5ade09eff6496cccf503692b506ff8407641d72430d006baf239f2955`.

The [case JSON](../../src/justice_sim/data/builtin/justice_data.json) contains 85
stable offers representing all 90 client rows. Five Mystery Gift rows and two
Double Dip rows are intentionally grouped. There are no missing or duplicated
client row mappings. The [row-by-row matrix](justice-case-json-2026-09.json)
records the original resource codes, scaling codes, payment gates, and offer IDs.

After normalizing case, punctuation, underscores, and resource placeholders,
89 of the 90 dialogue rows match. The remaining difference is Gratefulbinger's
substitution of the literal five-coin gift for the client's placeholder; the
value is correct. Dialogue is not treated as authoritative when executable code
contradicts it, notably Glass Gamble's advertised one-in-four chance and Cool
Bird's advertised loss of the last mental health.

An independent diagnostic ran extracted client resource/action code against the
simulator at five case levels (1, 6, 15, 30, 66), five resource configurations, and
three actions for every row. It checked **6,750 payment gates with zero
mismatches**, then compared **5,733 permitted immediate action results**. The
simulator's advance-to-next-case call was replaced with an identity function
inside that temporary diagnostic only, so a client's post-action state was not
incorrectly compared with a state that already received next-case investment
income. Neither repository code nor tests were altered by the diagnostic.

For grouped Grumblo cases, matching categorical branches were selected. Glass
Gamble used its losing branch and Billionaire used its two-chest branch in this
matrix; separate regression tests cover the other reward branches and probability
boundaries. Encounter eligibility and interactions with existing deals are
covered separately, not claimed to be exhaustive by this immediate-result matrix.

The original matrix had **5,708 matching results**. The other **25** all concern the
Gratefulbinger health boundary described below. Additional targeted client
arrival/action probes confirmed the two popularity-boundary findings.

## Findings and corrections

### 1. Hand's arrival penalty is clamped too early

**Impact: incorrect popularity and potentially incorrect recommendations.**

With Above the Law active, zero popularity, and ten coins, the next Reanimated
Hand arrival produces fourteen coins and temporarily **-2 popularity** in the
client. Approving Waive the Fine at case 2 adds one popularity, then the
client clamps the final result to **0**.

Before correction, the simulator clamped arrival popularity to zero immediately.
Approval then raised it to **1**. The JSON's -2 arrival penalty and +1 approval reward are
individually correct; their interpretation at the resource boundary is not.

**Resolved:** intermediate popularity survives through action evaluation. Ghost
still clamps its own drain to zero before Hand arrives, regardless of agreement
order. Final normalization then clamps Hand's result.

Relevant client rows: 62 (agreement), 1 (follow-up example). Relevant simulation
paths: `preview_state_after_encounter_triggers`, `apply_effects`, and
`coerce_resource_value`. The correction preserves the client's intermediate
values until the appropriate normalization boundary, including manual previews
and affordability checks.

### 2. Never Uncool's floor is enforced before the client enforces it

**Impact: the simulator can permit an approval the client blocks.**

With Never Uncool and Ghost's scare permit active, start displayed case 21 at
five popularity. The client's ordinary arrival drain reduces popularity to
**4**, even though the permanent popularity floor exists. Retirement Chester's
Pop for Chest requires **5**, so approval is unavailable at that point. The
client reapplies the popularity floor after resolving an action.

Before correction, the simulator clamped the arrival drain back to **5**, making
approval appear affordable. The floor value is correct in the JSON; its continuous
enforcement is not equivalent to the client's post-action enforcement.

**Resolved:** affordability and action formulas use the below-floor arrival value;
the permanent floor returns after the action resolves.

Relevant rows: 58, 50, 22. This shares the normalization-timing problem with
finding 1 and is addressed by one engine change with tests for
intermediate values, final values, manual resolution, and planner shortcuts.

### 3. Gratefulbinger rejection retains negative mental health

**Impact: incorrect final state and exaggerated low-health utility penalties.**

Rejecting Gratefulbinger from five MH yields **0 MH** in the client and **-994 MH**
in the original simulator. Both terminate survival, but the recorded resource
value and utility differ. The JSON's -999 penalty agrees with the client table; the client
also applies a final nonnegative clamp to MH. This accounts for all 25 remaining
immediate-result differences in the diagnostic.

**Resolved:** the builtin dataset now clamps final MH to zero. Generic datasets
and explicit `allow_negative` debt mode retain their behavior.

Relevant row: 25. Regression tests preserve custom-dataset and explicit debt-mode
behavior alongside the corrected builtin default.

### 4. Stale or incomplete wiki-derived notes

These were annotations in the JSON, rather than errors in the corrected numeric
outcomes or encounter rules. All five notes now describe the client behavior:

| Row | Offer | Original note discrepancy |
|---|---|---|
| 72 | Life Insurance | Claimed all currencies except dismissals become one, although retirement chests are preserved. |
| 26 | The Loan | Described a flat 15% reappearance chance every case; the actual ordinary-case proposal can be replaced and naturally selected Bean encounters can also repay it. |
| 61 | The Secret | Said it appeared immediately after the third drink; Harbinger rounds and Chest Magnet can delay it. |
| 25 | Gratefulbinger | Gave the probability formula without its minimum of three popularity. |
| 28 | Riddle Chest | The note ended mid-sentence; the executable answer is dismissal. |

The builtin `on_unpaid_effects` entry now identifies its legacy penalty label. Its
underfunded-approval path is now unreachable for the gated builtin Harbinger
case. Generic custom-dataset support for unpaid effects remains in use and is
not a reason to remove that engine capability.

## Correction discovered during this pass

The row matrix caught a detail missed in the preceding audit: only client rows
44 and 46 penalize Mystery Gift rejection. Rows 45, 47, and 71 do not. The
correct conditional chance is **40%, not 60%**. This was corrected, tested, and
folded into the existing local Grumblo correction commit before this report.
The earlier finding that an always-free rejection was incorrect still holds.

## Verification of the preceding implementation

The implementation passed `./scripts/validate_repo.sh`: formatting, linting,
schema validation, **264 unit tests**, **47 GUI tests**, and smoke launch.
Direct affected tests also passed, including exact no-rollout expectations,
custom random-outcome handling, real deterministic Rupie interaction, and the
Cool Bird losing branch at one MH. Six explicit GUI artifact tests passed;
ordinary verification did not update tracked review screenshots.

Saved-state round-trip coverage includes labelled pending investments. Existing
saved pending-effect payloads are not rewritten retrospectively; they retain
their stored amounts. The existing 85 offer IDs remain stable. Client row
probabilities are reproduced, but the browser's PRNG stream is not copied.

## Verification of the boundary correction

A fresh official client download retained the pinned hash. Re-running the same
immediate-result diagnostic produced **5,733 matches out of 5,733** and zero
mismatches across all **6,750 payment gates**. Targeted extracted-client probes
confirmed Hand/Ghost arrival ordering, the below-floor Rupie result (16 coins,
6 popularity), and Gratefulbinger's zero MH. The original tracked row matrix is
retained as evidence of the pre-correction audit.

The correction passed `./scripts/validate_repo.sh`: formatting, linting, both
schemas, **282 unit tests**, **50 GUI tests**, and smoke launch. The directly
affected unit suites passed **126 tests**; all **9** audit GUI interactions passed,
including the three new boundary paths. Short-circuit tests still require exact
expectations with zero rollouts.

See [ADR 0002](../adr/0002-client-case-distributions.md) for row representation and
[ADR 0003](../adr/0003-resource-normalization-boundaries.md) for normalization
configuration and compatibility. All findings listed in this audit are corrected;
the coverage limits above still apply.
