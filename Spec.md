# Idleon Justice Simulator/Advisor — Codex Implementation Spec (Python + Qt + Rich + uv)

> Goal: A desktop Linux Python application that simulates the Idleon “Justice Monument” minigame.
> Users set their progression + starting state, then repeatedly input the current NPC/offer they see in-game.
> The app uses a JSON-driven rules database + a configurable lookahead simulator to recommend the best action (Approve/Reject/Dismiss) to maximize expected Retirement Chests, with configurable risk tolerance.
> Provide BOTH a Qt GUI and an interactive Rich CLI that share the same core engine.

---

## ✅ Core Objectives

- Maximize **expected number of Retirement Chests** over a run.
- Provide **lookahead-based** suggestions (simulation mode, not greedy-only).
- Risk is **user-configurable** (safety-first ⇄ greedy).
- Encounter distribution is configurable:
  - Default: uniform
  - Optional: user-defined weights
  - Optional: learned-from-logs estimator (does not apply unless enabled)
- Random outcomes use default probabilities and are easily overridden.
- Runs are fully replayable via session log; support undo.
- Import/export:
  - Player progression profiles
  - Active run state
  - Encounter model (weights + learned priors)
- JSON is the source of truth for NPCs/offers/effects. User can supply override JSON.

---

## ✅ Confirmed Mechanics (encode directly)

### Resources / State variables
- `case_index` (1-based)
- `coins` (Court Coins)
- `pop` (Popularity)
- `mh` (Mental Health)
- `dismissals` (consumed by Dismiss action; not affected by allow_insufficient_funds)
- `retirement_chests` (count)
- `active_effects` (timed buffs/debuffs; durations measured in cases)
- `scheduled_events` (trigger at a future case index)
- `constraints` / `promises` (e.g., “must approve next”, “cannot approve for N cases”)

### Scaling formulas
- For any numeric expression object with `scaling: "case"`: multiply by:
  - `case_scale = ceil(case_index / 5)`
- Numeric expression objects default to `scaling: "none"` when omitted.
- For `scaling: "harbinger"`: multiply by:
  - `harbinger_cost` (from `special_rules.harbinger.cost_expr`)
- Harbinger coin cost:
  - `harbinger_cost = ceil(case_index / 5) * (1 + 0.25 * floor((case_index - 1) / 13))`

### Harbinger cadence
- Harbinger encounter happens on every case where `case_index % 5 == 0`
- Only override is **replacement chance** by Gratefulbinger.

### Gratefulbinger replacement chance
- When Harbinger is scheduled, replace with Gratefulbinger with probability:
  - `p_replace_percent = (40 * pop) / (pop + 20)`
  - Convert to probability in [0, 1] as needed.

### “Days”
- Any “days” duration is interpreted as **cases**.

### Scheduled events if run ends
- If the run ends before an event triggers, it never triggers.

### Insufficient funds policy (global + per-offer)
- Default behavior: block actions that would reduce non-negative resources
  (coins, pop, retirement_chests, dismissals) below 0 unless
  `allow_insufficient_funds` is true; when allowed, costs clamp at 0.
- Implement a global `debt_mode`:
  - `clamp_to_zero` (default)
  - `allow_negative`

---

## ✅ Unknown / Modelled Items (must be configurable)

- NPC/offer encounter distribution
- Many random outcomes (coin flips, “random gift”, etc.)
- Any “inconsistency/bug” behaviors: encode as defaults in JSON, allow override

---

## 📦 Tech Stack & Constraints

- Language: Python 3.12+
- Package manager: `uv` (NOT pip)
- GUI: Qt via `PySide6`
- CLI: `rich` + `prompt_toolkit` (or `textual` if preferred, but keep it simple)
- Data: JSON (built-in) + optional user override JSON
- No network features in runtime (offline-only)
- No automation/OCR required (user selects NPC/offer via search/dropdowns)

---

## 🗂️ Project Structure (required)

JusticeMonumentSimulator/
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ Spec.md
├─ scripts/
│  ├─ validate_repo.sh
│  └─ validate_schema.py
├─ src/
│  └─ justice_sim/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ config.py
│     ├─ models/
│     │  ├─ __init__.py
│     │  ├─ state.py
│     │  ├─ offer.py
│     │  ├─ actions.py
│     │  └─ outcomes.py
│     ├─ data/
│     │  ├─ builtin/
│     │  │  ├─ justice_data.json
│     │  │  ├─ suggested_rules.json
│     │  │  └─ images/
│     │  │     └─ (pngs for npcs and icons...)
│     │  └─ schema/
│     │     ├─ justice_data.schema.json
│     │     └─ suggested_rules.schema.json
│     ├─ engine/
│     │  ├─ __init__.py
│     │  ├─ reducer.py
│     │  ├─ effects.py
│     │  ├─ encounter.py
│     │  ├─ harbinger.py
│     │  ├─ rng.py
│     │  └─ scoring.py
│     ├─ planner/
│     │  ├─ __init__.py
│     │  ├─ rollout.py
│     │  ├─ mcts.py
│     │  └─ cache.py
│     ├─ persistence/
│     │  ├─ __init__.py
│     │  ├─ profiles.py
│     │  ├─ runs.py
│     │  └─ logs.py
│     ├─ ui_qt/
│     │  ├─ __init__.py
│     │  ├─ app.py
│     │  ├─ main_window.py
│     │  └─ widgets/
│     │     ├─ __init__.py
│     │     ├─ offer_search.py
│     │     ├─ offer_card.py
│     │     ├─ state_panel.py
│     │     ├─ suggestion_panel.py
│     │     └─ log_panel.py
│     ├─ ui_cli/
│     │  ├─ __init__.py
│     │  ├─ cli.py
│     │  ├─ screens.py
│     │  ├─ search.py
│     │  └─ render.py
│     └─ util/
│        ├─ __init__.py
│        ├─ expr.py
│        ├─ validation.py
│        └─ assets.py
└─ tests/
   ├─ (test files as necessary...)
   └─ fixtures/
      └─ tiny_data.json


---

## 🧠 Data Model (JSON Source of Truth)

### Top-level JSON
- `version`: string (e.g., "justice_data")
- `npcs`: list of NPC entries
- `offers`: list of offer entries
- `special_rules`: includes harbinger/gratefulbinger definitions
- `defaults`: global defaults (probabilities, clamp settings, etc.)

### NPC entry
- `id`: stable string
- `name`: display name
- `image`: relative path to packaged image (or optional user override path)
- `tags`: list of strings (search keywords)

### Offer entry
- `id`: stable string
- `npc_id`: foreign key
- `title`: short name
- `text`: in-game offer text
- `actions_available`: subset of ["approve", "reject", "dismiss"]
- `approve`: outcome spec
- `reject`: outcome spec
- `dismiss`: outcome spec (optional)
- `conditions`: list of predicates that must be true for the offer to be eligible (for chain events)
- `chain`: optional chain metadata (e.g., “if approved, schedule offer X in N cases”)
- `notes`: optional free text
- `allow_insufficient_funds`: optional override for this offer

### Outcome spec (generic)
An outcome is a list of `effects` applied in order. It may also contain random branching.

Outcome fields:
- `effects`: list of effect objects
- `random`: optional random spec:
  - `type`: "bernoulli" | "categorical"
  - `p`: probability (for bernoulli)
  - `choices`: list of { `weight`, `effects` } (for categorical)

### Effect object (must be extensible)
Each effect is a dict:
- `type`: string enum
- `params`: dict
- optional `when`: predicate
- optional `duration_cases`: int (for buffs/debuffs)
- optional `schedule_after_cases`: int (to create scheduled events)

Minimum built-in effect types:
- `add_resource` (coins/pop/mh/dismissals/retirement_chests)
- `set_resource`
- `clamp_resource` (min/max)
- `multiply_resource` (rare; keep)
- `add_flag` / `remove_flag`
- `add_status` (timed status, e.g., cannot_approve)
- `schedule_effects` (trigger later)
- `require_next_action` (e.g., must_approve_next)
- `modify_encounter_weights` (temporary weight change)
- `end_run` (game over)
- `noop`

### Predicates
Use a safe mini-language (NOT eval):
- comparison ops: == != < <= > >=
- boolean ops: and/or/not
- state fields: case_index, coins, pop, mh, dismissals, flags, statuses
- helper funcs: `has_flag("x")`, `has_status("y")`

Implement in `util/expr.py` with a small parser or `ast`-based whitelist.

---

## 🎯 Simulation & Planning

### Utility function (maximize chests + risk config)
Define utility for a terminal state `S`:
- `U(S) = w_chests * retirement_chests
         - w_death * I(mh <= 0)
         - w_low_mh * max(0, mh_threshold - mh)
         - w_insolvency * I(next_harbinger_unpayable_without_dismissal)
         + w_resources * (coins_scaled + pop_scaled + dismissals_scaled)`

Where:
- defaults emphasize chests but strongly penalize death.
- risk slider modifies weights:
  - “Safe”: high w_death, high w_insolvency
  - “Greedy”: lower penalties, higher w_resources

### Planner default: hybrid rollout
- For the currently observed offer, evaluate each available action:
  - Apply action deterministically; where outcome has random branching, compute expected by sampling OR exact expansion for small branch sets.
- Short-circuit recommendation without rollouts only when every current action is terminal. Nonterminal actions always receive horizon-based metrics, including when a rule constrains the recommendation to one action.
- From the resulting state, run Monte Carlo rollouts for H future cases:
  - Each rollout selects future encounters from the configured EncounterModel
  - Alternative current actions use common random-number streams so their comparison is not dominated by unrelated encounter samples.
  - At each simulated encounter, use a 1-step greedy policy with safety constraints. Explicit random branches are compared by expected immediate utility; effects that cannot be expanded use a small sample mean.
- Aggregate expected utility, expected chests, death probability, variance, and a 95% utility confidence interval; recommend the eligible action with highest expected utility.

### Defaults (reasonable)
- Horizon H = 12 cases
- Rollouts per action = 200
- RNG seed configurable; default random seed each session, but log it for reproducibility
- Adaptive option:
  - if the top two utility estimates overlap within their sampling uncertainty, increase to 400 rollouts per action

### Performance requirements
- Recommendation should complete in < 1 second on a typical desktop for default settings (best-effort)
- Implement caching:
  - hash GameState to memoize value estimates
  - cache encounter expansions for the same case_index/pop bucket if needed

---

## 🎲 Encounter Models

### Interface: EncounterModel
- `sample_encounter(state, rng) -> offer_id`
- `eligible_offers(state) -> list[offer_id]` (respects conditions and chain restrictions)
- `update_from_log(event)` (optional; used by learned model)

### Implementations
1) `UniformEncounterModel` (default)
- uniform over eligible offers except forced specials (Harbinger logic injected separately)

2) `WeightedEncounterModel`
- user supplies weights by npc_id and/or offer_id
- final weight = npc_weight * offer_weight

3) `LearnedEncounterModel`
- maintains Dirichlet counts (priors configurable)
- updates counts from session logs
- can export/import priors
- NOT used unless explicitly enabled; otherwise only logs training.

### Harbinger injection
- In the encounter selection pipeline:
  - If `case_index % 5 == 0`: return Harbinger-like encounter
  - With Gratefulbinger replacement probability, return Gratefulbinger instead
  - If `special_rules.harbinger.offer_pool` is defined, select a random eligible offer from that pool; otherwise use `offer_id`
- These specials live in JSON `special_rules` but are implemented by engine, not the generic encounter model.

---

## 🧾 Logging, Undo, Import/Export

### Session log requirements
Each step records:
- timestamp
- pre_state snapshot (or hash + delta)
- encountered offer_id
- action taken
- RNG seed or RNG advancement info (for reproducibility)
- post_state snapshot (or delta)
- any random branch chosen

Undo:
- revert to previous pre_state snapshot
- planner should re-run from restored state

Export formats
- `profile.json`: progression + preferences + encounter model config
- `run_state.json`: full current state + log + RNG seed
- `learned_model.json`: Dirichlet counts/priors

---

## 🖥️ Qt GUI Requirements (PySide6)

### Main layout (single window)
Left column: State & Controls
- Current state panel: case, coins, pop, health, dismissals, chests
  - `[-]` icon value `[+]` controls adjust values during a run (case stays fixed)
  - Holding `[-]`/`[+]` steadily adjusts the value, with repeat speed increasing over hold duration
  - Default starting state: coins 5, pop 3, health 1, dismissals 0
- Progression/profile selector + load/save buttons
- Encounter model selector + settings button
- Risk slider + planner settings (horizon, rollouts, adaptive)
  - Full simulate toggle picks a random encounter each case
- Planner settings include a “Full simulate” toggle (when off, user selects random outcomes)
- Import/export run buttons
- Toast notifications appear beneath import/export buttons

Center: Offer selection
- Search bar:
  - If input starts with `#`, treat remainder as NPC-name filter
  - Empty input shows all offers currently eligible in the pool
  - On harbinger cases (every 5th), search input is locked/greyed to `#binger`
  - Otherwise substring search over:
    - NPC name
    - offer title/text
    - approve/reject summary text (rendered from effects)
  - Optional “Show all offers” toggle inside the search bar ignores conditions
  - NPC quick-filter button row ends with a circle-slash clear button that clears the current filter and is dimmed only when no filter is active
- Results list:
  - each row displays “card”:
    - NPC image
    - NPC name
    - Offer title + offer text
    - Approve summary line + Reject summary line (icons ok but optional)
  - When no search filter is active, show encounter-luck rank suffix next to deal name: `<npc>: <title> (<rank>/<possible>)`
  - If “Show All” is enabled with no search filter, rank pool is all offers; otherwise rank pool is currently available offers
  - Ranking uses hybrid scoring: one-step utility baseline, blended with planner simulation utility when available for a state/offer
- Select result sets “current observed offer”

Right column: Recommendation + actions + log
- Recommendation panel:
  - Top recommended action with:
    - estimated expected chests (rollout mean)
    - estimated death probability (from rollouts)
    - confidence/variance display
  - Show top 3 actions
- Action buttons:
  - “Apply Approve/Reject/Dismiss/Skip” (records in log)
  - “Apply Recommended”
  - Below “Apply Recommended”, show run-level deal-luck indicator (color-coded red→green) aggregated from logged deal rankings
  - If no valid action remains or all actions would drop MH to 0, replace buttons with a red “Game Over” label
- Log panel:
  - list of steps with brief summary
  - Undo button (undo last step)
  - Jump-to-step (optional)
  - Manual state adjustments add debounced log entries that merge when consecutive
  - Hover card shows encounter luck ranking as `<rank>/<possible>` with red→green color based on closeness to best

### GUI behavior
- Planner runs when offer is selected or settings change.
- Planner should cancel the previous worker process if a new selection occurs.
- Use a worker process for planning so CPU-bound simulation never blocks the UI process.
- If no offer is selected, action buttons (except Skip) appear dimmed and prompt to select an offer first.

---

## 💻 Rich CLI Requirements

Command: `justice-sim`

Command-driven REPL:
- `state` / `status` to show resources and selection
- `search <query>` and `list` for offer discovery
  - `#npc` filtering
  - `$term` effect-only filtering
  - `show-all on/off` to ignore offer conditions when allowed
- `select <#>` to choose an offer; `offer` shows full details
- `recommend` to show planner output (disabled in sim mode `none`)
- `apply <approve|reject|dismiss|skip|best>` (plus `approve/reject/dismiss/skip/best` shorthands)
- `undo` to revert last action
- `log` / `log show <#>` for run history and details
- `reset` to restart the run
- `import <path>` / `export <path>` for run state
- `adjust <resource> <delta>` supports coins/pop/mh/dismissals/chests mid-run
- `save-profile <path>` / `load-profile <path>` for planner settings
- `planner set risk|horizon|rollouts <value>` to tune the planner
- `sim full|mid|none` to switch simulation modes:
  - `full`: auto-roll randomness and auto-pick encounters
  - `mid`: manual randomness with recommendations enabled
  - `none`: manual randomness, recommendations disabled
- `choose <#>` / `value <n>` / `cancel` to resolve manual randomness

CLI must reuse the same `OfferSearch` code and `Planner` engine as GUI.

---

## 🧪 Testing & Validation

### Unit tests (required)
- Scaling factor: `ceil(case/5)` correct for cases 1..30
- Harbinger cost formula spot checks
- Gratefulbinger probability formula spot checks
- Effect application:
  - add/set/clamp
  - timed statuses decrement each case
  - scheduled events trigger correctly
- Encounter injection:
  - harbinger on multiples of 5, gratefulbinger replacement probability path (use deterministic RNG seeds)
- Planner smoke test:
  - using tiny_data fixture, ensures returns a recommendation without errors

### Data validation
- Validate builtin JSON at startup.
- Validate user override JSON and show helpful error messages:
  - unknown effect type
  - missing npc_id
  - malformed predicate
  - duplicate IDs

---

## 🔧 uv + packaging requirements

### pyproject.toml
- Define console scripts:
  - `justice-sim = justice_sim.ui_cli.cli:main`
  - `justice-sim-gui = justice_sim.ui_qt.app:main`
- Dependencies (minimum):
  - PySide6
  - rich
  - prompt_toolkit
  - pydantic (optional but recommended for validation)
  - numpy (optional; only if planner needs it)
- No pip instructions; all commands use `uv`.

### Developer commands (document in README)
- `uv sync`
- `uv run justice-sim`
- `uv run justice-sim-gui`
- `uv run pytest`

---

## ✅ Implementation Checklist (Codex must follow)

### Phase 0 — scaffolding
- [x] Create repo structure exactly as specified
- [x] Set up `pyproject.toml` for uv with scripts
- [x] Add basic README with run commands

### Phase 1 — core models & validation
- [x] Implement dataclasses/pydantic models for NPC, Offer, Outcome, Effect, GameState
- [x] Implement JSON loader + schema validation + good error messages
- [x] Add builtin `justice_data.json` with a minimal viable subset (at least: one normal NPC offer, Harbinger, Gratefulbinger)

### Phase 2 — engine
- [x] Implement reducer: apply action -> new state
- [x] Implement effect engine with scheduling + timed statuses
- [x] Implement insufficient-funds behavior: per-offer + global debt_mode
- [x] Implement harbinger injection + gratefulbinger replacement
- [x] Implement deterministic RNG wrapper with seed logging

### Phase 3 — encounter models
- [x] Uniform encounter model
- [x] Weighted encounter model
- [x] Learned encounter model (Dirichlet counts) + training-from-log
- [x] Import/export learned priors; ensure not auto-applied unless enabled

### Phase 4 — planner
- [x] Implement rollout planner with configurable horizon/rollouts
- [x] Implement utility scoring + risk slider mapping
- [x] Implement adaptive rollouts when close calls
- [x] Add caching/memoization for performance

### Phase 5 — search & offer rendering
- [x] Implement shared offer search:
  - [x] `#npc` prefix filtering
  - [x] `$term` effect-only filtering (approve/reject summaries)
  - [x] substring across npc/title/text/outcome summaries
- [x] Implement “offer card summary” renderer for GUI + CLI

### Phase 6 — CLI (Rich)
- [x] Implement interactive loop with search, recommendation, apply action
- [x] Implement undo, import/export, profile load/save
- [x] Ensure CLI uses core engine/planner/search modules only
- [x] Expand CLI to command-driven REPL with sim modes, show-all toggle, planner controls, and log detail

### Phase 7 — GUI (Qt)
- [x] Implement main window layout with panels described
- [x] Implement offer search widget + card list with NPC images
- [x] Implement suggestion panel with metrics + apply buttons
- [x] Implement session log panel + undo
- [x] Run planner in worker process with cancellation
- [x] Add Mid/Full encounter-luck ranking on log hover cards (`rank/possible`, red→green)

### Phase 8 — persistence
- [x] Implement profile save/load (progression + settings)
- [x] Implement run state save/load (full state + log + RNG seed)
- [x] Ensure backwards-compatible version fields

### Phase 9 — tests
- [x] Add unit tests for formulas, effect timing, harbinger injection
- [x] Add planner smoke tests with tiny fixture data
- [x] Add data validation tests

### Phase 10 — data completion workflow
- [ ] Document how to expand `justice_data.json` from the user’s info dump
- [ ] Ensure adding offers requires no code changes (JSON-only)

---

## ✅ Acceptance Criteria (Definition of Done)

- GUI and CLI both run on Linux via `uv run ...`
- User can configure progression/start state, select offer, and get recommendation
- Lookahead simulation works and is configurable (horizon/rollouts/risk/encounter model)
- Session log records every step; undo works reliably
- Import/export for profiles and run states works
- JSON-driven effects cover all mechanics without adding new code for each offer
- Tests pass with `uv run pytest`

---

## Notes to Codex (implementation style)
- Prefer pure functions for reducer/effect application.
- Keep engine deterministic under a fixed RNG seed.
- Avoid tight coupling between UI and engine.
- Design effect system to be future-proof: new effects should be addable without rewriting planner/UI.

# Suggested rules
- Notes: Rules that say "Always", "Never", or "Only" are enforced as hard constraints; "Prefer" rules are soft biases.
- [x] Timmy: Stinky Head and Poopy Head - It's a lose-lose, but rejecting adds to Harbinger/Timmy interaction so it should always, if possible, be approved
- [x] Timmy: Ice Cream - Prefer approving if not in imminent danger
- [x] Reanimated Hand: Bail Me Out - Prefer rejecting unless very far ahead of the curve in coins (determine ahead of the curve based on how much money 3x (x is for the case number formula) is compared to how many coins you have)
- [x] Reanimated Hand: Waive the Fine - Prefer accepting unless low on coins (behind the curve in coins using money 2x compared to how many coins you have)
- [x] Reanimated Hand: Chest Heist - Always approve this unless cannot afford.
- [x] Head Honcho: Hedgefund - Never approve after case 15, prefer not to approve between 10-15, no bias prior to case 10.
- [x] Head Honcho: 15-Day Return - Only approve if very far ahead of the curve (compare money 5x to how many coins you have)
- [x] Head Honcho: Pop Futures - Only reject if you're far ahead of the curve (compared money 3x to how many coins you have)
- [x] Head Honcho: Life Insurance - Never approve unless on 1 health
- [x] Head Honcho: Reaper Contract - Never approve unless at 1 or less dismissals, in which case no bias
- [x] Mister Bribe: Approval Lock - Never approve if within 3 cases of a Harbinger (getting gratefulbinger with this is certain death)
- [x] Scripticus: Promise Me - Never approve if the next case is a Harbinger
- [x] Cool Bird: Sanity Flip - Prefer not to approve at low health
- [x] Fizzare Drink: All (but Chest Magnet) - Prefer to approve fizarre deals (except no bias on Chest Magnet)
- [x] Retirement Chester: Vitality Trade - Never approve if over 1 health
- [x] Retirement Chester: Double Dip - Prefer not to approve
- [x] Retirement Chester: Jackpot Boost - Prefer not to approve
