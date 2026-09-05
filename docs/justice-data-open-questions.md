# Justice Monument Data: Open Questions

Last reviewed: 2026-09-05.

The [case JSON audit](audits/justice-case-json-2026-09.md) now compares the builtin
data directly with the official deployed web client. All 90 client rows map to
the existing 85 simulator offers; Grumblo's indistinguishable rows are grouped
with their original selection multiplicity.

## Resolved from executable client code

- Cool Bird uses 50/50 flips; the health flip preserves the last MH on tails.
- Glass Gamble is one in three despite the one-in-four dialogue.
- Billionaire's reward probabilities are 30% two chests, 63% three chests,
  3.5% two dismissals, and 3.5% two coins.
- Grumblo's conditional gift weights are equal; Mystery Gift rejection loses
  one popularity on two of the five underlying rows.
- Rupie's ordinary exchanges use deterministic percentage formulas.
- Poppy's Humble Lesson adds 160% of original popularity, rounded to nearest;
  her IOU is repaid by the next Scripticus at 135%, rounded upward.
- Life Insurance preserves retirement chests.
- Ordinary row multiplicity, eligibility, forced Harbinger variants, the
  post-Harbinger chest bias, and magnet/Secret ordering have client evidence.

These findings are implemented and regression-tested. The prior uniform-offer
assumption is superseded for the builtin client-backed dataset. Existing custom
datasets retain their generic defaults unless they opt into the new rules.

## Subsequent JSON audit corrections

Hand's temporary popularity debt and Never Uncool's floor now survive until the
client's post-action normalization boundary. Ghost retains its explicit arrival
zero clamp and runs before Hand, regardless of agreement order. Gratefulbinger
rejection records zero MH under the builtin default; custom datasets and explicit
debt modes retain their behavior.

The immediate-result comparison now matches all 5,733 permitted actions and all
6,750 payment gates. See the audit for source provenance and coverage limits.
Several wiki-derived annotations remain to be corrected separately.
