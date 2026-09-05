# Simulation optimization verification

Measured with Python 3.12.3, builtin data and suggested rules, seed 42, and
Scripticus: Kitchen Loan at case 11 with 50 coins, 20 popularity, 8 MH,
2 dismissals, and no existing commitments. Timings exclude data loading and GUI
startup. Benchmarks ran separately from test suites on this machine.

| Implementation and horizon | Root samples per action | Seconds |
| --- | --- | --- |
| Original, horizon 12 | 200 | 114.69 |
| Optimized, horizon 12 | 200 | 35.06 |
| Optimized, horizon 20 | 200 | 102.73 |

Adaptive sampling was enabled, with the unchanged maximum of 400; none of these
three recommendations needed a top-up. The same-horizon speedup is about 3.27x.
The new default evaluates 67% more future cases and completed about 10% sooner
than the original default in this scenario. This is not a latency guarantee:
different states, commitments, offers, hardware, and adaptive top-ups change work.
The longer horizon still has approximately quadratic policy-comparison cost.

The original audit also measured five samples per action, without adaptive
sampling: approximately 3.05 seconds at horizon 12, 8.48 at 20, 19.07 at 30,
and 30.09 at 40. Final optimized probes took 0.94 and 2.72 seconds at 12 and 20.
Small probes are timing evidence, not recommendation-quality assessments.

## Reproduce

```bash
uv run python scripts/benchmark_planner.py \
  --output /tmp/justice-planner-benchmark.json
```

Use `--rollouts 5 --no-adaptive` for a short probe, or `--offer` to select another
builtin title. The output records state, settings, seed, sample counts, timing,
and a hash of every recommendation score and utility sample. No personal run is
loaded. The script writes an artifact only when `--output` is provided.

The final 200-sample hashes are:

- Horizon 12: `1f155263a81b5121666a4bc25c21c95662bf5442d539205377ee624340d18001`
- Horizon 20: `70fbf18ec7ef7d4db56e8bc64c466f4b92c49b254b6ba09901f10fdc8558799f`

## Behavioral verification

Direct tests compare health probes with full reducer actions, including active
agreements, random preparation, fractional resources, and a required-action
penalty that drains coins after affordability succeeds. Cache tests cover saved
counter expressions with whitespace, parentheses, and line continuations.
Formula tests compare cached results with full context evaluation. Rollout tests
compare samples, complete terminal states, and RNG draw counts with deterministic
transition reuse disabled. Single-branch random outcomes still consume a draw.

The builtin-horizon test follows Honcho's actual 15-case investment through quiet
forced encounters: its payout lies outside the former horizon and inside 20.

Run `./scripts/validate_repo.sh` for formatting, lint, both schemas, all marked unit
and Qt tests, and smoke launch. Direct GUI coverage includes real worker
completion, returning to a cached offer, changed state/settings, and clearing
a completed Mid selection. This native Qt repository has no Playwright suite.

Optional direct GUI review captures:

```bash
JUSTICE_OPTIMIZATION_ARTIFACT_DIR=/tmp/justice-optimization-review \
  uv run --with pytest pytest tests/gui/test_recommendation_reuse.py -q
```

Ordinary verification produces no success screenshots and does not update
tracked review artifacts.
