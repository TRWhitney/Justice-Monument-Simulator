# Justice Monument Data: Open Questions

Last reviewed: 2026-08-06

## Scope and sources

This document tracks Justice Monument behavior that cannot currently be settled
from the available public sources. The audit compared all 85 local encounter
texts with the 85 Justice Monument interaction rows on the IdleOn Wiki's
[The Caverns](https://idleon.wiki/wiki/The_Caverns#tabber-Monument_Of_Justice)
page. References to the same NPCs in other caverns are intentionally excluded.

The deployed [IdleOn Justice helper](https://idleon-justice.vercel.app/) and its
[source repository](https://github.com/rcoopr/idleon-justice) are useful
secondary references, but they are not treated as authoritative when they
conflict with the Justice Monument table.

## Unresolved behavior

### Fizarre Drink: Glass Gamble probability

- Wiki encounter text and outcome: 1-in-4 chance.
- Wiki note and current simulator: 1-in-3 chance.
- Current behavior: `p = 1/3`.
- Needed evidence: an in-game data extraction, code reference, or sufficiently
  large controlled sample of Glass Gamble results.

### Concerned Poppy: Humble Lesson repayment

- The wiki only says that Popularity is set to 1 and more is returned at the
  next Poppy encounter.
- Current behavior: restore 180% of the Popularity removed when the deal was
  accepted.
- Unknowns: the multiplier, rounding point, and whether later Popularity gains
  affect the repayment.
- Needed evidence: before/after captures covering multiple starting Popularity
  values, preferably including values that produce fractional results.

### Concerned Poppy: IOU Request follow-up

- Poppy's dialogue says Scripticus will repay the coins.
- The wiki outcome table lists only the immediate `-4x` coins and `+5`
  Popularity, with no later repayment.
- Current behavior: immediate effects only; no Scripticus trigger.
- Needed evidence: observation of the next Scripticus encounter after accepting
  the IOU, or confirmation that the dialogue is flavor text.

### Rupie Slug exchange amount

- Both Rupie exchange rows say that "some" of one resource is removed and the
  other is given in return, without a range or distribution.
- Current behavior: exchange a uniformly selected whole amount from 1 through
  the ordinary case multiplier, at a 1:1 rate.
- Unknowns: minimum, maximum, distribution, exchange rate, and rounding.
- Needed evidence: repeated in-game exchanges at several case ranges.

### Random reward weights

The wiki lists possible rewards but not their probabilities for:

- Billionaire Chester: the three reward categories and the 2-3 chest range.
- Grumblo: Double Dip's two rewards.
- Grumblo: Mystery Gift's five rewards.

Current behavior gives each listed category equal weight and uses a uniform
integer roll for the chest range. Needed evidence is an in-game data reference
or a sufficiently large sample for each encounter.

## Accepted simulation assumption

Ordinary eligible encounters, including Harbinger offers, are treated as equally
likely by the full simulation because no encounter-weight data is available.
This is an intentional approximation for the simulator's non-core, exploratory
mode and should not be changed without new evidence.

## Resolved during the 2026-08-06 audit

The following are no longer open questions:

- Concerned Poppy: Fan Mail rejection is a flat `-40` Popularity.
- Cool Bird: Chest Flip awards 2 chests or removes 1 chest.
- Ordinary `x` scaling, Harbinger coin scaling, and Gratefulbinger probability
  match the formulas displayed by the wiki.
- Confirmed encounter-value, duration, override-lifecycle, solvency, rounding,
  and probability-boundary defects have regression coverage in the unit suite.
