# Headless recommendations

`justice_sim.headless` is the public library interface. Importing it loads no Qt
modules and opens no window. Builtin data, suggested rules and validation schemas
are included in the wheel and loaded with `importlib.resources`. The existing
`justice-sim` and `justice-sim-gui` entry points and installation dependencies remain.

```python
from justice_sim.headless import (
    GameState,
    RolloutPlanner,
    load_builtin_data,
    load_builtin_suggested_rules,
)

data = load_builtin_data()
rules = load_builtin_suggested_rules(data)
planner = RolloutPlanner.from_defaults(data, rules, seed=42)
offer = data.offers_by_id[offer_id]  # The encounter visible in the overlay.
state = GameState(
    case_index=11,
    coins=14,
    pop=7,
    mh=8,
    dismissals=2,
    retirement_chests=0,
    # Include the run's remaining agreements, triggers and overrides here.
)
recommendation = planner.recommend(state, offer, arrival_processed=True)
print(recommendation.best_action)
```

`from_defaults` uses the dataset's planner defaults. Construct a `PlannerConfig`
explicitly when the consumer needs a different configuration. The API preserves
risk presets, horizon, initial samples and adaptive maxima. Supplying the same
seed, data, configuration and decision state reproduces sampling.

## Prepared decisions

`arrival_processed` is an optional keyword on `recommend`,
`recommend_incremental` and `rollout_work_total`. It defaults to `False`, which
retains existing pre-arrival behavior.

Set it to `True` when the supplied state already reflects the current encounter's
arrival effects and override consumption. The root preserves the supplied
resources and remaining overrides. It still applies the chosen action, action
agreements, dismissal costs, outcome, normalization and case advancement through
the reducer. Simulated future encounters process their arrivals and consume
remaining override uses normally.

The consumer must reconstruct the full `GameState`, including active statuses,
flags, counters, resource floors, scheduled events, triggers, requirements and
remaining encounter overrides. The library does not decode Idleon memory or
infer agreements from visible resource totals. Keep input state, data, rules and
encounter-model configuration stable while a recommendation is running. Use a
separate planner for concurrent decisions.

For example, a visible Ghost/Hand state with 14 coins and 7 popularity stays at
those values during root arrival preparation. Ordinary pre-arrival preparation
would apply the effects and produce 18 coins and 4 popularity. A Chest Magnet
with two remaining uses keeps both at the prepared root.

## Incremental estimates and cancellation

```python
from threading import Event

obsolete = Event()
updates = planner.recommend_incremental(
    state,
    offer,
    arrival_processed=True,
    batch_size=1,
    cancelled=obsolete.is_set,
)
for update in updates:
    display_estimates(update.best_action, update.action_scores)
    if update.cancelled:
        break
    if update.complete:
        final = update.recommendation
```

Each immutable `PlannerUpdate` contains `recommendation`, `complete` and
`cancelled`, plus convenience accessors `best_action` and `action_scores`.
Each `ActionScore` contains the action, sample count, expected utility, expected
chests, death probability and variance. Excluded actions have zero samples and
utility `-inf`. Exact shortcuts have zero Monte Carlo samples and can complete
in a single update.

`batch_size` defaults to one sample per active action. A batch with three active
actions can execute three samples. Larger batches reduce reporting overhead but
increase cancellation latency. Cancellation is cooperative, checked before
preparation and between batches. Calling `obsolete.set()` causes the iterator to
emit a terminal update with `cancelled=True` and `complete=False`; it does not
interrupt a rollout already in progress. Closing the iterator with
`updates.close()` also stops further work.

Batch size changes reporting frequency only. Adaptive contender selection occurs
at the configured initial and top-up boundaries. The final recommendation,
including sample sequences, matches the synchronous API across batch sizes.
Intermediate moments are updated per observation; final moments use the existing
synchronous aggregation. Intermediate updates omit `utility_samples` to avoid
copying every observation on every update. The completed recommendation retains
those samples as before. Completion means the configured sampling policy finished,
not that the suggested action is certain to be optimal.

The iterator performs work on the calling thread. An overlay should consume it
on its own worker thread and pass immutable updates to its display thread.
The existing synchronous `progress` callback still receives one increment per
completed sample.

## Verification and latency

The package regression test builds a wheel, installs it with locked dependencies
into a temporary virtual environment, then imports and invokes the public API
from outside the checkout with Qt imports blocked. It checks both installed
entry points and package resource files.

See the [latency measurements](latency.md),
[decision record](../adr/0019-headless-prepared-and-incremental-decisions.md) and
[configurable options](../adr/headless-options.html).

## Optional CPU workers

Both recommendation APIs accept `workers=1`. Larger positive integers opt into
spawned CPU processes; existing GUI and CLI calls retain one-process behavior.
Uniform, weighted and learned builtin encounter models support workers. Custom
planner or model types must use one worker to preserve their dispatch.

Use a guarded executable entry point, as required by Python process spawning:

```python
from justice_sim.headless import GameState, RolloutPlanner, load_builtin_data


def main():
    data = load_builtin_data()
    planner = RolloutPlanner.from_defaults(data, seed=42)
    offer = next(o for o in data.offers if o.title == "Scripticus: Kitchen Loan")
    result = planner.recommend(GameState(11, 50, 20, 8, 2, 0), offer, workers=4)
    print(result.best_action)


if __name__ == "__main__":
    main()
```

For an overlay, pass `workers=4` to `recommend_incremental` alongside its prepared
state and cancellation predicate. The iterator still runs on the consuming
thread, while child processes calculate the sampled rollouts. `batch_size=1`
submits one sample per active action, so three actions initially occupy at most
three workers. Larger batches offer more parallel tasks but wait longer before
reporting or checking cancellation. No future batches are submitted ahead.

Workers use identical absolute sample indices and deliver observations in the
original order. Final results and every utility sample match local execution,
including adaptive top-ups. Worker count does not change sampling budgets or
horizon. Each decision starts fresh processes and caches; startup can outweigh
parallel gains for small workloads. Pick the worker count for the host's spare
CPU capacity using the [execution comparison](../adr/planner-execution-options.html).

Cancellation, completion and iterator close release all owned processes. Worker
errors propagate to the consumer. If the consumer breaks iteration early, use
`try/finally: updates.close()` or `contextlib.closing(updates)` to release workers
immediately. The synchronous progress callback receives aggregate increments for
completed samples in each parallel batch; its sum is the completed sample count.
The temporary-install test also runs real CPU sampling with Qt imports blocked
in the parent and spawned workers.
