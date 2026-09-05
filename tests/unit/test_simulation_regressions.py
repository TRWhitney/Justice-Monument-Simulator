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
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
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
