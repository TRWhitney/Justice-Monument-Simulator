"""Regressions from the simulation audit, including real offer combinations."""

from dataclasses import replace
from io import StringIO

import pytest
from rich.console import Console

from justice_sim.engine.reducer import (
    ActionNotAllowed,
    action_may_survive,
    apply_action,
    can_afford_action,
    preview_state_before_outcome,
)
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import UtilityWeights, utility
from justice_sim.models.offer import BernoulliSpec, EffectSpec, OutcomeSpec
from justice_sim.models.state import EncounterTrigger, GameState
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner
from justice_sim.ui_cli.cli import CliApp

pytestmark = pytest.mark.unit


def _resource(resource, amount):
    return EffectSpec("add_resource", {"resource": resource, "amount": amount})


def _planner(data):
    return RolloutPlanner(
        data,
        PlannerConfig(horizon_cases=0, rollouts_per_action=16, adaptive_rollouts=False),
        seed=7,
    )


@pytest.mark.parametrize("debt_mode", ["clamp_to_zero", "allow_negative"])
@pytest.mark.parametrize("coins, affordable", [(10, False), (11, True), (12, True)])
def test_shark_attack_uses_rounded_payment(builtin_data, coins, affordable, debt_mode):
    data = replace(
        builtin_data, defaults=replace(builtin_data.defaults, debt_mode=debt_mode)
    )
    offer = next(o for o in data.offers if "shark_attack" in o.id)
    state = GameState(15, coins, 3, 1, 0, 0)
    assert can_afford_action(state, offer, "approve", data) is affordable
    if not affordable:
        with pytest.raises(ActionNotAllowed, match="Insufficient funds"):
            apply_action(state, offer, "approve", data, Rng(0))
        return
    result, _ = apply_action(state, offer, "approve", data, Rng(0))
    assert (result.coins, result.mh) == (coins - 11, 1)
    assert _planner(data).recommend(state, offer).best_action == "approve"


@pytest.mark.parametrize("scheduled", [False, True])
def test_affordability_does_not_charge_inactive_or_deferred_effects(
    data_factory, scheduled
):
    data = data_factory()
    effect = (
        replace(_resource("coins", -10), schedule_after_cases=2)
        if scheduled
        else replace(_resource("coins", -10), when="false")
    )
    offer = replace(data.offers[0], approve=OutcomeSpec(effects=(effect,)))
    state = GameState(1, 0, 0, 3, 0, 0)
    assert can_afford_action(state, offer, "approve", data)
    result, _ = apply_action(state, offer, "approve", data, Rng(0))
    assert result.coins == 0
    assert bool(result.scheduled_events) is scheduled


def test_survival_preview_keeps_last_chance_gamble(builtin_data, promised_gamble):
    state, offer = promised_gamble
    assert apply_action(state, offer, "approve", builtin_data, Rng(0))[0].mh == 0
    assert apply_action(state, offer, "approve", builtin_data, Rng(1))[0].mh == 3
    assert action_may_survive(state, offer, "approve", builtin_data)
    assert not action_may_survive(state, offer, "reject", builtin_data)
    assert not action_may_survive(
        replace(state, ended=True), offer, "approve", builtin_data
    )


def test_cli_allows_manual_surviving_gamble(builtin_data, promised_gamble):
    state, offer = promised_gamble
    app = CliApp(builtin_data, SuggestedRules.empty(), console=Console(file=StringIO()))
    app.sim_mode = "none"
    app.session.state = state
    app.current_offer = offer
    before_rng = app.session.rng.state()
    assert app.handle_command("approve")
    assert app.pending_prompt.kind == "choice"
    assert app.session.state == state
    assert app.session.rng.state() == before_rng
    assert app.handle_command("choose 1")
    assert app.session.state.mh == 3
    assert app.session.state.required_action is None
    assert len(app.session.log.entries) == 1


def test_cli_manual_exchange_matches_full_simulation(builtin_data, ghost_exchange):
    state, offer = ghost_exchange
    app = CliApp(builtin_data, SuggestedRules.empty(), console=Console(file=StringIO()))
    app.sim_mode = "none"
    app.session.state = state
    app.current_offer = offer
    app.session.rng = Rng(0)
    expected, _ = apply_action(state, offer, "approve", builtin_data, Rng(0))
    assert app.handle_command("approve")
    assert app.pending_prompt is None
    assert app.session.state == expected
    assert (expected.coins, expected.pop) == (18, 0)
    assert len(app.session.log.entries) == 1


def test_preparation_preview_does_not_double_consume_trigger(data_factory):
    data = data_factory()
    offer = data.offers[0]
    trigger = EncounterTrigger(
        effects=(
            EffectSpec(
                "random_range_resource", {"resource": "coins", "min": 1, "max": 3}
            ),
        ),
        remaining_uses=1,
    )
    state = GameState(1, 5, 3, 3, 0, 0, encounter_triggers=(trigger,))
    rng = Rng(5)
    prepared = preview_state_before_outcome(
        state, offer, "approve", data, Rng.from_state(rng.state())
    )
    assert rng.state().draws == 0
    assert state.encounter_triggers == (trigger,)
    result, _ = apply_action(state, offer, "approve", data, rng)
    assert result.coins == prepared.coins + 2
    assert not result.encounter_triggers
    assert rng.state().draws == 1


def test_random_upside_scores_are_exact_without_rollouts(builtin_data):
    state = GameState(1, 5, 3, 3, 1, 0)
    offer = next(o for o in builtin_data.offers if o.npc_id == "billionaire_chester")
    planner = _planner(builtin_data)
    progress = []
    result = planner.recommend(state, offer, progress=progress.append)
    score = next(s for s in result.action_scores if s.action == "approve")
    # This checks the configured distribution independently of the planner.
    outcomes = [
        (replace(state, case_index=2, retirement_chests=2), 1 / 6),
        (replace(state, case_index=2, retirement_chests=3), 1 / 6),
        (replace(state, case_index=2, dismissals=3), 1 / 3),
        (replace(state, case_index=2, coins=6), 1 / 3),
    ]
    values = [(utility(s, builtin_data, planner.weights), p) for s, p in outcomes]
    expected = sum(v * p for v, p in values)
    assert result.best_action == "approve"
    assert progress == []
    assert score.sample_count == 0
    assert score.expected_chests == pytest.approx(5 / 6)
    assert score.expected_utility == pytest.approx(expected)
    assert score.variance == pytest.approx(
        sum(p * (v - expected) ** 2 for v, p in values)
    )
    assert score.variance > 0
    assert score.death_probability == 0


@pytest.mark.parametrize("change", ["base", "encounter", "penalty", "dismissal"])
def test_probability_uses_state_at_random_branch(data_factory, change):
    data = data_factory(include_grateful=False)
    state = GameState(1, 1, 3, 1, 1, 0)
    zero_coins = EffectSpec("set_resource", {"resource": "coins", "value": 0})
    action = "dismiss" if change == "dismissal" else "approve"
    outcome = OutcomeSpec(
        effects=(zero_coins,) if change == "base" else (),
        random=BernoulliSpec(
            "bernoulli",
            "dismissals" if change == "dismissal" else "coins",
            (_resource("coins", 100),),
            (_resource("mh", -1),),
        ),
    )
    offer = replace(
        data.offers[0],
        approve=OutcomeSpec(),
        reject=OutcomeSpec(),
        dismiss=OutcomeSpec(),
    )
    offer = replace(offer, **{action: outcome})
    if change == "encounter":
        state = replace(
            state,
            encounter_triggers=(
                EncounterTrigger(effects=(zero_coins,), remaining_uses=1),
            ),
        )
    elif change == "penalty":
        state = replace(
            state,
            required_action="reject",
            required_action_penalty_effects=(zero_coins,),
        )
    planner = _planner(data)
    actual, _ = apply_action(state, offer, action, data, Rng(1))
    assert actual.mh == 0
    assert planner._expected_action_value(
        state, offer, action, Rng(3)
    ) == pytest.approx(utility(actual, data, planner.weights))
    progress = []
    result = planner.recommend(state, offer, progress=progress.append)
    assert result.best_action != action
    assert progress  # The alleged guaranteed upside must not bypass rollouts.


def test_random_base_effects_have_branch_specific_probabilities(data_factory):
    data = data_factory(include_grateful=False)
    outcome = OutcomeSpec(
        effects=(
            EffectSpec(
                "random_range_resource", {"resource": "coins", "min": 0, "max": 1}
            ),
        ),
        random=BernoulliSpec(
            "bernoulli", "coins", (_resource("retirement_chests", 1),), ()
        ),
    )
    offer = replace(data.offers[0], approve=outcome)
    planner = _planner(data)
    planner.weights = UtilityWeights(
        w_chests=20,
        w_death=0,
        w_low_mh=0,
        w_insolvency=0,
        w_resources=0,
        w_dismissals=0,
        w_progress=0,
    )
    assert planner._expected_action_value(
        GameState(1, 0, 3, 3, 0, 0), offer, "approve", Rng(0)
    ) == pytest.approx(10)


def test_state_dependent_guaranteed_upside_still_short_circuits(data_factory):
    data = data_factory()
    offer = replace(
        data.offers[0],
        approve=OutcomeSpec(
            effects=(EffectSpec("set_resource", {"resource": "coins", "value": 1}),),
            random=BernoulliSpec(
                "bernoulli",
                "coins",
                (_resource("retirement_chests", 2),),
                (_resource("mh", -1),),
            ),
        ),
        reject=OutcomeSpec(),
    )
    progress = []
    result = _planner(data).recommend(
        GameState(1, 0, 3, 1, 0, 0), offer, progress=progress.append
    )
    assert result.best_action == "approve"
    assert progress == []
    score = next(s for s in result.action_scores if s.action == "approve")
    assert score.expected_chests == 2
    assert score.death_probability == 0


def test_shortcut_does_not_omit_unclassified_alternative(data_factory):
    data = data_factory()
    offer = replace(
        data.offers[0],
        approve=OutcomeSpec(effects=(_resource("coins", 1),)),
        reject=OutcomeSpec(
            effects=(
                EffectSpec(
                    "random_exchange",
                    {
                        "take_resource": "pop",
                        "give_resource": "retirement_chests",
                        "min": 1,
                        "max": 1,
                    },
                ),
            )
        ),
        dismiss=OutcomeSpec(),
    )
    progress = []
    result = _planner(data).recommend(
        GameState(1, 5, 1, 3, 1, 0), offer, progress=progress.append
    )
    assert result.best_action == "reject"
    assert progress
