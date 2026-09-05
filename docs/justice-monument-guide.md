# Justice Monument: complete game mechanics

Justice Monument is a court-case minigame in the Hole's tenth cavern. A run, called a story, consists of numbered cases. Each case presents one character and one request. Approving, rejecting, or dismissing that request changes the run's resources and may create obligations that affect later cases. The story ends when the post-decision mental-health check finds zero health. Its remaining retirement chests then produce account rewards.

This reference describes the official web client retrieved on September 5, 2026. It covers the rules, every request, continuing effects, encounter selection, and reward calculations. Short request labels in the catalogue describe the dialogue; the game does not assign those labels as formal case names. [Primary source: official game client](https://www.legendsofidleon.com/ytGl5oc/N.js).

- [Time, unlocks, and starting resources](#1-the-three-kinds-of-time)
- [Resources and notation](#2-resources-and-notation)
- [Case lifecycle and action processing](#3-the-lifecycle-of-a-case)
- [Encounter selection](#4-how-the-next-request-is-selected)
- [Complete request catalogue](#5-complete-request-catalogue)
- [Special calculations and continuing effects](#6-special-calculations-and-continuing-effects)
- [Retirement and account rewards](#7-retirement-and-account-rewards)
- [Source](#8-source-and-verification-boundary)

## 1. The three kinds of time

Three separate quantities are involved:

- **Monument AFK hours** are permanent account progress earned by AFKing at Justice. They unlock starting-resource bonuses. Starting a story does not spend these hours.
- **Accumulated story time** builds the monument's reward multiplier. Starting a story snapshots that multiplier and resets this accumulated time to zero.
- **Court cases**, also called days in some requests, are turns within a story. Advancing a case advances contracts and installments. Waiting at a request does not advance these contracts.

### Monument hours and starting bonuses

Justice's initial interaction requires at least one credited monument hour. The AFK award is credited in whole hours and is affected by monument AFK bonuses. The normal award path requires at least one actual hour away before crediting the hours. The listed thresholds are credited monument hours, not necessarily an equal number of real hours after bonuses.

The monument has eight sequential bricks. Once the corresponding hours requirement is met, clicking the next brick unlocks its bonus. Merely crossing the threshold is not the same as removing the brick.

| Credited hours required | Bonus unlocked | Starting MH after this brick | Starting dismissals | Starting popularity | Starting coin multiplier |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Starting coins | 1 | 0 | 3 | 1× |
| 80 | One additional MH | 2 | 0 | 3 | 1× |
| 300 | One dismissal | 2 | 1 | 3 | 1× |
| 750 | Higher starting coins | 2 | 1 | 3 | 1.5× |
| 2,000 | One additional MH and dismissal | 3 | 2 | 3 | 1.5× |
| 5,000 | Starting popularity becomes 10 | 3 | 2 | 10 | 1.5× |
| 10,000 | Higher starting coins | 3 | 2 | 10 | 3× |
| 24,000 | Two additional MH and dismissals | 5 | 4 | 10 | 3× |

The two coin upgrades combine additively: `1 + 0.5 + 1.5 = 3`, rather than multiplying 1.5 by 3.

Without Compound Interest, starting coins are the client's nearest-integer rounding of `5 × coin multiplier`: 5, 8, or 15. With the Compound Interest building bonus enabled:

`starting coins = round((5 + log2(max(credited Justice hours, 1))) × coin multiplier)`

The logarithm is not floored before the final rounding. New stories start at displayed case 1, with zero retirement chests and no active court agreements or court counters. Permanent bonus levels, credited monument hours, and prior Justice Opals remain account progress.

### Story availability and its multiplier

Let:

- `T` be accumulated story time in hours;
- `L` be the number of hours over which accumulation remains linear;
- `A` be the account multiplier from the Monument reward bonus supplied by Meritocracy and the applicable Legend Points bonus, multiplied together.

The story reward multiplier is:

`W = (min(T, L) / 20 + (1 + max(0, T − L) / 20)^0.3 − 1) × A`

A story can start when `W ≥ 1`. With no relevant bonuses, this takes 20 hours. The unmodified linear period is 48 hours. Time beyond that period still increases W, but uses the fractional-power term. It is not a hard storage cap.

For Justice, the linear period in hours is:

`L = 24 × (2 + B70 + B96 + 10G31 + 14J9 + LP27/24)`

Here B70 and B96 are the day contributions of Max Monument Rewards and Monument Mogmaxing, each normally 2 when owned and 0 otherwise; G31 is the applicable Superbit value; J9 is 1 when the Justice study is unlocked and 0 otherwise; and LP27 is the applicable Legend Points bonus value. The external reward multiplier is `A = (1 + MeritocracyBonus7/100) × (1 + LP27/100)`.

Story time is accumulated by the monument's elapsed-time system once its availability condition is met. It is separate from AFKing a character at the monument for permanent hours. Starting uses the entire current W for that story and resets its time accumulator; it does not subtract just one story's minimum charge. W affects retirement reward quantities, not court coin prices or encounter probabilities.

## 2. Resources and notation

| Symbol | Resource | Meaning |
| --- | --- | --- |
| M | Mental health | Checked after a decision to determine whether the story ends. |
| C | Court coins | Used in exchanges, payments, investments, and several selection conditions. |
| P | Popularity | Used in exchanges, payment checks, Gratefulbinger probability, and some forced encounters. |
| D | Dismissals | One is spent whenever the dismissal action is used. |
| R | Retirement chests | One reward selection per remaining chest when the story ends. Some requests can spend or remove chests during the story. |

Amounts such as `+3C` mean “add three court coins”; `+3SC` means “add three times S court coins,” and `+2SP` means “add twice S popularity.” `C := 0` means “replace the coin balance with zero.” `S` is the case multiplier:

`S = ceil(displayed case number / 5)`

S is 1 on cases 1–5, 2 on 6–10, 3 on 11–15, and so on. Only amounts explicitly written with S scale. Fixed health, chest, dismissal, coin, and popularity amounts remain fixed.

The client uses JavaScript rounding: `round(x) = floor(x + 0.5)` for the values discussed here. Thus `round(2.5) = 3`, but `round(−2.5) = −2`. `ceil` rounds upward and `floor` downward. The order of operations matters: rounding a negative resource change is not always equivalent to rounding a positive price and subtracting it.

Resources can temporarily fall below zero during action processing. M, C, P, and D receive a nonnegative integer clamp after the action. The ordinary rules also prevent a negative chest balance through payment gates and the chest flip's explicit boundary. Never Uncool then restores P to at least 5. These final clamps do not run continuously between every sub-effect.

## 3. The lifecycle of a case

### Arrival and presentation

On entry to a case, the client performs the following operations in order:

1. Draw an initial candidate request.
2. Advance the fixed-duration contracts: time-management investment, Crypto, Hedgefund, then approval lock. Matured payments and installments change C now.
3. Select the final request using the fifth-case rules or ordinary-case rules in section 4. Ghost's ordinary-case popularity drain occurs within this step.
4. Apply the selected character's arrival effects, in the order described below.
5. Display that request and allow a decision.

Arrival effects are caused by seeing the character. They do not depend on approving that character's new request. Rejecting or dismissing cannot undo them. Selection eligibility is evaluated before these character-specific arrival effects, so a selected request can become unaffordable after an arrival changes the balances.

The character-specific arrival effects are:

| Arriving character | Effects, in execution order |
| --- | --- |
| Honcho | Pay a pending student-loan investment, then apply pending Life Insurance. Each obligation is removed when processed. |
| Bored Bean | Return the stored all-coins loan and remove it. |
| Scripticus | Repay his kitchen loan, then Poppy's IOU; remove each paid obligation. |
| Reanimated Hand | If Above the Law is active, add 4C and subtract 2P. |
| Retirement Chester | Resolve his recorded-coin gamble, then remove it. |
| Concerned Poppy | Pay the recorded popularity-example return, then remove it. |

Ghost's drain precedes all of these. Ghost itself clamps its drain to zero. Hand's later −2P does not have that immediate clamp and can leave temporary negative popularity for the decision.

### Which actions are available

An unavailable or unaffordable action does not resolve or advance the case. An approval may be blocked by an explicit payment requirement, an active general approval lock, or the next-Timmy approval block. The catalogue lists each request's payment requirement.

- A **coin** requirement checks that C covers the absolute value of the request's rounded coin change.
- A **popularity** requirement similarly checks P.
- A **chest** requirement checks R.
- A **dismissal** payment requires at least one D.
- **None** means no resource-payment gate. Resource losses on that request can still be applied and then clamped to zero.

The payment check occurs before approval bonuses. Bean's +4C approval income therefore cannot fund a payment that was unaffordable when clicked.

Rejection has no corresponding resource-payment requirement. Dismissal requires at least one D. Reaper Contract additionally disables dismissal when the selected character is the Harbinger; Gratefulbinger is a separate character and is not covered by that restriction.

### Approval processing

Approval runs special behavior first, then adds the ordinary approval amounts from the request. The significant order is:

1. Record student-loan, kitchen-loan, and time-management payments; establish approval lock or Hand's agreement where applicable.
2. Execute Bean's all-coins loan or half-coins health purchase; resolve a winning Glass Gamble; establish Never Uncool or Bean's Bet where applicable.
3. Count an approved Fizarre Drink; establish Crypto, Hedgefund, or Chest Magnet; execute a losing Cool Bird adjustment if the flip loses.
4. Establish the Timmy block, apply Chester's conditional health cost, or establish/remove Ghost's permit as applicable.
5. Clear an existing Scripticus approval promise. If the current request is a new promise, establish it.
6. Execute Honcho's all-popularity buyout.
7. If Bean's Bet is active, add 4C. This includes the approval that first establishes the Bet.
8. Record Chester's coin-gamble threshold; execute Rupie's exchanges; establish Life Insurance; record and reduce Poppy's popularity; record Poppy's IOU; resolve Billionaire Chester's gift; establish Reaper Contract; execute Magic Rupie's swap, as applicable.
9. Increment ordinary Rupie progress or the approved ice-cream stage, as applicable.
10. Apply the current request's ordinary resource additions and subtractions.
11. Apply final resource normalization and Never Uncool's floor.

Consequently, Bean's loan records C before its approval bonus, Brain for Sale halves C before that bonus, and Rupie's exchanges use C after the bonus. Chester's gamble records C after the bonus. Magic Rupie swaps the bonus into P.

A resource change that temporarily takes M below zero does not independently end the story between these steps. Cool Bird's losing-health branch deliberately uses this ordering to preserve the last MH after its ordinary +2M is added.

### Rejection processing

Rejection applies the request's ordinary rejection changes first. It then:

1. Subtracts 1M and clears an outstanding Scripticus approval promise.
2. If the character is Timmy, increments the Timmy-rejection counter and clears a pending Timmy approval block.
3. If Bean's Bet is active, consumes one of its two rejection allowances. Consuming the second sets P to zero and removes the Bet.
4. Performs final normalization and applies Never Uncool's floor.

The rejection allowances are cumulative, not consecutive. Approving between two rejections does not restore an allowance.

### Dismissal processing

Dismissal subtracts 1D and does not apply the request's ordinary approval or rejection changes. It then:

1. Subtracts 1M if the request is Broke Again.
2. Adds 1R if the request is Bean's riddle.
3. Subtracts 1M and clears an outstanding Scripticus approval promise.
4. Removes Bean's Bet without its zero-popularity penalty.
5. Clears a pending Timmy approval block if this is a Timmy encounter.
6. Performs final normalization and applies Never Uncool's floor.

These effects stack. For example, dismissing Broke Again with an outstanding approval promise spends 1D and subtracts 2M.

### End-of-case check

After the action resolves, the client checks M. At M ≤ 0 it enters retirement. Otherwise, it advances the displayed case number by one and performs the next arrival sequence. Rejection and dismissal both consume the case just as approval does.

The death check is after the decision, not immediately after character-specific arrival effects. For example, Chester's pending gamble can reduce M to zero on arrival; a health-granting approval on that case can change M before the post-decision check. There is no fixed maximum case number in this progression.

## 4. How the next request is selected

The client contains **90 request rows**. Ordinary proposals select rows uniformly, not characters uniformly. Rows that share identical dialogue still count separately. Thus Grumblo's five ordinary gift rows contribute five entries to the lottery.

Random float draws come from `Math.random()`. Different random calls are separate draws. The documented odds follow these branch conditions; there is no popularity or streak modifier on Cool Bird or Glass Gamble.

### Every fifth case

Displayed cases 5, 10, 15, etc. follow this sequence:

1. If P ≥ 3, roll for Gratefulbinger with probability `0.4P / (P + 20)`. With P < 3, he cannot appear.
2. If that succeeds, select Gratefulbinger and do not perform the ordinary Harbinger overrides.
3. Otherwise choose uniformly among seven ordinary Harbinger rows.
4. If P is exactly zero, replace that row with Revenge Plot.
5. If C is exactly zero, replace it with the next broke variant and update the broke flag immediately on arrival: an unset flag produces Busted Bills and sets it; a set flag produces Broke Again and clears it.
6. Only when C is nonzero, if Timmy has been rejected at least three times, replace the selected row with Timmy Meltdown and clear the entire Timmy-rejection counter.

A solvent Harbinger visit does not clear the broke flag. Gratefulbinger does not consume the Timmy counter or toggle the broke flag. The Timmy counter is not cleared by approvals or dismissals of Timmy.

### Ordinary cases

On all other case numbers:

1. If Ghost's permit is active, subtract 1P and immediately clamp P to zero.
2. If Bean's all-coins loan is pending, a 15% roll replaces the initial proposal with one of his half-coins health purchase, riddle, or Bet rows, equally likely.
3. Reject any ineligible proposal and draw another uniformly from all 90 rows until eligible. A failed special Bean proposal goes through ordinary rerolls; it does not repeatedly receive the 15% special treatment.
4. On displayed cases 6, 11, 16, etc., a separate 40% roll replaces the selected row with Chester's 2S-coin chest trade or S-popularity chest trade, equally likely. These requests can also occur from the ordinary lottery.
5. If Chest Magnet is active, consume one use and replace the request with one of its six rows, equally likely. Harbinger rounds do not consume uses.
6. Otherwise, if at least three Fizarre Drinks have been approved since the last Secret, select Bean's Secret and clear the drink counter immediately on arrival.

A case need not be affordable to be eligible. The selector does not discard a coin-gated request just because its price exceeds C.

### Ordinary eligibility restrictions

All rows are ordinarily eligible except as restricted here:

| Request or group | Eligibility condition |
| --- | --- |
| All Harbinger requests, Gratefulbinger, and Bean's Secret | Excluded from the ordinary lottery; reached through the special selection rules. |
| Honcho's Life Insurance | M ≤ 1. |
| Timmy's four ice-cream stages | Only the row matching the current ice-cream stage. |
| Poppy's IOU | No outstanding Poppy IOU. |
| Magic Rupie | At least three ordinary Rupie approvals since the last accepted Magic Rupie. |
| Reaper Contract | Not already active. |
| General approval lock | Not already active. |
| Above the Law | Not already active. |
| Ghost's permit | Permit not active. |
| Ghost's reinstatement of the ban | Permit active. |
| Chest Magnet | No remaining magnet uses. |
| Hedgefund, Crypto, time-management investment | The corresponding investment is not pending. Each is checked separately. |
| Bean's all-coins loan | No outstanding Bean loan. |
| Bean's Bet | Bet not active. |

Other arrival-paid arrangements do not need extra repeat-suppression rules: their relevant visitor settles the previous arrangement on arrival before the new decision. Fifth-case and ordinary-case replacements follow their stated priority rather than becoming extra equally weighted lottery entries.

## 5. Complete request catalogue

The following tables give **base action results plus the indicated special behavior**. Existing agreements, arrival effects, final clamps, and the universal 1D dismissal cost apply in addition. “No change” means no request-specific resource change; it does not suppress those global effects.

Dismissal has no additional request-specific effect except for **Broke Again** (−1M) and **Bean's riddle** (+1R). Those exceptions are also listed in their entries. Every other request can be dismissed for the ordinary 1D cost when dismissal is available. Harbinger costs K3 through K8 and H are defined in section 6.

### Little Timmy

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Asks for coins | S coins | −SC; +2SP. | −SP. |
| Asks to call everyone stinky | None | −SP. | +SP. |
| YouTube subscription | None | +SP. | −2SP. |
| Stolen-toy bribe | None | +SC; −SP. | +SP. |
| School holiday | None | −3SC; +2SP. | No change. |
| Red ice cream | S coins | −SC; +SP. Advance ice-cream stage from 0 to 1. | −SP. |
| Blue ice cream | S coins | −SC; +SP. Advance ice-cream stage from 1 to 2. | −SP. |
| Yellow ice cream | 2S coins | −2SC; +SP. Advance ice-cream stage from 2 to 3. | −SP. |
| Ice-cream thank-you hug | None | +4M. Advance ice-cream stage from 3 to 4 and award the achievement. | −999P. |
| Demands free stuff | 2S coins | −2SC; +SP. | −5SP. |
| Calls the judge a poopy head | None | −SP. | −SP. |

### Reanimated Hand

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Asks to waive a fine | None | +SP. | +2SC; −SP. |
| Asks for bail | 3S coins | −3SC; +SP. | −SP. |
| Coins for a handshake | None | +5SC; −1M. | No change. |
| Chest for popularity | 1 chest | −1R; +4SP. | −SP. |
| Above the Law | None | −1P. Enable +4C/−2P on later Hand arrivals. | +2P. |

### Head Honcho of Big Biz LLC

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Student-loan investment | 3S coins | −3SC; −1P. Record the paid coins for a 2× Honcho-arrival repayment. | +2P. |
| Buys all popularity | None | C := C + 2P; P := 0, before any Bean approval bonus. | +1P. |
| Popularity investment | S popularity | −SP; +3SC. | +SP. |
| Time-management investment | 5S coins | −5SC. Record the payment for a 250% repayment after 15 advances. | +1P. |
| Crypto investment | 6 coins | −6C; −1P. Start 15 installments of +1C. | +1P. |
| Retirement hedgefund | 1 chest | −1R. Start 10 installments of +2C. | +1P. |
| Life Insurance | None | +4M. Arm the next-Honcho M/C/P reset to 1. | +2P. |
| Reaper Contract | None | +20SC. Permanently block Harbinger dismissal this story. | +1P. |

### Mister Bribe

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Cash with a popularity cost | None | +3SC; −SP. | +SP. |
| Cash with a health cost | None | +7SC; −1M. | +1P. |
| Clean coin | None | +1C. | −1P. |
| Block next Timmy approval | None | +3SC. Block approval of the next Timmy request. | No change. |
| Reverse bribe | S coins | −SC; +SP. | No change. |
| General approval lock | None | +7SC. Set approval-lock counter to 3. | No change. |

### The Harbinger

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Heart attack | K5 coins | −K5 C. | −1M. |
| Car-crash coma | K4 coins | −K4 C. | −1M. |
| Snake bite | K4 coins | −K4 C. | −1M. |
| Shark attack | K3 coins | −K3 C. | −1M. |
| Bad livestream | K4 coins | −K4 C. | −1M. |
| Rent payment | K3 coins | −K3 C. | −1M. |
| Blocked artery | K4 coins | −K4 C. | −1M. |
| Revenge plot | K6 coins | −K6 C. | −1M. |
| Timmy meltdown | K8 coins | −K8 C. | −1M. |
| Busted bills | S popularity | −SP; +round(H) C. | −1M. |
| Broke again | None | −1M. | −1M. Dismissal also subtracts 1M. |

### Retirement Chester

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Chest for 2S coins | 2S coins | +1R; −2SC. | No change. |
| Chest for S popularity | S popularity | +1R; −SP. | No change. |
| Chest for health | None | +1R. Subtract 1M only if M ≥ 2. | No change. |
| Chest taking both coins and popularity | None | +1R; −2SC; −SP. | No change. |
| Free chest | None | +1R. | No change. |
| Chest for 3S coins | 3S coins | +1R; −3SC. | No change. |
| Two-chest coin-balance gamble | None | +2R. Record C after any Bean approval bonus for the next Chester arrival. | No change. |
| Two chests for 10S coins | 10S coins | −10SC; +2R. | No change. |

### Scripticus

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Coins for popularity | None | −2SC; +SP. | −SP. |
| Promise to approve next case | None | +3SC. Require approval of the next case. | −1P. |
| Kitchen loan | 2S coins | −2SC; +SP. Record the payment for a 125% Scripticus-arrival repayment. | −SP. |

### Esquire Bored Bean

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Loan of all coins | None | +12P. Record and set C to zero before the Bean approval bonus; repay on Bean arrival. | No change. |
| Health for half the coins | None | +1M. First set C := floor(C/2). | No change. |
| Riddle | None | −1P. | −1P. Dismissal instead grants +1R. |
| Four-coin approval agreement | None | Start the Bet; +4C immediately through that agreement. | No change. |
| Secret after three drinks | None | +2SP. | −4SP. |

### The Gratefulbinger

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Gratefulbinger gift | None | +5C; +1R. | −999M. |

### Cool Bird

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Coin flip | None | 50% +3SC; 50% a net round(−1.95S)C. | No change. |
| Popularity flip | None | 50% +2SP; 50% a net round(−1.3S)P. | No change. |
| Chest flip | None | 50% R := R + 2; 50% R := max(0, R − 1). | No change. |
| Mental-health flip | None | 50% M := M + 2; 50% M := max(1, M − 1). | No change. |

### Chippy

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Asks to be eaten | None | +SP. | −SP. |

### Ghost

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Legalize scaring | None | +6SC. Enable the subsequent ordinary-arrival −1P drain. | +1P. |
| Reinstate the scaring ban | None | +4SC; +1P. Remove the scaring permit. | No change. |

### Grumblo

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Mystery gift: hidden chest row | S coins | −SC; +1R. | −1P. |
| Mystery gift: hidden scaled-popularity row | S coins | −SC; +3SP. | No change. |
| Mystery gift: hidden health row | S coins | −SC; +1M. | −1P. |
| Mystery gift: hidden fixed-popularity row | S coins | −SC; +2P. | No change. |
| Double gift: hidden chest row | 3S coins | −3SC; +2R. | No change. |
| Mystery gift: hidden dismissal row | S coins | −SC; +1D. | No change. |
| Double gift: hidden popularity row | 3S coins | −3SC; +4SP. | No change. |

### Fizarre Drink

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Chest Magnet drink | S coins | −SC. Set magnet uses to 3; count this drink. | No change. |
| Popularity drink | S coins | −SC; +SP. Count this drink. | No change. |
| Dismissal drink | S coins | −SC; +2D; −1M. Count this drink. | No change. |
| Never Uncool drink | S coins | Enable the post-action P ≥ 5 floor; −SC; count this drink. | No change. |
| Collectible-glass drink | S coins | 1/3 net +5SC; 2/3 −SC; count this drink. | No change. |

### Rupie Slug

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Popularity-to-coins exchange | None | C := ceil(C + 0.3P); P := ceil(0.8P). Increment Rupie progress. | No change. |
| Coins-to-popularity exchange | None | P := ceil(P + min(P/3, 0.3C)); C := ceil(0.8C). Increment Rupie progress. | No change. |
| Lost coins | None | −3SC; +6SP. Increment ordinary Rupie progress. | +3SC; −5SP. |
| Dismissal for health | 1 dismissal | −1D; +1M. Increment ordinary Rupie progress. | No change. |
| Admires the judge | None | +2P. Increment ordinary Rupie progress. | −5P. |
| Magic Rupie | None | +1M. First swap C and P after any Bean approval bonus; consume Rupie progress. | No change. |

### Concerned Poppy

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Popularity example for children | None | Record P; P := 1. Repay round(1.6 × recorded P) on the next Poppy arrival. | No change. |
| IOU repaid by Scripticus | 4S coins | −4SC; +5P. Record the payment for a 135% Scripticus-arrival repayment. | −3P. |
| Sells a dismissal | 6S coins | −6SC; +1D. | −2P. |
| Megafish request | None | +2SP. | −2SP. |
| Coins for health | None | +10SC; −1M. | −2P. |
| Community thank-you gift | None | +3SC; +2P. | −40P. |

### Billionaire Chester

| Request | Approval payment requirement | Approve | Reject |
| --- | --- | --- | --- |
| Free billionaire gift | None | 30% +2R; 63% +3R; 3.5% +2D; 3.5% +2C. | No change. |

## 6. Special calculations and continuing effects

### Harbinger payments and Gratefulbinger odds

For displayed case N, define:

`H = 1 + 0.25 × floor((N − 1)/13)`

`Kb = abs(round(−b × S × H))`

Kb is the coin payment for a Harbinger row with base cost b. The catalogue's K3, K4, K5, K6, and K8 use that definition. S scales in five-case groups; H increases on displayed cases 14, 27, 40, etc. H affects the Harbinger's coin changes only. Busted Bills therefore gives `round(H)` coins while its popularity payment is S.

| Displayed case | K3 | K4 | K5 | K6 | K8 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 3 | 4 | 5 | 6 | 8 |
| 10 | 6 | 8 | 10 | 12 | 16 |
| 15 | 11 | 15 | 19 | 22 | 30 |
| 20 | 15 | 20 | 25 | 30 | 40 |
| 25 | 19 | 25 | 31 | 37 | 50 |
| 30 | 27 | 36 | 45 | 54 | 72 |

The seven ordinary rows consist of two base-3 rows, four base-4 rows, and one base-5 row. Before the forced replacements, each of those seven rows has probability 1/7.

Gratefulbinger's percentage chance is `40P/(P + 20)` when P ≥ 3 and zero otherwise. It is approximately 5.22% at P = 3, 8% at 5, 20% at 20, and 26.67% at 40. It approaches but never reaches 40% for finite positive P. His gift is a fixed 5C and 1R; neither amount scales with the case. His rejection subtracts 999M, followed by the ordinary health clamp and death check.

### Bean's Bet

Approval establishes a two-rejection agreement. While it exists, every approval grants a fixed 4C, including acceptance of the agreement itself. This amount does not use S.

One rejection leaves the income active with one allowance remaining. A second rejection removes the agreement and sets P to zero after the request's normal rejection result. Never Uncool can then restore P to 5. A dismissal removes the agreement without this popularity reset. The Bet's request is excluded from the lottery while the agreement exists.

### Arrival-paid loans and returns

| Agreement | Recorded quantity on approval | Settlement on arrival | Settlement rounding |
| --- | --- | --- | --- |
| Honcho's student-loan investment | Coin payment, 3S | Next Honcho adds twice the recorded payment to C. | Nearest integer |
| Bean's all-coins loan | Entire C before the Bean approval bonus | Next Bean adds the recorded C back. | Nearest integer |
| Scripticus's kitchen loan | Coin payment, 2S | Next Scripticus adds 1.25 times the payment to C. | Round the resulting C upward |
| Poppy's IOU | Coin payment, 4S | Next Scripticus adds 1.35 times the payment to C. | Round the resulting C upward |
| Poppy's popularity example | Entire P immediately before setting P to 1 | Next Poppy adds `round(1.6 × recorded P)` to the then-current P. | Round the added amount to nearest |

There is no fixed case deadline for these visits. A payment uses the original recorded amount, not the later case multiplier. Settlement happens on arrival regardless of the action chosen for the new request, and removes the obligation.

For example, a kitchen loan of 2C returns 3C because `ceil(2 × 1.25) = 3`. A Poppy IOU of 4C returns 6C. A popularity example accepted at P = 20 records a later +32P; it does not replace the later popularity with 32.

### Investments paid by case advances

- **Time management:** accepting the request records the 5S coin payment and sets a 15-advance countdown. Each subsequent case entry subtracts one. At zero, C receives 2.5 times the recorded payment, rounded to nearest, and the investment is removed.
- **Crypto:** accepting pays a fixed 6C and 1P, then grants 1C at each of the next 15 case entries, for 15C total. The first installment arrives at the next case.
- **Retirement Hedgefund:** accepting spends 1R, then grants 2C at each of the next 10 case entries, for 20C total.

Harbinger entries count toward all three. Rejection and dismissal still advance them if the story continues. If the story ends before an installment or maturity, it does not run further cases to finish those payments. The three investments can coexist; the same investment cannot be accepted again while its own timer remains active.

### Life Insurance

Acceptance adds 4M and arms a single Honcho-arrival reset. On the next Honcho arrival, the client sets M, C, and P to 1. It leaves D and R unchanged and removes the insurance obligation. If student-loan repayment is also pending, that repayment happens first, then the reset overwrites C.

Insurance does not revive the story automatically when health is lost. Its +4M happens on acceptance; the later effect is a reset on seeing Honcho.

### Promises and action restrictions

**Scripticus's promise:** approval grants 3SC and requires approval of the next request. Approval clears the old promise without a penalty; rejecting or dismissing subtracts 1M and clears it. If the next approved request is another promise, the old one is fulfilled and a new one is created. An unaffordable or blocked approval does not waive the promise.

**General approval lock:** approval grants 7SC and sets a counter to 3. It becomes 2 at the next case entry, then 1, then is removed at zero. Approval is unavailable on the first two subsequent cases and available again on the third. The acceptance case accounts for the dialogue's third day.

**Next-Timmy block:** approval of Mister Bribe's request grants 3SC and disables approval at the next Timmy encounter. Rejecting or dismissing Timmy clears the block. Other characters do not clear it. Rejection increments Timmy's separate rejection counter; dismissal does not.

**Reaper Contract:** approval grants 20SC and disables Harbinger dismissal for the remainder of this story. There is no countdown or cancellation request. It does not disable rejection or payment, and it does not disable Gratefulbinger dismissal.

### Ghost, Hand, and the permanent popularity floor

Ghost's permit grants 6SC immediately. Starting on the next ordinary case, each ordinary entry subtracts 1P and clamps that drain to zero. Fifth cases skip the drain. Seeing Ghost's reinstatement request still incurs the ordinary entry drain before the decision. Approving reinstatement removes the permit and adds 4SC plus a fixed 1P.

Hand's agreement costs a fixed 1P on acceptance and causes later Hand arrivals to add a fixed 4C and subtract a fixed 2P. It lasts for the rest of the story. The arrival payment is independent of whether the new Hand request is approved, rejected, or dismissed.

Never Uncool establishes a P floor of 5 at the end of every action, including the action that buys the drink. Repeated purchases do not raise or stack this floor, but still spend the drink price and count as drink approvals.

The floor is not an arrival-time payment guarantee. If Ghost drains P from 5 to 4 before a request requiring 5P, that approval fails its payment check. Hand can also produce temporary negative P: arriving with P = 0 while the agreement is active gives P = −2; an approval granting +1P then reaches −1, which becomes zero at normalization, or 5 if Never Uncool is active.

### Chester's coin-balance gamble

Acceptance adds 2R and records C after Bean's approval bonus, if any. At the next Retirement Chester arrival:

- if the then-current C is lower than the recorded C, subtract 1M;
- otherwise there is no health change;
- remove the recorded obligation in either case.

The comparison uses coins after that case's scheduled income. Equality does not incur the loss. Billionaire Chester is a different character and does not resolve this agreement. The current Chester request is decided after this comparison.

### Cool Bird's flips

Each flip has a 50% winning branch and a 50% losing branch. There are no payment gates for the flips.

For coins and popularity, the client first performs a losing adjustment of −1.65 times the normal reward when the flip loses, rounds the resulting balance, then adds the normal reward. With integer starting balances, the net changes are:

| Flip | Winning branch | Losing branch before final resource clamp |
| --- | --- | --- |
| Coins | +3SC | `round(−1.95S)` C |
| Popularity | +2SP | `round(−1.3S)` P |
| Chests | +2R | R becomes `max(0, R − 1)` |
| Mental health | +2M | M becomes `max(1, M − 1)` |

The chest and health formulas come from explicit intermediate floors followed by the normal +2 reward. At 1M, the health flip ends at 3M or 1M. At 0R, the chest flip ends at 2R or 0R. Coins and popularity instead use the ordinary final zero clamp, and popularity may additionally receive Never Uncool's floor.

### Fizarre Drinks, the magnet, and the Secret

Each drink costs SC and requires that coin payment. Every approved drink adds one to the shared drink counter, including repeat purchases of Never Uncool. Rejection and dismissal do not add to it.

- **Popularity drink:** adds SP.
- **Dismissal drink:** adds 2D and subtracts 1M.
- **Never Uncool:** establishes the popularity floor described above.
- **Collectible glass:** a uniform integer draw from 1 through 3 wins on one value. The winner adds 6SC before the normal SC price is applied, for a net +5SC. The other two outcomes lose SC. The executable chance is 1/3 despite the dialogue's 1/4 claim.
- **Chest Magnet:** sets three uses. At each subsequent ordinary entry, consumes one and forces one of six equally likely Chester rows: 2S-coin trade, S-popularity trade, health trade, both-resources trade, free chest, or 3S-coin trade. There is no free payment or automatic approval attached to the forced request.

At three or more drink approvals, the next ordinary case without a magnet becomes Bean's Secret. Harbinger cases and magnet cases take priority and delay it. Its arrival clears the entire drink counter, not just three points, regardless of the action then chosen. Secret approval adds 2SP; rejection subtracts 4SP. Its Bean arrival can also return a pending Bean loan.

### Rupie progress and exchanges

The five ordinary Rupie requests—both exchanges, lost coins, dismissal for health, and admiration—each add one progress point on approval. Rejection and dismissal do not add progress. At three or more, Magic Rupie becomes eligible in the ordinary lottery. It is not forced to be the next request.

Magic Rupie approval swaps C and P, adds 1M, and clears the progress. Rejecting or dismissing does not clear progress. In the swap, the current C already includes any active Bean +4C approval bonus.

The two ordinary exchanges are deterministic and do not use S:

- **Popularity to coins:** using P before this exchange, set `C := ceil(C + 0.3P)`, then `P := ceil(0.8P)`.
- **Coins to popularity:** using C and P before this exchange, set `P := ceil(P + min(P/3, 0.3C))`, then `C := ceil(0.8C)`.

Both use balances after Bean's approval bonus and before final normalization. With C = 20 and P = 20 and no agreement bonus, their results are respectively C/P = 26/16 and 16/26. The second formula gives no popularity increase from P = 0.

### Timmy's ice creams and rejection count

The ice-cream stage starts at zero:

1. Approving the red request pays SC, adds SP, and changes the stage to 1.
2. Approving the blue request pays SC, adds SP, and changes the stage to 2.
3. Approving the yellow request pays 2SC, adds SP, and changes the stage to 3.
4. Approving the thank-you hug adds 4M, awards the associated achievement, and changes the stage to 4.

Only the request for the current stage can be selected. At stage 4, none of the four ice-cream rows match, so the sequence is finished for that story. It does not cycle. Rejection and dismissal leave the stage unchanged. The S used for each purchase is the multiplier of that particular case; prices are not locked to the first purchase's case.

The rejection count is independent of the ice-cream stage. Every rejection of any Timmy request adds one, including rejection of ice cream. At three or more it can cause the forced Harbinger event under section 4. The achievement from accepting the final hug also contributes to the separate account monument-AFK bonus calculation.

### Grumblo's hidden rows

The five Mystery Gift entries have identical dialogue and the same SC payment. The hidden request row determines the result before the player chooses an action; approval does not reroll which of those five rewards was selected.

Conditional on an ordinary Mystery Gift encounter, each hidden row has probability 1/5. The outcomes are 1R, 3SP, 1M, fixed 2P, or 1D. Only the chest and health rows carry a rejection penalty of fixed −1P, giving a 40% conditional rejection-penalty chance. The reward and rejection result belong to the same hidden row.

The two Double Gift rows likewise have identical dialogue and cost 3SC. One grants 2R and the other 4SP, with equal conditional probability. Both have no request-specific rejection effect.

### Billionaire Chester's gift

The client uses a chain of fresh random draws:

1. A 30% first-branch chance grants 2R.
2. Otherwise, a 90% conditional chance grants 3R: `70% × 90% = 63%` overall.
3. Otherwise, a 50/50 draw grants 2D or 2C: each is `70% × 10% × 50% = 3.5%` overall.

There is no payment, no scaling, and no arrival effect shared with Retirement Chester. Rejection and dismissal do not generate a gift.

## 7. Retirement and account rewards

### Transition to retirement

Once the post-decision check finds M ≤ 0, normal case progression stops. The fatal case remains the current displayed case; the client does not increment to another case for reward calculations.

If R is zero, the story finishes without a chest selection. Otherwise, each chest produces three offered rewards and the player chooses one. Choosing adds that reward to a temporary story reward total and spends one R. The game repeats with three newly generated offers until all R has been spent.

The other two offered rewards are not awarded. The same reward type can recur on later chests. Court coins, popularity, mental health, and dismissals have no automatic conversion to rewards. Unpaid loans and unfinished installments have no separate retirement payout.

### Generating the three reward types

Let `n = final displayed case − 1`. The client uses this zero-based case value in reward generation. The ten ordinary Justice bonus types have indices 0 through 9 in the table below.

Whenever it needs a new candidate type, it draws a random float U and computes:

`B = min(9, 2 + min(1, n/11) + min(3, n/16) + min(3, floor(U² × n/25)))`

It then draws another independent float V and proposes:

`type = floor(V × (B + 1))`

B can be fractional. The client does not floor B before its random-integer helper, so replacing this formula with a uniform draw through `floor(B)` changes the distribution. In particular, the highest proposed index can have a smaller interval of random values than the lower indices.

The candidate variable and all three offer slots begin at −1. Before assigning each slot, the client draws again while the candidate equals any slot. It then assigns the candidate to the current slot and calculates its quantity. The first offer alone can then be replaced with an Opal.

Normally the candidate now matches the previously assigned slot, so a new candidate is required for the next slot; duplicate types are rerolled. If the first offer became an Opal, however, the candidate still holds its original ordinary type while the first slot now holds the Opal type. The second slot therefore reuses that original ordinary type without a new type draw. The third slot then requires a fresh nonduplicate candidate. Final offers have distinct types, but this retained-candidate behavior affects their joint distribution.

### Generating a normal reward quantity

Let W be the story multiplier captured at the start, and let F be the account's all-monument bonus-level multiplier:

`F = max(1, 1 + applicable companion bonus / 100)`

For each accepted ordinary reward type, draw a new independent random float Q:

`base quantity = floor(max(1, (1 + n/13 + 4Q) × W))`

`quantity = floor(base quantity × F)`

The two floors occur separately. Longer case depth changes both the possible type distribution and the quantity calculation. The multiplier W remains the captured start value throughout this story.

### Opal replacement

Only the first of the three offers can become an Opal offer. Define:

- O = Justice Opals already recorded on the account before finalizing this story;
- J = the account's current percentage bonus to Justice Opal chance from its Justice reward bonus;
- B = the Justice-study percentage bonus to Opal chance;
- o = Opals already selected in this story's temporary rewards.

The first-offer replacement probability is:

`p = min(0.5, 0.5^O × (1 + J/100) × (1 + B/100)) × 0.5^o`

The outer story factor is applied **after** the 50% cap. A selected Opal increases o, reducing later replacement probability in the same story. An offered but unselected Opal does not increase o. Replacing the ordinary offer sets its quantity to 1 before the blue-chest roll; it does not retain the ordinary bonus-level quantity.

### Blue reward offers

Each of the three offers independently receives a blue-chest roll:

`blue probability = 0.001 × (1 + applicable Sushi reward bonus / 100)`

Without that bonus the chance is 0.1% per offer. A blue result doubles that offer's quantity, including an Opal offer. Consequently a blue Opal offer gives two Opals, and selecting it increases the temporary Opal total by two. The blue roll does not change the offered reward type.

### The ten permanent Justice bonuses

At the end of the reward sequence, selected ordinary quantities are added as levels to these account bonuses. Selected Opals are then awarded and added to Justice's cumulative Opal count. The temporary bonus levels selected earlier in this same retirement sequence are not applied to the account partway through generating its later choices.

| Index | Justice bonus | Coefficient a | Unamplified value from level v |
| ---: | --- | ---: | --- |
| 0 | Catching efficiency | 2 | `2v` |
| 1 | Harp note gain | 4 | `4v` |
| 2 | Artifact find chance | 500 | `500v/(250 + v)` |
| 3 | Villager EXP gain | 1 | `v` |
| 4 | All Summoning essence gain | 5 | `5v` |
| 5 | Justice Opal chance | 2 | `2v` |
| 6 | Class EXP gain | 1 | `v` |
| 7 | Daily Lamp wishes | 300 | `300v/(250 + v)` |
| 8 | All Monument AFK gain | 50 | `50v/(250 + v)` |
| 9 | Justice bonuses multiplier | 250 | `250v/(250 + v)` |

For coefficients below 30, the unamplified value is `a × v`. For coefficients of at least 30, it is `a × v/(250 + v)`. Amplification is applied before the latter result is rounded upward to a tenth of a percentage point.

Let Z be the applicable Justice Fountain percentage, X the applicable Cosmo percentage, and E9 the final percentage value of bonus 9. Define `finish(i, f)` as:

- for i = 0, 1, 3, 4, 5, 6: `aᵢ × vᵢ × f`;
- for i = 2, 7, 8, 9: `0.1 × ceil(10 × aᵢ × vᵢ/(250 + vᵢ) × f)`.

Then:

`E9 = finish(9, max(1, 1 + Z/100))`

`Ei = finish(i, max(1, (1 + E9/100 + X/100) × (1 + Z/100))), for i = 0…8`

Bonus 9 does not amplify itself. Bonuses displayed as multipliers use `1 + Ei/100`; for example, a final Harp-note percentage of 40 is displayed as 1.4×. How these account bonuses combine with the other bonuses in Catching, the Harp, Sailing, and other systems is determined by those systems' own calculations.

## 8. Source and verification boundary

Source: the [official play page](https://www.legendsofidleon.com/ytGl5oc/) and the [N.js client it loads](https://www.legendsofidleon.com/ytGl5oc/N.js). The September 5, 2026 download is 26,056,155 bytes with SHA-256:

`51d3a0ea0f156fa039a21ebaaa8ebfe0c966a12972fcb921504632b88e2d8245`

The request catalogue covers all 90 rows in the extracted client table, including the five indistinguishable Mystery Gift rows and two Double Gift rows. The explanations use executable selection, action, resource, and reward code where dialogue differs from behavior. External account bonuses enter the formulas through their named values; this document does not reproduce the progression rules of those separate game systems.

Source search anchors include `J_StartCoins`, `MonumentRewardMulti`, `JusticeAccept`, `JusticeReject`, `TimmyIceCream`, `BeanDeal`, `ScareLegal`, `ChestMag`, `Justice_OpalRewardChanceDEC`, and `Justice_BlueChestChanceDEC`. The documented rules are those of this inspected web-client version. A later deployment or another platform can differ.
