from dataclasses import replace

import pytest

from justice_sim.engine.rng import Rng
from justice_sim.models.offer import (
    BernoulliSpec,
    ChainSpec,
    ChainStep,
    EffectSpec,
    OutcomeSpec,
)
from justice_sim.models.state import ForcedEncounter, GameState
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


def _rare_choice(data_factory, reward):
    data = data_factory(include_grateful=False)
    quiet = replace(data.offers[1], approve=OutcomeSpec(), reject=OutcomeSpec())
    offer = replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=OutcomeSpec(
            random=BernoulliSpec(
                type="bernoulli",
                p=0.99,
                then_effects=(
                    EffectSpec(
                        "add_resource",
                        {"resource": "coins", "amount": reward},
                        schedule_after_cases=2,
                    ),
                ),
                else_effects=(
                    EffectSpec("add_resource", {"resource": "mh", "amount": -3}),
                ),
            )
        ),
        reject=OutcomeSpec(),
    )
    data = replace(data, offers_by_id={**data.offers_by_id, quiet.id: quiet})
    state = GameState(
        1, 100, 3, 3, 0, 0, forced_encounters=(ForcedEncounter(2, quiet.id),)
    )
    return data, offer, state


@pytest.mark.parametrize("reward,expected_action", [(10, "reject"), (30, "approve")])
def test_future_policy_integrates_rare_loss_with_delayed_reward(
    data_factory, reward, expected_action
):
    data, offer, state = _rare_choice(data_factory, reward)
    planner = RolloutPlanner.from_defaults(data, seed=1)
    # Independent arithmetic: quiet survival ends at case 3 with utility 11.8.
    # Death ends at case 2: 10.3 resources + 1 progress - 150 death - 16 low MH.
    expected = 0.99 * (11.8 + reward * 0.1) + 0.01 * -154.7
    exact = planner._exact_action_results(state, offer, "approve")
    for seed in range(100):
        rng = Rng(seed)
        before = rng.state()
        assert planner._select_action(state, offer, rng, remaining=1) == expected_action
        assert rng.state() == before
        assert planner._continuation_value(
            state, offer, "approve", rng, 1, encounter_start=None, exact_results=exact
        ) == pytest.approx(expected)


def test_enumerated_policy_keeps_full_depth_and_paired_independent_streams(
    data_factory, monkeypatch
):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data, seed=3)
    state = GameState(1, 100, 3, 3, 0, 0)
    branches = [(replace(state, coins=110), 0.9), (replace(state, coins=90), 0.1)]
    calls = []

    def simulate(branch, rng, remaining, *, improve_policy=True):
        calls.append((branch.coins, rng.state(), remaining, improve_policy))
        rng.random()
        return branch

    monkeypatch.setattr(planner, "_simulate_future", simulate)
    rng = Rng(9)
    planner._continuation_value(
        state,
        data.offers[0],
        "approve",
        rng,
        39,
        encounter_start=None,
        exact_results=branches,
    )
    assert len(calls) == 4
    assert all(depth == 39 and improve is False for _, _, depth, improve in calls)
    assert calls[0][1] == calls[1][1]
    assert calls[2][1] == calls[3][1]
    assert calls[0][1] != calls[2][1]
    assert rng.state().draws == 0


def test_root_values_access_to_a_future_choice_with_safe_optimal_policy(data_factory):
    data, gamble, state = _rare_choice(data_factory, 10)
    quiet_id = state.forced_encounters[0].offer_id
    root = replace(
        data.offers[3],
        approve=OutcomeSpec(
            effects=(EffectSpec("add_resource", {"resource": "coins", "amount": 1}),)
        ),
        reject=OutcomeSpec(),
        chain=ChainSpec(
            steps=(
                ChainStep("approve", 1, gamble.id),
                ChainStep("reject", 1, quiet_id),
            )
        ),
    )
    data = replace(data, offers_by_id={**data.offers_by_id, gamble.id: gamble})
    state = replace(state, forced_encounters=(ForcedEncounter(3, quiet_id),))
    planner = RolloutPlanner.from_defaults(data, seed=42)
    planner.config = replace(
        planner.config,
        horizon_cases=2,
        rollouts_per_action=200,
        adaptive_rollouts=False,
    )
    result = planner.recommend(state, root)
    # Approval gives a free coin. Rejecting the later unfavorable gamble then
    # reaches the same safe terminal state as rejecting the root, plus that coin.
    scores = {score.action: score for score in result.action_scores}
    assert result.best_action == "approve"
    assert scores["approve"].expected_utility - scores[
        "reject"
    ].expected_utility == pytest.approx(0.1)
    assert all(score.death_probability == 0 for score in result.action_scores)


def test_unexpanded_random_preparation_keeps_sampled_full_continuations(
    data_factory, monkeypatch
):
    from justice_sim.engine.reducer import apply_action
    from justice_sim.models.state import EncounterTrigger

    data = data_factory()
    offer = replace(data.offers[0], approve=OutcomeSpec(), reject=OutcomeSpec())
    state = GameState(
        1,
        100,
        3,
        3,
        0,
        0,
        encounter_triggers=(
            EncounterTrigger(
                (
                    EffectSpec(
                        "random_range_resource",
                        {"resource": "coins", "min": 0, "max": 20},
                    ),
                )
            ),
        ),
    )
    planner = RolloutPlanner.from_defaults(data)
    assert planner._exact_action_results(state, offer, "approve") is None
    calls = []

    def simulate(next_state, rng, remaining, *, improve_policy=True):
        calls.append((next_state, rng.state(), remaining, improve_policy))
        return next_state

    monkeypatch.setattr(planner, "_simulate_future", simulate)
    rng = Rng(17)
    planner._continuation_value(state, offer, "approve", rng, 20, encounter_start=None)
    assert len(calls) == 2
    for index, (actual, rng_state, depth, improve) in enumerate(calls):
        reference_rng = rng.spawn(index)
        expected, _ = apply_action(state, offer, "approve", data, reference_rng)
        assert (actual, rng_state) == (expected, reference_rng.state())
        assert depth == 20 and improve is False
    assert rng.state().draws == 0
